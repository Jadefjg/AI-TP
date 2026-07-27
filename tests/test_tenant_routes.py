"""PR-1: cross-tenant access must return 403 on project-scoped routes."""

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
def tenant_setup(db):
    """User in default org; project in acme org."""
    suffix = uuid.uuid4().hex[:8]
    default_org = seed_default_organization(db)
    acme = Organization(slug=f"acme-pr1-{suffix}", name="ACME PR1", max_projects=10, monthly_ai_token_quota=0)
    db.add(acme)
    db.commit()
    db.refresh(acme)

    foreign = Project(organization_id=acme.id, name="Foreign", code_root="/tmp/foreign")
    db.add(foreign)
    db.commit()
    db.refresh(foreign)

    case = FunctionalCase(project_id=foreign.id, title="secret", steps=["x"])
    db.add(case)
    run = RunModel(project_id=foreign.id, status="completed")
    db.add(run)
    db.commit()
    db.refresh(case)
    db.refresh(run)

    member_role = db.query(Role).filter(Role.name == "member").one()
    pwd = "tenant123456"
    user = User(
        username=f"pr1_tenant_{suffix}",
        display_name="PR1 Tenant",
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
        "foreign_project": foreign,
        "foreign_case": case,
        "foreign_run": run,
        "password": pwd,
        "username": user.username,
    }


@pytest.fixture()
def tenant_headers(client: TestClient, tenant_setup: dict) -> dict[str, str]:
    res = login_with_encrypted_password(
        client,
        username=tenant_setup["username"],
        password=tenant_setup["password"],
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/projects/{pid}/functional-cases"),
        ("POST", "/projects/{pid}/functional-cases"),
        ("GET", "/projects/{pid}/knowledge/chunks"),
        ("GET", "/projects/{pid}/test-plans"),
        ("GET", "/projects/{pid}/api-regression-sets"),
        ("GET", "/projects/{pid}/perf/k6-jobs"),
        ("GET", "/projects/{pid}/workbench/sessions"),
        ("GET", "/projects/{pid}/integrations/ci"),
        ("GET", "/projects/{pid}/recipients"),
        ("POST", "/projects/{pid}/recipients"),
        ("POST", "/projects/{pid}/runs"),
    ],
)
def test_cross_tenant_project_routes_forbidden(
    client: TestClient,
    tenant_headers: dict,
    tenant_setup: dict,
    method: str,
    path: str,
):
    pid = tenant_setup["foreign_project"].id
    url = path.format(pid=pid)
    body = None
    if method == "POST":
        if "runs" in url:
            body = {"kinds": ["unit"]}
        elif "functional-cases" in url:
            body = {"title": "x", "steps": []}
        elif "recipients" in url:
            body = {"email": "blocked@example.com"}
    res = client.request(method, url, headers=tenant_headers, json=body)
    assert res.status_code == 403, res.text


def test_cross_tenant_run_routes_forbidden(
    client: TestClient,
    tenant_headers: dict,
    tenant_setup: dict,
):
    run_id = tenant_setup["foreign_run"].id
    for path in (
        f"/runs/{run_id}",
        f"/runs/{run_id}/reports",
        f"/runs/{run_id}/reports/html",
    ):
        method = "GET" if "html" in path or path.endswith(str(run_id)) else "POST"
        res = client.request(method, path, headers=tenant_headers)
        assert res.status_code == 403, res.text


def test_cross_tenant_case_detail_forbidden(
    client: TestClient,
    tenant_headers: dict,
    tenant_setup: dict,
):
    pid = tenant_setup["foreign_project"].id
    cid = tenant_setup["foreign_case"].id
    res = client.get(f"/projects/{pid}/functional-cases/{cid}", headers=tenant_headers)
    assert res.status_code == 403


def test_platform_admin_can_access_foreign_project(
    client: TestClient,
    admin_headers: dict,
    tenant_setup: dict,
):
    pid = tenant_setup["foreign_project"].id
    res = client.get(f"/projects/{pid}/functional-cases", headers=admin_headers)
    assert res.status_code == 200


def test_list_recent_runs_scoped_to_tenant(
    client: TestClient,
    tenant_headers: dict,
    tenant_setup: dict,
    db,
):
    own = Project(
        organization_id=tenant_setup["default_org"].id,
        name="Own",
        code_root="/tmp/own",
    )
    db.add(own)
    db.flush()
    db.add(RunModel(project_id=own.id, status="completed"))
    db.commit()

    res = client.get("/runs/recent?limit=50", headers=tenant_headers)
    assert res.status_code == 200
    ids = {r["project_id"] for r in res.json()}
    assert tenant_setup["foreign_project"].id not in ids
    assert own.id in ids
