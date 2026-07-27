from types import SimpleNamespace

from backend.services.security_report import build_security_scan_html, build_security_scan_pdf


def _job(**overrides):
    base = {
        "id": 3,
        "project_id": 1,
        "artifact_id": 16,
        "run_id": None,
        "target_url": "http://127.0.0.1:8002/system/health",
        "engine": "builtin",
        "status": "passed",
        "findings": [],
        "finding_reviews": {},
        "detail": {
            "tested_requests": 24,
            "finding_count": 0,
            "baseline_status": 200,
            "baseline_body_len": 16,
            "strategy_count": 3,
            "engines": ["builtin"],
        },
        "created_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_security_html_report_not_blank_when_no_findings():
    html = build_security_scan_html(_job(), project_name="呵呵")
    assert "安全扫描报告 #3" in html
    assert "执行结论" in html
    assert "扫描摘要" in html
    assert "探测请求数" in html
    assert "24" in html
    assert "未发现漏洞" in html
    assert "通过安全门禁" in html
    assert "（无漏洞项）" not in html


def test_security_html_report_shows_skip_reason():
    html = build_security_scan_html(
        _job(
            status="skipped",
            detail={"reason": "基线请求失败（目标不可达或服务未启动）: Connection refused"},
        ),
        project_name="呵呵",
    )
    assert "扫描已跳过" in html
    assert "Connection refused" in html


def test_security_html_report_lists_findings():
    html = build_security_scan_html(
        _job(
            status="completed",
            findings=[
                {
                    "vul_type": "SQL Injection",
                    "risk_level": "高",
                    "param": "q",
                    "scan_strategy": "query",
                    "http_status": 500,
                    "signals": ["status_spike"],
                    "test_payload": ["' OR 1=1"],
                    "body_preview": "error",
                }
            ],
            detail={"tested_requests": 8, "finding_count": 1, "baseline_status": 200},
        ),
        project_name="demo",
    )
    assert "漏洞明细（1）" in html
    assert "SQL Injection" in html
    assert "OR 1=1" in html
    assert "status_spike" in html


def test_security_pdf_report_builds_bytes():
    data = build_security_scan_pdf(_job(), project_name="呵呵")
    assert isinstance(data, (bytes, bytearray))
    assert data[:4] == b"%PDF"
