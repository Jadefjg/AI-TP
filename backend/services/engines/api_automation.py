from __future__ import annotations

import time
from typing import Any

import httpx
import yaml

from backend.services.engines.dsl_parser import parse_dsl, substitute_vars
from backend.core.defaults import DEFAULT_BASE_URL


def validate_dsl_script(script_content: str, variables: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        parse_dsl(script_content, variables)
        return {"valid": True, "reason": "DSL 解析通过"}
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "reason": str(exc)}


def _check_assertions(resp: httpx.Response, assert_rules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not assert_rules:
        return errors
    expected_status = assert_rules.get("status")
    if expected_status is not None and resp.status_code != int(expected_status):
        errors.append(f"status 期望 {expected_status} 实际 {resp.status_code}")
    body_contains = assert_rules.get("body_contains")
    if body_contains and body_contains not in resp.text:
        errors.append(f"响应体未包含: {body_contains}")
    json_path = assert_rules.get("json_path")
    if json_path:
        try:
            data = resp.json()
            parts = str(json_path).split(".")
            cur: Any = data
            for part in parts:
                cur = cur[part]
            expected = assert_rules.get("json_equals")
            if expected is not None and cur != expected:
                errors.append(f"json_path {json_path} 期望 {expected} 实际 {cur}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"json 断言失败: {exc}")
    return errors


def list_dsl_steps(script_content: str, *, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    variables = {"base_url": base_url.rstrip("/")}
    validation = validate_dsl_script(script_content, variables)
    if not validation["valid"]:
        return {"valid": False, "reason": validation["reason"], "steps": []}
    try:
        doc = parse_dsl(script_content, variables)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "reason": str(exc), "steps": []}
    preview: list[dict[str, Any]] = []
    for idx, step in enumerate(doc.get("steps") or []):
        if not isinstance(step, dict):
            preview.append({"index": idx, "name": f"step_{idx + 1}", "valid": False})
            continue
        req = step.get("request") or {}
        preview.append(
            {
                "index": idx,
                "name": str(step.get("name") or f"step_{idx + 1}"),
                "method": str(req.get("method") or "GET").upper() if isinstance(req, dict) else "GET",
                "url": substitute_vars(str(req.get("url") or ""), variables) if isinstance(req, dict) else "",
                "valid": True,
            }
        )
    return {"valid": True, "reason": "ok", "steps": preview}


def execute_dsl_step(
    script_content: str,
    step_index: int,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    variables = {"base_url": base_url.rstrip("/")}
    try:
        doc = parse_dsl(script_content, variables)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "detail": {"reason": str(exc)},
            "stdout": "",
            "stderr": str(exc),
            "steps": [],
        }
    steps = doc.get("steps") or []
    if step_index < 0 or step_index >= len(steps):
        return {
            "status": "failed",
            "detail": {"reason": f"step_index 越界: {step_index}, 共 {len(steps)} 步"},
            "stdout": "",
            "stderr": "step_index out of range",
            "steps": [],
        }
    single = {"version": doc.get("version"), "steps": [steps[step_index]]}
    single_yaml = yaml.safe_dump(single, allow_unicode=True, sort_keys=False)
    result = execute_dsl_script(single_yaml, base_url=base_url, timeout_sec=timeout_sec)
    result["detail"] = {**(result.get("detail") or {}), "step_index": step_index}
    return result


def execute_dsl_script(
    script_content: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout_sec: float = 30.0,
) -> dict[str, Any]:
    variables = {"base_url": base_url.rstrip("/")}
    validation = validate_dsl_script(script_content, variables)
    if not validation["valid"]:
        return {
            "status": "failed",
            "detail": validation,
            "stdout": "",
            "stderr": validation["reason"],
            "steps": [],
        }

    try:
        doc = parse_dsl(script_content, variables)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "detail": {"reason": str(exc)},
            "stdout": "",
            "stderr": str(exc),
            "steps": [],
        }

    step_results: list[dict[str, Any]] = []
    lines: list[str] = []
    all_ok = True

    with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
        for idx, step in enumerate(doc.get("steps") or []):
            if not isinstance(step, dict):
                all_ok = False
                step_results.append({"index": idx, "status": "failed", "reason": "step 必须是对象"})
                continue
            name = str(step.get("name") or f"step_{idx + 1}")
            req = step.get("request") or {}
            if not isinstance(req, dict):
                all_ok = False
                step_results.append({"index": idx, "name": name, "status": "failed", "reason": "缺少 request"})
                continue
            method = str(req.get("method") or "GET").upper()
            url = substitute_vars(str(req.get("url") or ""), variables)
            headers = req.get("headers") or {}
            if not isinstance(headers, dict):
                headers = {}
            json_body = req.get("json")
            data_body = req.get("data")
            started = time.perf_counter()
            try:
                response = client.request(
                    method,
                    url,
                    headers={str(k): str(v) for k, v in headers.items()},
                    json=json_body,
                    data=data_body,
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                assert_rules = step.get("assert") or {}
                if not isinstance(assert_rules, dict):
                    assert_rules = {}
                errors = _check_assertions(response, assert_rules)
                ok = not errors
                if not ok:
                    all_ok = False
                step_results.append(
                    {
                        "index": idx,
                        "name": name,
                        "status": "passed" if ok else "failed",
                        "method": method,
                        "url": url,
                        "http_status": response.status_code,
                        "elapsed_ms": elapsed_ms,
                        "errors": errors,
                        "body_preview": (response.text or "")[:500],
                    }
                )
                lines.append(f"[{name}] {method} {url} -> {response.status_code} ({elapsed_ms}ms)")
            except Exception as exc:  # noqa: BLE001
                all_ok = False
                step_results.append(
                    {"index": idx, "name": name, "status": "failed", "method": method, "url": url, "errors": [str(exc)]}
                )
                lines.append(f"[{name}] FAILED: {exc}")

    stdout = "\n".join(lines)
    return {
        "status": "passed" if all_ok else "failed",
        "detail": {"step_count": len(step_results), "passed": sum(1 for s in step_results if s.get("status") == "passed")},
        "stdout": stdout,
        "stderr": "" if all_ok else "部分步骤断言失败",
        "steps": step_results,
    }
