from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.models.entities import FunctionalCase, Organization, Project, Role, TestRun as RunModel, User
from backend.services.auth_service import hash_password
from backend.services.member_service import bind_member_to_organization
from backend.services.tenant_service import seed_default_organization
from tests.auth_helpers import login_with_encrypted_password


@pytest.fixture()
def dashboard_tenant_data(db):
    suffix = uuid.uuid4().hex[:8]
    default_org = seed_default_organization(db)
    acme = Organization(slug=f"dash-acme-{suffix}", name="Dash ACME", max_projects=10, monthly_ai_token_quota=0)
    db.add(acme)
    db.commit()

    acme_proj = Project(organization_id=acme.id, name="ACME Only", code_root="/tmp/acme")
    default_proj = Project(organization_id=default_org.id, name="Default Only", code_root="/tmp/def")
    db.add_all([acme_proj, default_proj])
    db.flush()
    db.add(FunctionalCase(project_id=acme_proj.id, title="acme case", steps=["a"]))
    db.add(FunctionalCase(project_id=default_proj.id, title="def case", steps=["b"]))
    db.add(RunModel(project_id=acme_proj.id, status="completed"))
    db.add(RunModel(project_id=default_proj.id, status="failed"))
    db.commit()

    member_role = db.query(Role).filter(Role.name == "member").one()
    pwd = "dash123456"
    user = User(
        username=f"dash_user_{suffix}",
        password_hash=hash_password(pwd),
        is_active=True,
        organization_id=default_org.id,
    )
    db.add(user)
    db.flush()
    bind_member_to_organization(db, org=default_org, user=user, role_ids=[member_role.id])
    db.commit()

    return {
        "default_org": default_org,
        "acme": acme,
        "password": pwd,
        "username": user.username,
        "acme_project_id": acme_proj.id,
        "default_project_id": default_proj.id,
    }


@pytest.fixture()
def tenant_headers(client: TestClient, dashboard_tenant_data: dict) -> dict[str, str]:
    res = login_with_encrypted_password(
        client,
        username=dashboard_tenant_data["username"],
        password=dashboard_tenant_data["password"],
    )
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_dashboard_summary_scoped_to_tenant_org(
    client: TestClient,
    tenant_headers: dict,
    dashboard_tenant_data: dict,
):
    res = client.get("/dashboard/summary", headers=tenant_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["organization_id"] == dashboard_tenant_data["default_org"].id
    assert body["case_count"] == 1
    assert body["total_run_count"] == 1
    assert body["project_count"] >= 1


def test_dashboard_tenant_cannot_query_other_org(
    client: TestClient,
    tenant_headers: dict,
    dashboard_tenant_data: dict,
):
    other = dashboard_tenant_data["acme"].id
    res = client.get(f"/dashboard/summary?organization_id={other}", headers=tenant_headers)
    assert res.status_code == 403


def test_dashboard_admin_global_vs_org_filter(
    client: TestClient,
    admin_headers: dict,
    dashboard_tenant_data: dict,
):
    global_res = client.get("/dashboard/summary", headers=admin_headers)
    assert global_res.status_code == 200
    assert global_res.json()["organization_id"] is None
    assert global_res.json()["project_count"] >= 2

    acme_id = dashboard_tenant_data["acme"].id
    scoped = client.get(f"/dashboard/summary?organization_id={acme_id}", headers=admin_headers)
    assert scoped.status_code == 200
    assert scoped.json()["organization_id"] == acme_id
    assert scoped.json()["project_count"] == 1
    assert scoped.json()["case_count"] == 1


def test_run_trends_scoped(client: TestClient, tenant_headers: dict, dashboard_tenant_data: dict):
    res = client.get("/dashboard/run-trends?days=7", headers=tenant_headers)
    assert res.status_code == 200
    assert res.json()["organization_id"] == dashboard_tenant_data["default_org"].id
    total = sum(p["total"] for p in res.json()["points"])
    assert total >= 1


def test_dashboard_overview_merged(client: TestClient, admin_headers: dict):
    res = client.get("/dashboard/overview?days=14", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "summary" in body
    assert "run_trends" in body
    assert body["run_trends"]["days"] == 14
    assert body["summary"]["organization_id"] is None
    assert body["system_overview"] is not None
    assert body["ai_usage"] is not None
    assert "user_count" in body["system_overview"]
    assert "by_module" in body["ai_usage"]


def test_dashboard_overview_tenant_scoped(
    client: TestClient,
    tenant_headers: dict,
    dashboard_tenant_data: dict,
):
    summary_res = client.get("/dashboard/summary", headers=tenant_headers)
    res = client.get("/dashboard/overview?days=7", headers=tenant_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    org_id = dashboard_tenant_data["default_org"].id
    assert body["summary"] == summary_res.json()
    assert body["run_trends"]["organization_id"] == org_id
    assert len(body["run_trends"]["points"]) == 7
