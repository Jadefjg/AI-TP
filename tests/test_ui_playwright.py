from types import SimpleNamespace

from backend.services.engines.ui_playwright import (
    execute_ui_agent,
    extract_goal_phrase,
    is_generic_selector,
    list_ui_steps,
    steps_from_functional_case,
    steps_to_playwright_code,
)


def test_infer_and_preview_playwright_steps():
    case = SimpleNamespace(
        title="登录",
        steps=["打开 /login", "输入用户名", "点击登录", "悬停菜单"],
        expected="控制台",
        ui_script=None,
    )
    doc = steps_from_functional_case(case, force_rebuild=True)
    actions = [row["action"] for row in doc["steps"]]
    assert actions[0] == "goto"
    assert "fill" in actions
    assert "click" in actions
    assert "hover" in actions
    assert "expect_text" in actions

    click = next(row for row in doc["steps"] if row["action"] == "click")
    assert extract_goal_phrase(click) == "登录"
    assert is_generic_selector(click["selector"]) is True

    preview = list_ui_steps(doc, base_url="http://127.0.0.1:8088")
    assert preview["valid"] is True
    assert preview["base_url"] == doc["base_url"]
    assert len(preview["steps"]) == len(doc["steps"])
    assert any(row.get("goal") == "登录" for row in preview["steps"])

    code = steps_to_playwright_code(doc)
    assert "sync_playwright" in code
    assert "page.goto" in code
    assert "get_by_role" in code


def test_extract_goal_phrase_and_generic_selector():
    assert extract_goal_phrase({"action": "click", "remark": "点击登录"}) == "登录"
    assert extract_goal_phrase({"action": "fill", "remark": "输入用户名"}) == "用户名"
    assert extract_goal_phrase({"name": "step_1", "selector": "body"}) == ""
    assert is_generic_selector("button, a, [role='button']") is True
    assert is_generic_selector("#login-btn") is False


def test_gui_agent_skips_empty_script():
    result = execute_ui_agent({"version": "1", "base_url": "http://127.0.0.1:8088", "steps": []})
    assert result["status"] == "skipped"
    assert result["traces"] == []
