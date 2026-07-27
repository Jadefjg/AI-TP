import json
from pathlib import Path
from unittest.mock import patch

from backend.services.engines.k6_metrics import parse_k6_ndjson_timeseries


def test_parse_k6_ndjson_timeseries(tmp_path: Path):
    path = tmp_path / "metrics.json"
    rows = [
        {"type": "Point", "data": {"time": "5s", "value": 0.12, "metric": "http_req_duration"}},
        {"type": "Point", "data": {"time": "5s", "value": 1, "metric": "http_reqs"}},
        {"type": "Point", "data": {"time": "10s", "value": 0.2, "metric": "http_req_duration"}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    series = parse_k6_ndjson_timeseries(path, bucket_sec=5)
    assert len(series) >= 1
    assert "rt_ms" in series[0]
    assert series[0]["rt_ms"] == 120.0


def test_parse_k6_ndjson_skips_oversized_file(tmp_path: Path):
    path = tmp_path / "huge.metrics.json"
    path.write_text('{"type":"Point"}\n', encoding="utf-8")
    with patch("backend.services.engines.k6_metrics._MAX_K6_NDJSON_BYTES", 1):
        assert parse_k6_ndjson_timeseries(path) == []
