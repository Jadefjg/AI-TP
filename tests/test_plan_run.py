from backend.services.plan_run_service import resolve_functional_case_ids
from tests.project_helpers import create_test_project


def test_resolve_suite_case_ids(db, admin_headers, client):
    project_id = create_test_project(client, admin_headers, name="plan-run")
    case = client.post(
        f"/projects/{project_id}/functional-cases",
        headers=admin_headers,
        json={"title": "c1", "steps": ["s"]},
    ).json()
    suite = client.post(
        f"/projects/{project_id}/test-suites",
        headers=admin_headers,
        json={"name": "suite-a"},
    ).json()
    client.put(
        f"/projects/{project_id}/test-suites/{suite['id']}/cases",
        headers=admin_headers,
        json={"case_ids": [case["id"]]},
    )
    ids = resolve_functional_case_ids(db, project_id=project_id, suite_id=suite["id"])
    assert ids == [case["id"]]


def test_start_run_functional_kind(client, db, admin_headers):
    project_id = create_test_project(client, admin_headers, name="fn-kind")
    case = client.post(
        f"/projects/{project_id}/functional-cases",
        headers=admin_headers,
        json={"title": "login", "steps": ["open", "submit"]},
    ).json()
    suite = client.post(
        f"/projects/{project_id}/test-suites",
        headers=admin_headers,
        json={"name": "s1"},
    ).json()
    client.put(
        f"/projects/{project_id}/test-suites/{suite['id']}/cases",
        headers=admin_headers,
        json={"case_ids": [case["id"]]},
    )
    res = client.post(
        f"/projects/{project_id}/runs",
        headers=admin_headers,
        json={"suite_id": suite["id"]},
    )
    assert res.status_code == 202
    body = res.json()
    kinds = [i["kind"] for i in body["items"]]
    assert "functional" in kinds
    assert "unit" not in kinds

    from backend.models.entities import ExecutionJob
    from backend.services.job_queue import process_job

    job = db.query(ExecutionJob).filter(ExecutionJob.run_id == body["id"]).one()
    process_job(db, job.id)
    detail = client.get(f"/runs/{body['id']}", headers=admin_headers).json()
    fn_item = next(i for i in detail["items"] if i["kind"] == "functional")
    assert fn_item["status"] in {"passed", "failed", "skipped"}
