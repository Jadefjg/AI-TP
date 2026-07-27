from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.services.ai.llm_client import LlmResult


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_workbench_session_and_apply(client: TestClient, admin_headers: dict):
    proj = client.post(
        "/projects",
        headers=admin_headers,
        json={"name": "WB", "code_root": "/tmp/wb"},
    ).json()

    sess = client.post(
        f"/projects/{proj['id']}/workbench/sessions",
        headers=admin_headers,
        json={"module_type": "functional_cases", "title": "用例会话"},
    )
    assert sess.status_code == 200, sess.text
    session_id = sess.json()["id"]

    fake_llm = LlmResult(
        content='已生成用例\n```json\n{"cases": [{"case_name": "登录", "operate_step": "打开页面;输入账号", "expect_result": "成功"}]}\n```',
        model="test",
        prompt_tokens=10,
        completion_tokens=20,
        latency_ms=5,
        used_fallback=False,
    )
    with patch(
        "backend.services.workbench_service.chat_completion",
        new_callable=AsyncMock,
        return_value=fake_llm,
    ):
        with patch(
            "backend.services.workbench_service.retrieve_context_chunks_async",
            new_callable=AsyncMock,
            return_value=[],
        ):
            chat = client.post(
                f"/projects/{proj['id']}/workbench/sessions/{session_id}/chat",
                headers=admin_headers,
                json={"message": "生成登录用例", "use_rag": False},
            )
    assert chat.status_code == 200, chat.text

    applied = client.post(
        f"/projects/{proj['id']}/workbench/sessions/{session_id}/apply",
        headers=admin_headers,
    )
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body.get("applied") is True
    assert body.get("count", 0) >= 1


def test_ci_webhook_triggers_run(client: TestClient, admin_headers: dict):
    proj = client.post(
        "/projects",
        headers=admin_headers,
        json={"name": "CI", "code_root": "/tmp/ci"},
    ).json()
    pid = proj["id"]

    cfg = client.get(f"/projects/{pid}/integrations/ci", headers=admin_headers)
    assert cfg.status_code == 200
    secret_res = client.put(
        f"/projects/{pid}/integrations/ci",
        headers=admin_headers,
        json={"default_branch": "main", "default_kinds": ["unit"]},
    )
    assert secret_res.status_code == 200

    from backend.db.session import SessionLocal
    from backend.services.ci_webhook_service import get_or_create_config

    db = SessionLocal()
    try:
        from backend.models.entities import Project

        project = db.query(Project).filter(Project.id == pid).one()
        row = get_or_create_config(db, project)
        token = row.secret
    finally:
        db.close()

    hook = client.post(
        f"/integrations/ci/{pid}/webhook",
        headers={"X-CI-Token": token},
        json={"ref": "refs/heads/main", "after": "abc123"},
    )
    assert hook.status_code == 200, hook.text
    data = hook.json()
    assert data.get("run_id") or data.get("duplicate")


def test_ui_automation_preview(client: TestClient, admin_headers: dict):
    proj = client.post(
        "/projects",
        headers=admin_headers,
        json={"name": "UI", "code_root": "/tmp/ui"},
    ).json()
    case = client.post(
        f"/projects/{proj['id']}/functional-cases",
        headers=admin_headers,
        json={"title": "UI Case", "steps": ["打开首页"]},
    ).json()

    preview = client.post(
        f"/projects/{proj['id']}/ui-automation/preview",
        headers=admin_headers,
        json={
            "ui_script": {
                "version": "1",
                "base_url": "http://127.0.0.1:5173",
                "steps": [{"name": "home", "action": "goto", "url": "/"}],
            },
        },
    )
    assert preview.status_code == 200
    assert preview.json()["valid"] is True

    gen = client.post(
        f"/projects/{proj['id']}/ui-automation/cases/{case['id']}/generate-from-case",
        headers=admin_headers,
    )
    assert gen.status_code == 200
    assert gen.json()["ui_script"]["steps"]
