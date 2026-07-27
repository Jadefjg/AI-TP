from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.db import session as db_session
from backend.models.entities import Organization, Project, User
from backend.services.credential_service import encrypt_secret, mask_secret
from backend.services.tenant_service import assert_ai_token_quota, organization_token_usage, seed_default_organization


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_organization_seeded(db):
    org = seed_default_organization(db)
    assert org.slug == "default"
    assert db.query(Project).filter(Project.organization_id.is_(None)).count() == 0


def test_admin_lists_all_organizations_when_bound_to_default_org(
    client: TestClient,
    admin_headers: dict,
    db,
):
    default_org = seed_default_organization(db)
    extra = Organization(slug="bound-admin-extra", name="Extra Org", max_projects=10, monthly_ai_token_quota=0)
    db.add(extra)
    admin = db.query(User).filter(User.username == get_settings().bootstrap_admin_username).one()
    admin.organization_id = default_org.id
    db.commit()

    res = client.get("/organizations", headers=admin_headers)
    assert res.status_code == 200, res.text
    slugs = {row["slug"] for row in res.json()}
    assert "bound-admin-extra" in slugs
    assert default_org.slug in slugs


def test_create_organization_duplicate_slug_message(client: TestClient, admin_headers: dict):
    first = client.post(
        "/organizations",
        headers=admin_headers,
        json={"slug": "dup-org", "name": "Dup Org", "max_projects": 1, "monthly_ai_token_quota": 0},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/organizations",
        headers=admin_headers,
        json={"slug": "dup-org", "name": "Dup Org 2", "max_projects": 1, "monthly_ai_token_quota": 0},
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "部门编码已存在，请更换编码"


def test_create_organization_and_quota(client: TestClient, admin_headers: dict):
    res = client.post(
        "/organizations",
        headers=admin_headers,
        json={"slug": "acme", "name": "ACME", "max_projects": 2, "monthly_ai_token_quota": 1000},
    )
    assert res.status_code == 200, res.text
    org_id = res.json()["id"]
    q = client.get(f"/organizations/{org_id}/quota", headers=admin_headers)
    assert q.status_code == 200
    assert q.json()["project_count"] == 0
    assert q.json()["monthly_ai_token_quota"] == 1000


def test_project_quota_enforced(client: TestClient, admin_headers: dict):
    org_res = client.post(
        "/organizations",
        headers=admin_headers,
        json={"slug": "tiny", "name": "Tiny", "max_projects": 1, "monthly_ai_token_quota": 0},
    )
    org_id = org_res.json()["id"]
    p1 = client.post(
        "/projects",
        headers=admin_headers,
        json={"organization_id": org_id, "name": "P1", "code_root": "/tmp/p1"},
    )
    assert p1.status_code == 200
    p2 = client.post(
        "/projects",
        headers=admin_headers,
        json={"organization_id": org_id, "name": "P2", "code_root": "/tmp/p2"},
    )
    assert p2.status_code == 429


def test_project_byok_credentials(client: TestClient, admin_headers: dict):
    proj = client.post(
        "/projects",
        headers=admin_headers,
        json={"name": "BYOK", "code_root": "/tmp/byok"},
    ).json()
    put = client.put(
        f"/projects/{proj['id']}/ai-credentials",
        headers=admin_headers,
        json={
            "provider": "openai",
            "api_base_url": "https://api.openai.com/v1",
            "api_key": "sk-test-key-12345678",
            "model_override": "gpt-4o-mini",
            "enabled": True,
        },
    )
    assert put.status_code == 200
    body = put.json()
    assert body["configured"] is True
    assert "sk-t" in (body["api_key_masked"] or "")


def test_audit_export(client: TestClient, admin_headers: dict):
    res = client.get("/logs/export?days=7", headers=admin_headers)
    assert res.status_code == 200
    assert "id,created_at" in res.text


def test_ai_quota_raises(db):
    org = Organization(slug="qtest", name="Q", max_projects=10, monthly_ai_token_quota=10)
    db.add(org)
    db.commit()
    db.refresh(org)
    from backend.models.entities import AiCallLog

    db.add(
        AiCallLog(
            organization_id=org.id,
            project_id=None,
            module_type="test",
            model_name="m",
            prompt_tokens=8,
            completion_tokens=8,
            latency_ms=1,
            status="success",
        )
    )
    db.commit()
    assert organization_token_usage(db, org.id) == 16
    with pytest.raises(Exception) as exc:
        assert_ai_token_quota(db, org, extra_tokens=1)
    assert exc.value.status_code == 429  # type: ignore[attr-defined]


def test_credential_mask():
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a...mnop"
