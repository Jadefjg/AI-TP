from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.models.entities import Organization, Project, Role, User
from backend.services.billing_service import build_invoice_pdf, generate_invoice
from backend.services.member_service import bind_member_to_organization
from backend.services.oidc_service import _organization_slug_from_claims
from backend.services.tenant_service import get_project_for_user, seed_default_organization


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_org_member_role_binding(db, client: TestClient, admin_headers: dict):
    org = seed_default_organization(db)
    member_role = db.query(Role).filter(Role.name == "member").one()
    user = User(
        username="tenant_user_1",
        display_name="Tenant",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    bind_member_to_organization(db, org=org, user=user, role_ids=[member_role.id])
    assert user.organization_id == org.id
    res = client.get(f"/organizations/{org.id}/members", headers=admin_headers)
    assert res.status_code == 200
    assert any(m["username"] == "tenant_user_1" for m in res.json())


def test_ai_route_tenant_denied(db):
    default_org = seed_default_organization(db)
    acme = Organization(slug="acme-iso", name="ACME", max_projects=5, monthly_ai_token_quota=0)
    db.add(acme)
    db.commit()
    proj = Project(organization_id=acme.id, name="Secret", code_root="/tmp/x")
    db.add(proj)
    db.commit()

    member_role = db.query(Role).filter(Role.name == "member").one()
    user = User(
        username="scoped_u_iso",
        password_hash="x",
        is_active=True,
        organization_id=default_org.id,
    )
    user.roles = [member_role]
    db.add(user)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        get_project_for_user(db, user, proj.id)
    assert exc.value.status_code == 403


def test_billing_invoice_pdf(db):
    org = seed_default_organization(db)
    invoice = generate_invoice(db, org=org, period="2025-06")
    pdf = build_invoice_pdf(invoice, org)
    assert pdf[:4] == b"%PDF"


def test_oidc_org_slug_claim():
    assert _organization_slug_from_claims({"org_slug": "Acme"}) == "acme"
    assert _organization_slug_from_claims({"tenant": "t1"}) == "t1"


def test_billing_generate_api(client: TestClient, admin_headers: dict, db):
    org = seed_default_organization(db)
    res = client.post(f"/organizations/{org.id}/billing/invoices/generate", headers=admin_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["period"]
    pdf = client.get(
        f"/organizations/{org.id}/billing/invoices/{body['id']}/pdf",
        headers=admin_headers,
    )
    assert pdf.status_code == 200
    assert "application/pdf" in pdf.headers["content-type"]


def test_billing_checkout_mock_without_stripe(client: TestClient, admin_headers: dict, db):
    org = seed_default_organization(db)
    invoice = generate_invoice(db, org=org, period="2025-07")
    assert invoice.status == "issued"
    res = client.post(
        f"/organizations/{org.id}/billing/checkout",
        headers=admin_headers,
        json={
            "invoice_id": invoice.id,
            "success_url": "http://127.0.0.1:5174/billing/success",
            "cancel_url": "http://127.0.0.1:5174/billing/cancel",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["mock"] is True
    assert body["checkout_url"] == "http://127.0.0.1:5174/billing/success"
    db.refresh(invoice)
    assert invoice.status == "paid"
    assert invoice.stripe_checkout_session_id.startswith("mock_cs_")
