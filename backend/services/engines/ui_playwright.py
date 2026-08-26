from __future__ import annotations

import base64
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.core.defaults import DEFAULT_UI_BASE_URL

GENERIC_SELECTORS = {
    "input, textarea",
    "button, a, [role='button']",
    "button, a",
    "body",
    "input",
    "button",
    "a",
}

_GOAL_PREFIXES = (
    "打开",
    "进入",
    "访问",
    "跳转",
    "点击",
    "单击",
    "按下",
    "选择",
    "提交",
    "确认",
    "保存",
    "输入",
    "填写",
    "填入",
    "录入",
    "悬停",
    "等待",
    "goto",
    "open",
    "click",
    "fill",
    "type",
    "hover",
    "press",
)


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
                "goal": extract_goal_phrase(step),
            }
        )
    return {"valid": True, "steps": preview, "base_url": doc.get("base_url")}


def _absolute_url(base: str, url: Any) -> str:
    raw = str(url or "/")
    if raw.startswith("http"):
        return raw
    return base + (raw if raw.startswith("/") else f"/{raw}")


def is_generic_selector(selector: str | None) -> bool:
    value = str(selector or "").strip()
    if not value:
        return True
    return value in GENERIC_SELECTORS or "," in value


def extract_goal_phrase(step: dict[str, Any]) -> str:
    """Pull a human target (button name / field label) from a DSL step."""
    skip_names = {"open_home", "assert_expected", "assert_page"}
    for key in ("goal", "remark", "name"):
        text = str(step.get(key) or "").strip()
        if not text:
            continue
        if key == "name" and (text.startswith("step_") or text in skip_names):
            continue
        cleaned = text
        lower = cleaned.lower()
        for prefix in _GOAL_PREFIXES:
            if cleaned.startswith(prefix) or lower.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip(" ：:，,.-")
                break
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned.startswith("/") or cleaned.startswith("http"):
            continue
        if cleaned:
            return cleaned[:40]
    return ""


def _locator_count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:  # noqa: BLE001
        return 0


def _resolve_locator(page: Any, step: dict[str, Any]) -> tuple[Any | None, str]:
    """Map a DSL step to a Playwright locator; prefer role/label over generic CSS."""
    action = str(step.get("action") or "").lower()
    selector = str(step.get("selector") or "").strip()
    goal = extract_goal_phrase(step)

    if selector and not is_generic_selector(selector):
        loc = page.locator(selector)
        if _locator_count(loc) > 0:
            return loc.first, selector

    if action in {"click", "hover"} and goal:
        for role in ("button", "link", "menuitem", "tab", "checkbox"):
            loc = page.get_by_role(role, name=re.compile(re.escape(goal), re.I))
            if _locator_count(loc) > 0:
                return loc.first, f"role={role} name={goal}"
        loc = page.get_by_text(goal, exact=False)
        if _locator_count(loc) > 0:
            return loc.first, f"text={goal}"

    if action == "fill" and goal:
        for factory, label in (
            (lambda: page.get_by_label(re.compile(re.escape(goal), re.I)), f"label={goal}"),
            (lambda: page.get_by_placeholder(re.compile(re.escape(goal), re.I)), f"placeholder={goal}"),
            (lambda: page.get_by_role("textbox", name=re.compile(re.escape(goal), re.I)), f"role=textbox name={goal}"),
        ):
            loc = factory()
            if _locator_count(loc) > 0:
                return loc.first, label

    if action == "wait_for" and selector:
        return page.locator(selector), selector

    if action == "expect_text" and selector:
        return page.locator(selector), selector or "body"

    if selector:
        loc = page.locator(selector)
        if _locator_count(loc) > 0:
            return loc.first, selector
        return loc, selector
    return None, ""


def _observe_page(page: Any, *, embed_screenshot: bool) -> dict[str, Any]:
    observe: dict[str, Any] = {}
    try:
        observe["url"] = page.url
        observe["title"] = page.title()
    except Exception:  # noqa: BLE001
        pass
    try:
        observe["visible_text"] = (page.inner_text("body") or "")[:400]
    except Exception:  # noqa: BLE001
        pass
    try:
        aria = page.locator("body").aria_snapshot()
        if aria:
            observe["aria"] = str(aria)[:1200]
    except Exception:  # noqa: BLE001
        pass
    if embed_screenshot:
        data_url = _screenshot_data_url(page)
        if data_url:
            observe["screenshot_data_url"] = data_url
    return observe


def _screenshot_data_url(page: Any) -> str:
    try:
        raw = page.screenshot(type="jpeg", quality=42, full_page=False)
        if not raw:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:  # noqa: BLE001
        return ""


def _apply_playwright_step(page: Any, step: dict[str, Any], *, base: str) -> tuple[str, str]:
    """Run one GUI Agent action. Returns (stdout line, locator used)."""
    action = str(step.get("action") or "goto").lower()
    name = str(step.get("name") or "step")
    locator, used = _resolve_locator(page, step)

    if action == "goto":
        url = _absolute_url(base, step.get("url") or "/")
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return f"[ok] goto {url}", "goto"

    if action == "click":
        if locator is None:
            raise RuntimeError(f"no locator for click ({name})")
        locator.click(timeout=15_000)
        return f"[ok] click {name} via {used}", used

    if action == "fill":
        if locator is None:
            raise RuntimeError(f"no locator for fill ({name})")
        locator.fill(str(step.get("value") or ""), timeout=15_000)
        return f"[ok] fill {name} via {used}", used

    if action == "hover":
        if locator is None:
            raise RuntimeError(f"no locator for hover ({name})")
        locator.hover(timeout=15_000)
        return f"[ok] hover {name} via {used}", used

    if action == "press":
        page.keyboard.press(str(step.get("value") or "Enter"))
        return f"[ok] press {name}", "keyboard"

    if action == "wait_for":
        target = locator if locator is not None else page.locator(str(step.get("selector")))
        target.wait_for(timeout=int(step.get("value") or 15_000))
        return f"[ok] wait_for {name}", used

    if action == "expect_text":
        target = locator if locator is not None else page.locator("body")
        text = target.inner_text()
        expected = str(step.get("value") or "")
        assert expected in text, f"expected {expected!r} in {text!r}"
        return f"[ok] expect_text {name}", used or "body"

    if action == "wait":
        page.wait_for_timeout(int(step.get("value") or step.get("ms") or 500))
        return f"[ok] wait {name}", "timeout"

    if action == "screenshot":
        return f"[ok] screenshot {name}", "screenshot"

    return f"[skip] unknown action {action}", ""


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
        goal = extract_goal_phrase(step)
        lines.append(f"        # {name}")
        if action == "goto":
            lines.append(f"        page.goto({_absolute_url(base, step.get('url') or '/')!r})")
        elif action == "click":
            if goal:
                lines.append(f"        page.get_by_role('button', name={goal!r}).click()")
            else:
                lines.append(f"        page.click({step.get('selector')!r})")
        elif action == "fill":
            if goal:
                lines.append(
                    f"        page.get_by_label({goal!r}).fill({str(step.get('value') or '')!r})"
                )
            else:
                lines.append(f"        page.fill({step.get('selector')!r}, {str(step.get('value') or '')!r})")
        elif action == "hover":
            lines.append(f"        page.hover({step.get('selector')!r})")
        elif action == "press":
            lines.append(f"        page.keyboard.press({str(step.get('value') or 'Enter')!r})")
        elif action == "wait_for":
            lines.append(f"        page.wait_for_selector({step.get('selector')!r})")
        elif action == "expect_text":
            lines.append(
                f"        assert {str(step.get('value') or '')!r} in page.locator({step.get('selector')!r}).inner_text()"
            )
        elif action == "wait":
            ms = int(step.get("value") or step.get("ms") or 500)
            lines.append(f"        page.wait_for_timeout({ms})")
        elif action == "screenshot":
            lines.append(f"        page.screenshot(path={str(step.get('value') or 'step.png')!r})")
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


def _playwright_import_error() -> dict[str, Any]:
    return {
        "status": "skipped",
        "detail": {"reason": "playwright not installed; pip install playwright && playwright install chromium"},
        "stdout": "",
        "stderr": "ImportError: playwright",
    }


def chromium_ready() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright not installed; pip install playwright && playwright install chromium"
    path: Path | None = None
    try:
        with sync_playwright() as p:
            path = Path(getattr(p.chromium, "executable_path", "") or "")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    if path is None or not path.exists():
        return False, f"chromium not installed ({path}); run: playwright install chromium"
    return True, ""


def execute_ui_script(ui_script: dict | list | None, *, base_url: str = DEFAULT_UI_BASE_URL) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _playwright_import_error()

    doc = _normalize_script(ui_script, base_url, force_base_url=True)
    if not doc.get("steps"):
        return {
            "status": "skipped",
            "detail": {"reason": "empty ui_script steps"},
            "stdout": "",
            "stderr": "",
        }

    ready, reason = chromium_ready()
    if not ready:
        return {"status": "skipped", "detail": {"reason": reason}, "stdout": "", "stderr": reason}

    code = steps_to_playwright_code(doc)
    stdout_lines: list[str] = []
    base = str(doc.get("base_url") or base_url).rstrip("/")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            script_path = Path(tmp) / "test_ui_flow.py"
            script_path.write_text(code, encoding="utf-8")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                base = str(doc.get("base_url") or base_url).rstrip("/")
                for step in doc.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    line, _used = _apply_playwright_step(page, step, base=base)
                    stdout_lines.append(line)
                browser.close()
        return {
            "status": "passed",
            "stdout": "\n".join(stdout_lines),
            "stderr": "",
            "detail": {"steps": len(doc.get("steps") or []), "base_url": base, "engine": "playwright"},
        }
    except Exception as exc:  # noqa: BLE001
        return _failure_payload(doc, stdout_lines, exc)


def execute_ui_agent(
    ui_script: dict | list | None,
    *,
    base_url: str = DEFAULT_UI_BASE_URL,
    embed_screenshots: bool = True,
) -> dict[str, Any]:
    """Run the full UI DSL as a Playwright GUI Agent (observe → act → record)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {**_playwright_import_error(), "traces": []}

    doc = _normalize_script(ui_script, base_url, force_base_url=True)
    steps = [s for s in (doc.get("steps") or []) if isinstance(s, dict)]
    if not steps:
        return {
            "status": "skipped",
            "detail": {"reason": "empty ui_script steps"},
            "stdout": "",
            "stderr": "",
            "traces": [],
        }

    ready, reason = chromium_ready()
    if not ready:
        return {
            "status": "skipped",
            "detail": {"reason": reason},
            "stdout": "",
            "stderr": reason,
            "traces": [],
        }

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path("data") / "ui-agent" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_lines: list[str] = []
    traces: list[dict[str, Any]] = []
    base = str(doc.get("base_url") or base_url).rstrip("/")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for idx, step in enumerate(steps):
                line, used = _apply_playwright_step(page, step, base=base)
                stdout_lines.append(line)
                observe = _observe_page(page, embed_screenshot=embed_screenshots)
                shot_name = f"step-{idx:02d}.jpg"
                shot_path = out_dir / shot_name
                try:
                    page.screenshot(path=str(shot_path), type="jpeg", quality=42, full_page=False)
                    observe["screenshot"] = str(shot_path)
                except Exception as shot_exc:  # noqa: BLE001
                    observe["screenshot_error"] = str(shot_exc)
                traces.append(
                    {
                        "index": idx,
                        "name": str(step.get("name") or f"step_{idx + 1}"),
                        "action": str(step.get("action") or "goto"),
                        "goal": extract_goal_phrase(step),
                        "locator": used,
                        "ok": True,
                        "stdout": line,
                        **observe,
                    }
                )
            browser.close()
        return {
            "status": "passed",
            "stdout": "\n".join(stdout_lines),
            "stderr": "",
            "traces": traces,
            "playwright_code": steps_to_playwright_code(doc),
            "detail": {
                "engine": "playwright-gui-agent",
                "mode": "observe-act",
                "steps": len(steps),
                "base_url": base,
                "trace_dir": str(out_dir),
            },
        }
    except Exception as exc:  # noqa: BLE001
        payload = _failure_payload(doc, stdout_lines, exc)
        if traces:
            traces[-1]["ok"] = False
            traces[-1]["error"] = str(exc)
        payload["traces"] = traces
        payload["detail"] = {
            **(payload.get("detail") if isinstance(payload.get("detail"), dict) else {}),
            "engine": "playwright-gui-agent",
            "mode": "observe-act",
            "trace_dir": str(out_dir),
        }
        return payload


def dispatch_or_execute_ui_agent(
    ui_script: dict | list | None,
    *,
    base_url: str = DEFAULT_UI_BASE_URL,
) -> dict[str, Any]:
    """Run locally when Chromium exists; otherwise enqueue to RQ worker (Docker)."""
    doc = _normalize_script(ui_script, base_url, force_base_url=True)
    steps = [s for s in (doc.get("steps") or []) if isinstance(s, dict)]
    if not steps:
        return {
            "status": "skipped",
            "detail": {"reason": "empty ui_script steps"},
            "stdout": "",
            "stderr": "",
            "traces": [],
        }
    ready, reason = chromium_ready()
    if ready:
        return execute_ui_agent(ui_script, base_url=base_url)
    remote = _try_rq_dispatch(ui_script, base_url=base_url)
    if remote is not None:
        return remote
    return {
        "status": "skipped",
        "detail": {
            "reason": (
                f"{reason}。API 进程无 Chromium 时，请确认 Worker 镜像为 worker-tools 且 JOB_QUEUE_BACKEND=rq。"
            )
        },
        "stdout": "",
        "stderr": reason,
        "traces": [],
    }


def _try_rq_dispatch(ui_script: dict | list | None, *, base_url: str) -> dict[str, Any] | None:
    from backend.core.config import get_settings

    settings = get_settings()
    if (settings.job_queue_backend or "").strip().lower() != "rq" or not (settings.redis_url or "").strip():
        return None
    try:
        import time

        from backend.services.job_queue_rq import get_rq_queue

        queue = get_rq_queue()
        timeout = min(int(settings.rq_job_timeout_sec or 600), 180)
        job = queue.enqueue(
            "backend.services.job_tasks.process_ui_agent_job",
            ui_script,
            base_url,
            job_timeout=timeout,
            result_ttl=max(int(settings.rq_result_ttl_sec or 3600), 600),
            failure_ttl=settings.rq_failure_ttl_sec,
            description="ui-gui-agent",
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw_status = job.get_status()
            status = str(getattr(raw_status, "value", raw_status) or "").lower()
            if status == "finished":
                result = getattr(job, "return_value", None)
                if result is None:
                    result = getattr(job, "result", None)
                if isinstance(result, dict):
                    detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
                    result["detail"] = {**detail, "dispatched": "rq"}
                    return result
                return {"status": "failed", "stderr": "invalid worker result", "traces": []}
            if status in {"failed", "stopped", "canceled"}:
                return {
                    "status": "failed",
                    "stderr": str(getattr(job, "exc_info", None) or status),
                    "detail": {"reason": f"GUI Agent worker {status}"},
                    "traces": [],
                }
            time.sleep(0.4)
        return {
            "status": "failed",
            "detail": {"reason": "GUI Agent worker timeout"},
            "stderr": "timeout",
            "traces": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "skipped",
            "detail": {"reason": f"无法下发 GUI Agent 到 Worker：{exc}"},
            "stderr": str(exc),
            "traces": [],
        }


def _failure_payload(doc: dict[str, Any], stdout_lines: list[str], exc: Exception) -> dict[str, Any]:
    err = str(exc)
    hint = ""
    if "ERR_CONNECTION_REFUSED" in err or "Connection refused" in err:
        hint = (
            f"无法连接 UI 目标 {doc.get('base_url')}。"
            "请确认被测前端已启动，或把 base_url 改成当前可访问地址。"
        )
    elif "Executable doesn't exist" in err or "chromium" in err.lower():
        hint = "Playwright Chromium 未安装。Worker 请使用 worker-tools 镜像，或执行 playwright install chromium。"
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
    if any(k in text for k in ("打开", "进入", "访问", "跳转", "goto", "open", "navigate")):
        path = "/"
        for token in text.replace("，", " ").replace(",", " ").split():
            if token.startswith("/") or token.startswith("http"):
                path = token
                break
        return {"name": name, "action": "goto", "url": path, "remark": text[:120]}
    if any(k in text for k in ("输入", "填写", "填入", "fill", "type", "录入")):
        remark = text[:120]
        rest = re.sub(r"^(输入|填写|填入|录入|fill|type)\s*", "", text, flags=re.I).strip()
        parts = rest.split()
        typed = parts[-1] if len(parts) >= 2 else ""
        return {
            "name": name,
            "action": "fill",
            "selector": "input, textarea",
            "value": typed,
            "remark": remark,
        }
    if any(k in text for k in ("悬停", "hover", "移入")):
        return {"name": name, "action": "hover", "selector": "button, a, [role='button']", "remark": text[:120]}
    if any(k in text for k in ("点击", "单击", "按下", "选择", "click", "press", "submit", "提交", "确认", "保存")):
        return {
            "name": name,
            "action": "click",
            "selector": "button, a, [role='button']",
            "value": "",
            "remark": text[:120],
        }
    if any(k in text for k in ("等待", "wait", "sleep", "稍后")):
        return {"name": name, "action": "wait", "value": 800, "remark": text[:120]}
    return {
        "name": name,
        "action": "expect_text",
        "selector": "body",
        "value": text[:120],
        "remark": text[:120],
    }
