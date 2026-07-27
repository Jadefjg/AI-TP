from backend.services.engines.k6_metrics import parse_k6_text_summary


def test_parse_k6_text_summary_basic():
    stdout = """
    http_req_duration..............: avg=120ms min=50ms med=100ms max=500ms p(95)=250ms
    http_reqs......................: 1200 20.5/s
    http_req_failed................: 1.50% 18 out of 1200
    iterations.....................: 1200
    """
    summary = parse_k6_text_summary(stdout)
    assert summary["tps"] == 20.5
    assert summary["error_rate"] == 1.5
    assert summary["http_reqs"] == 1200
