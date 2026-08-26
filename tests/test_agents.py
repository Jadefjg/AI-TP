from types import SimpleNamespace

from backend.services.agents import get_agent, list_agent_manifests, ui_agent
from backend.services.agents.metrics import agent_quality_stats
from backend.services.agents.security_agent import extract_security_strategies
from backend.services.ai.gateway import complete, gateway_stats


def test_agent_registry_has_five_specialists():
    keys = [item.key for item in list_agent_manifests()]
    assert keys == ["requirement", "ui", "interface", "perf", "security"]
    assert get_agent("ui") is ui_agent
    try:
        get_agent("unknown")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "unknown agent" in str(exc)


def test_ui_agent_preview_and_empty_execute_skipped():
    case = SimpleNamespace(
        title="登录",
        steps=["打开 /login", "输入用户名", "点击登录"],
        expected="控制台",
        ui_script=None,
    )
    from backend.services.engines.ui_playwright import steps_from_functional_case

    doc = steps_from_functional_case(case, force_rebuild=True)
    preview = ui_agent.preview(doc, base_url="http://127.0.0.1:8088")
    assert preview["valid"] is True
    assert preview["agent"] == "ui"

    empty = ui_agent.execute(
        {"version": "1", "base_url": "http://127.0.0.1:8088", "steps": []},
        base_url="http://127.0.0.1:8088",
    )
    assert empty["status"] == "skipped"
    assert empty["agent"] == "ui"


def test_extract_security_strategies_shapes():
    assert extract_security_strategies([{"vul_type": "xss"}]) == [{"vul_type": "xss"}]
    assert extract_security_strategies({"strategies": [{"vul_type": "sqli"}]}) == [{"vul_type": "sqli"}]
    assert extract_security_strategies({"vul_type": "csrf", "test_payload": "<a>"}) == [
        {"vul_type": "csrf", "test_payload": "<a>"}
    ]
    assert extract_security_strategies("noop") == []


def test_gateway_stats_increment_on_stub_complete():
    import asyncio

    before = int(gateway_stats().get("calls") or 0)
    result = asyncio.run(
        complete(
            system_prompt="you are a tester",
            user_prompt="return {}",
            profile="bulk",
            json_mode=True,
        )
    )
    after = gateway_stats()
    assert int(after.get("calls") or 0) == before + 1
    assert result.model


def test_agent_quality_stats_empty(db):
    stats = agent_quality_stats(db)
    assert set(stats["coverage"]) == {"requirement", "ui", "interface", "perf", "security"}
    assert stats["security_false_positive"]["reviewed"] == 0
    assert stats["security_false_positive"]["rate"] == 0.0


def test_ai_agents_catalog_endpoint(client, admin_headers):
    denied = client.get("/ai/agents")
    assert denied.status_code == 401
    res = client.get("/ai/agents", headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    keys = [row["key"] for row in body["agents"]]
    assert keys == ["requirement", "ui", "interface", "perf", "security"]
    assert "calls" in body["gateway"]
    assert "coverage" in body["quality"]
    assert "security_false_positive" in body["quality"]
