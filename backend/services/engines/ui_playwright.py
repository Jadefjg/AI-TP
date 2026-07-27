from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


from backend.core.defaults import DEFAULT_UI_BASE_URL


def _normalize_script(
    ui_script: dict | list | None,
    base_url: str,
    *,
    force_base_url: bool = False,
) -> dict[str, Any]:
    resolved = (base_url or DEFAULT_UI_BASE_URL).rstrip("/")
    if isinstance(ui_script, list):
        return {"version": "1", "base_url": resolved, "steps": ui_script}
    if isinstance(ui_script, dict):
        doc = dict(ui_script)
        doc.setdefault("version", "1")
        doc.setdefault("steps", [])
        if force_base_url or not str(doc.get("base_url") or "").strip():
            doc["base_url"] = resolved
        else:
            doc["base_url"] = str(doc.get("base_url")).rstrip("/")
        return doc
    return {"version": "1", "base_url": resolved, "steps": []}


def list_ui_steps(ui_script: dict | list | None, *, base_url: str = DEFAULT_UI_BASE_URL) -> dict[str, Any]:
    doc = _normalize_script(ui_script, base_url.rstrip("/"))
    steps = doc.get("steps") or []
    preview = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        preview.append(
            {
                "index": idx,
                "name": str(step.get("name") or f"step_{idx + 1}"),
                "action": str(step.get("action") or "goto"),
                "selector": step.get("selector"),
                "url": step.get("url"),
            }
        )
    return {"valid": True, "steps": preview, "base_url": doc.get("base_url")}


def steps_to_playwright_code(doc: dict[str, Any]) -> str:
    base = str(doc.get("base_url") or DEFAULT_UI_BASE_URL).rstrip("/")
    lines = [
        "from playwright.sync_api import sync_playwright",
        "",
        "def run():",
        "    with sync_playwright() as p:",
        "        browser = p.chromium.launch(headless=True)",
        "        page = browser.new_page()",
    ]
    for step in doc.get("steps") or []:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "goto").lower()
        name = str(step.get("name") or "step")
        lines.append(f"        # {name}")
        if action == "goto":
            url = step.get("url") or "/"
            if not str(url).startswith("http"):
                url = base + (url if str(url).startswith("/") else f"/{url}")
            lines.append(f"        page.goto({url!r})")
        elif action == "click":
            lines.append(f"        page.click({step.get('selector')!r})")
        elif action == "fill":
            lines.append(f"        page.fill({step.get('selector')!r}, {str(step.get('value') or '')!r})")
        elif action == "expect_text":
            lines.append(
                f"        assert {str(step.get('value') or '')!r} in page.locator({step.get('selector')!r}).inner_text()"
            )
        elif action == "wait":
            ms = int(step.get("value") or step.get("ms") or 500)
            lines.append(f"        page.wait_for_timeout({ms})")
    lines.extend(["        browser.close()", "", "if __name__ == '__main__':", "    run()"])
    return "\n".join(lines)


def execute_ui_step(
    ui_script: dict | list | None,
    step_index: int,
    *,
    base_url: str = DEFAULT_UI_BASE_URL,
) -> dict[str, Any]:
    """Execute UI steps 0..step_index so the page has prior navigation context.

    Isolating a single mid-script step (e.g. expect_text) without goto would
    always fail on a blank page; prefix replay matches step-debug UX.
    """
    # Request base_url wins over stale DSL defaults (e.g. dead :5173 while UI is on :5174).
    doc = _normalize_script(ui_script, base_url, force_base_url=True)
    steps = doc.get("steps") or []
    if step_index < 0 or step_index >= len(steps):
        return {"status": "failed", "stderr": "step_index out of range", "stdout": ""}
    prefix = {**doc, "steps": steps[: step_index + 1]}
    result = execute_ui_script(prefix, base_url=str(doc.get("base_url") or base_url))
    result["detail"] = {
        **(result.get("detail") if isinstance(result.get("detail"), dict) else {}),
        "step_index": step_index,
        "steps_executed": step_index + 1,
        "base_url": doc.get("base_url"),
        "focused_step": steps[step_index] if isinstance(steps[step_index], dict) else None,
    }
    return result


def execute_ui_script(ui_script: dict | list | None, *, base_url: str = DEFAULT_UI_BASE_URL) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "skipped",
            "detail": {"reason": "playwright not installed; pip install playwright && playwright install chromium"},
            "stdout": "",
            "stderr": "ImportError: playwright",
        }

    doc = _normalize_script(ui_script, base_url, force_base_url=True)
    if not doc.get("steps"):
        return {
            "status": "skipped",
            "detail": {"reason": "empty ui_script steps"},
            "stdout": "",
            "stderr": "",
        }

    code = steps_to_playwright_code(doc)
    stdout_lines: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "test_ui_flow.py"
            script_path.write_text(code, encoding="utf-8")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                base = str(doc.get("base_url") or base_url).rstrip("/")
                for idx, step in enumerate(doc.get("steps") or []):
                    if not isinstance(step, dict):
                        continue
                    action = str(step.get("action") or "goto").lower()
                    name = str(step.get("name") or f"step_{idx + 1}")
                    if action == "goto":
                        url = step.get("url") or "/"
                        if not str(url).startswith("http"):
                            url = base + (url if str(url).startswith("/") else f"/{url}")
                        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        stdout_lines.append(f"[ok] goto {url}")
                    elif action == "click":
                        page.click(str(step.get("selector")))
                        stdout_lines.append(f"[ok] click {name}")
                    elif action == "fill":
                        page.fill(str(step.get("selector")), str(step.get("value") or ""))
                        stdout_lines.append(f"[ok] fill {name}")
                    elif action == "expect_text":
                        text = page.locator(str(step.get("selector"))).inner_text()
                        expected = str(step.get("value") or "")
                        assert expected in text, f"expected {expected!r} in {text!r}"
                        stdout_lines.append(f"[ok] expect_text {name}")
                    elif action == "wait":
                        page.wait_for_timeout(int(step.get("value") or step.get("ms") or 500))
                        stdout_lines.append(f"[ok] wait {name}")
                browser.close()
        return {
            "status": "passed",
            "stdout": "\n".join(stdout_lines),
            "stderr": "",
            "detail": {"steps": len(doc.get("steps") or []), "base_url": base},
        }
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        hint = ""
        if "ERR_CONNECTION_REFUSED" in err or "Connection refused" in err:
            hint = (
                f"无法连接 UI 目标 {doc.get('base_url')}。"
                "请确认前端已启动，或在脚本中把 base_url 改成当前页面地址（例如 http://127.0.0.1:5174）。"
            )
        return {
            "status": "failed",
            "stdout": "\n".join(stdout_lines),
            "stderr": err,
            "detail": {
                "error": err,
                "reason": hint or err,
                "base_url": doc.get("base_url"),
            },
        }


def steps_from_functional_case(case, *, force_rebuild: bool = False) -> dict[str, Any]:
    """Build a Playwright UI DSL from a functional case.

    When force_rebuild is False and case.ui_script already exists, return it.
    Generate-from-case should pass force_rebuild=True.
    """
    if not force_rebuild and isinstance(case.ui_script, (dict, list)) and case.ui_script:
        return _normalize_script(case.ui_script, DEFAULT_UI_BASE_URL)

    steps: list[dict[str, Any]] = [
        {"name": "open_home", "action": "goto", "url": "/", "remark": "打开应用首页"},
    ]
    raw_steps = case.steps or []
    for idx, item in enumerate(raw_steps):
        text = item if isinstance(item, str) else str(item or "")
        text = text.strip()
        if not text:
            continue
        steps.append(_infer_ui_step_from_text(text, idx + 1))

    if case.expected:
        expected = str(case.expected).strip()
        if expected:
            steps.append(
                {
                    "name": "assert_expected",
                    "action": "expect_text",
                    "selector": "body",
                    "value": expected[:200],
                    "remark": "校验期望结果",
                }
            )

    if len(steps) == 1:
        # Only home — add a placeholder expect so generate is never empty.
        title = str(getattr(case, "title", "") or "用例").strip() or "用例"
        steps.append(
            {
                "name": "assert_page",
                "action": "expect_text",
                "selector": "body",
                "value": title[:80],
                "remark": "用例无操作步骤，使用标题做弱断言",
            }
        )

    return {"version": "1", "base_url": DEFAULT_UI_BASE_URL, "steps": steps}


def _infer_ui_step_from_text(text: str, index: int) -> dict[str, Any]:
    lower = text.lower()
    name = f"step_{index}"
    # Navigation cues
    if any(k in text for k in ("打开", "进入", "访问", "跳转", "goto", "open", "navigate")):
        path = "/"
        for token in text.replace("，", " ").replace(",", " ").split():
            if token.startswith("/") or token.startswith("http"):
                path = token
                break
        return {"name": name, "action": "goto", "url": path, "remark": text[:120]}
    # Input / fill
    if any(k in text for k in ("输入", "填写", "填入", "fill", "type", "录入")):
        return {
            "name": name,
            "action": "fill",
            "selector": "input, textarea",
            "value": text[:80],
            "remark": text[:120],
        }
    # Click
    if any(k in text for k in ("点击", "单击", "按下", "选择", "click", "press", "submit", "提交", "确认", "保存")):
        return {
            "name": name,
            "action": "click",
            "selector": "button, a, [role='button']",
            "remark": text[:120],
        }
    # Wait
    if any(k in text for k in ("等待", "wait", "sleep", "稍后")):
        return {"name": name, "action": "wait", "value": 800, "remark": text[:120]}
    # Default: text assertion against body
    return {
        "name": name,
        "action": "expect_text",
        "selector": "body",
        "value": text[:120],
        "remark": text[:120],
    }

