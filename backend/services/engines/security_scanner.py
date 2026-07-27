from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

SQL_ERROR_HINTS = (
    "sql syntax",
    "mysql",
    "sqlite",
    "postgresql",
    "ora-",
    "odbc",
    "syntax error",
    "unclosed quotation",
)
XSS_HINTS = ("<script", "alert(", "onerror=", "javascript:")


@dataclass
class ScanTarget:
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body_params: dict[str, str] = field(default_factory=dict)
    timeout_sec: float = 15.0


def _merge_url(base_url: str, query_params: dict[str, str]) -> str:
    parsed = urlparse(base_url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update(query_params)
    new_query = urlencode(existing)
    return urlunparse(parsed._replace(query=new_query))


def _analyze_response(
    *,
    vul_type: str,
    payload: str,
    response: httpx.Response,
    baseline_status: int,
    baseline_len: int,
) -> dict[str, Any]:
    text = (response.text or "").lower()
    signals: list[str] = []
    suspected = False

    if vul_type.lower().find("sql") >= 0:
        if any(h in text for h in SQL_ERROR_HINTS):
            signals.append("response_contains_sql_error")
            suspected = True
        if response.status_code >= 500 and baseline_status < 500:
            signals.append("server_error_after_sqli_payload")
            suspected = True

    if "xss" in vul_type.lower():
        if payload.lower() in (response.text or "").lower():
            signals.append("payload_reflected")
            suspected = True
        if any(h in text for h in XSS_HINTS):
            signals.append("xss_pattern_in_body")
            suspected = True

    if "越权" in vul_type or "auth" in vul_type.lower():
        if response.status_code in {200, 201, 204} and baseline_status in {401, 403}:
            signals.append("unauthorized_access_possible")
            suspected = True

    if abs(len(response.text or "") - baseline_len) > max(200, baseline_len * 0.5):
        signals.append("response_length_delta")
        if vul_type.lower().find("sql") >= 0:
            suspected = True

    return {
        "suspected": suspected,
        "signals": signals,
        "http_status": response.status_code,
        "body_preview": (response.text or "")[:600],
    }


def _send(
    client: httpx.Client,
    target: ScanTarget,
    *,
    param_name: str | None,
    param_value: str,
    inject: str,
) -> httpx.Response:
    method = target.method.upper()
    headers = dict(target.headers)
    query = dict(target.query_params)
    body = dict(target.body_params)

    if inject == "query" and param_name:
        query[param_name] = param_value
    elif inject == "body" and param_name:
        body[param_name] = param_value
    elif inject == "header" and param_name:
        headers[param_name] = param_value

    url = _merge_url(target.url, query)
    if method in {"GET", "HEAD", "DELETE"}:
        return client.request(method, url, headers=headers)
    return client.request(method, url, headers=headers, data=body)


def execute_security_scan(
    strategies: list[dict[str, Any]],
    target: ScanTarget,
    *,
    max_payloads_per_type: int = 8,
    delay_ms: int = 50,
) -> dict[str, Any]:
    if not strategies:
        return {
            "status": "skipped",
            "detail": {"reason": "无可用扫描策略，请先生成安全测试策略产物"},
            "findings": [],
            "stdout": "",
            "stderr": "no strategies",
        }

    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    tested = 0

    with httpx.Client(timeout=target.timeout_sec, follow_redirects=False) as client:
        try:
            baseline = _send(client, target, param_name=None, param_value="", inject="query")
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "skipped",
                "detail": {
                    "reason": f"基线请求失败（目标不可达或服务未启动）: {exc}",
                    "target_url": target.url,
                },
                "findings": [],
                "stdout": "",
                "stderr": str(exc),
            }
        baseline_status = baseline.status_code
        baseline_len = len(baseline.text or "")

        for item in strategies:
            if not isinstance(item, dict):
                continue
            vul_type = str(item.get("vul_type") or "unknown")
            risk_level = str(item.get("risk_level") or "中")
            payloads = item.get("test_payload") or []
            if not isinstance(payloads, list):
                continue
            scan_strategy = str(item.get("scan_strategy") or "")
            inject = "query"
            if "header" in scan_strategy.lower():
                inject = "header"
            elif "body" in scan_strategy.lower() or "post" in scan_strategy.lower():
                inject = "body"

            param_names = list(target.query_params.keys() or target.body_params.keys())
            if not param_names:
                param_names = ["q"]

            effective_inject = inject
            if target.method.upper() in {"POST", "PUT", "PATCH"} and target.body_params:
                effective_inject = "body"
            elif target.query_params:
                effective_inject = "query"

            for payload in payloads[:max_payloads_per_type]:
                if not isinstance(payload, str):
                    continue
                for param_name in param_names[:3]:
                    tested += 1
                    try:
                        resp = _send(
                            client,
                            target,
                            param_name=param_name,
                            param_value=payload,
                            inject=effective_inject,
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(str(exc))
                        continue

                    analysis = _analyze_response(
                        vul_type=vul_type,
                        payload=payload,
                        response=resp,
                        baseline_status=baseline_status,
                        baseline_len=baseline_len,
                    )
                    if analysis["suspected"]:
                        findings.append(
                            {
                                "vul_type": vul_type,
                                "risk_level": risk_level,
                                "param": param_name,
                                "payload": payload,
                                "inject": inject,
                                "signals": analysis["signals"],
                                "http_status": analysis["http_status"],
                                "body_preview": analysis["body_preview"],
                                "scan_strategy": scan_strategy,
                                "test_payload": [payload],
                            }
                        )
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)

    # Scan execution succeeded. Findings mean risks discovered, not scanner crash.
    status = "completed" if findings else "passed"
    strategy_count = sum(1 for item in strategies if isinstance(item, dict))
    return {
        "status": status,
        "detail": {
            "tested_requests": tested,
            "finding_count": len(findings),
            "baseline_status": baseline_status,
            "baseline_body_len": baseline_len,
            "strategy_count": strategy_count,
            "errors": errors[:20],
        },
        "findings": findings,
        "stdout": f"security scan finished: {len(findings)} suspected issue(s)",
        "stderr": "",
    }


def normalize_security_job_status(result: dict[str, Any], findings: list[Any]) -> str:
    """Map engine result → persisted job status.

    - skipped: target unavailable / no strategy (resilient skip)
    - completed: scan finished and reported findings
    - passed: scan finished with no findings
    - failed: unexpected hard failure
    """
    raw = str(result.get("status") or "")
    if raw == "skipped":
        return "skipped"
    if findings:
        return "completed"
    if raw in {"passed", "completed"}:
        return "passed"
    if raw == "failed":
        detail = result.get("detail") if isinstance(result.get("detail"), dict) else {}
        if detail.get("reason"):
            return "skipped"
        return "failed"
    return "passed"

