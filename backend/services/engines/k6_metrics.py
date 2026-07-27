from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _parse_duration_value(raw: str) -> float:
    raw = raw.strip().lower()
    if raw.endswith("ms"):
        return float(raw[:-2])
    if raw.endswith("s"):
        return float(raw[:-1]) * 1000
    if raw.endswith("m"):
        return float(raw[:-1]) * 60_000
    return float(raw)


def parse_k6_text_summary(stdout: str, stderr: str = "") -> dict[str, Any]:
    text = f"{stdout}\n{stderr}"
    summary: dict[str, Any] = {
        "avg_rt_ms": None,
        "p95_rt_ms": None,
        "tps": None,
        "error_rate": None,
        "http_reqs": None,
        "iterations": None,
    }

    dur_match = re.search(
        r"http_req_duration[^:]*:\s*avg=([\d.]+)(\w+)?.*?p\(95\)=([\d.]+)(\w+)?",
        text,
        re.DOTALL,
    )
    if dur_match:
        summary["avg_rt_ms"] = _parse_duration_value(dur_match.group(1) + (dur_match.group(2) or "ms"))
        summary["p95_rt_ms"] = _parse_duration_value(dur_match.group(3) + (dur_match.group(4) or "ms"))

    reqs_match = re.search(r"http_reqs[^:]*:\s*(\d+)\s+([\d.]+)/s", text)
    if reqs_match:
        summary["http_reqs"] = int(reqs_match.group(1))
        summary["tps"] = float(reqs_match.group(2))

    fail_match = re.search(r"http_req_failed[^:]*:\s*([\d.]+)%", text)
    if fail_match:
        summary["error_rate"] = float(fail_match.group(1))

    iter_match = re.search(r"iterations[^:]*:\s*(\d+)", text)
    if iter_match:
        summary["iterations"] = int(iter_match.group(1))

    return summary


def parse_k6_summary_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    metrics = data.get("metrics") or data
    if not isinstance(metrics, dict):
        return None

    def _metric_value(name: str, field: str = "avg") -> float | None:
        block = metrics.get(name)
        if not isinstance(block, dict):
            return None
        values = block.get("values") if isinstance(block.get("values"), dict) else block
        if not isinstance(values, dict):
            return None
        val = values.get(field)
        return float(val) if val is not None else None

    avg_rt = _metric_value("http_req_duration", "avg")
    p95_rt = _metric_value("http_req_duration", "p(95)")
    tps = _metric_value("http_reqs", "rate")
    err = _metric_value("http_req_failed", "rate")
    return {
        "avg_rt_ms": avg_rt * 1000 if avg_rt is not None and avg_rt < 1000 else avg_rt,
        "p95_rt_ms": p95_rt * 1000 if p95_rt is not None and p95_rt < 1000 else p95_rt,
        "tps": tps,
        "error_rate": err * 100 if err is not None and err <= 1 else err,
        "http_reqs": int(_metric_value("http_reqs", "count") or 0) or None,
        "iterations": int(_metric_value("iterations", "count") or 0) or None,
        "raw_metrics": list(metrics.keys())[:20],
    }


# k6 `--out json=` can grow to multi-GB NDJSON; never load the whole file into memory.
_MAX_K6_NDJSON_BYTES = 64 * 1024 * 1024


def parse_k6_ndjson_timeseries(path: Path, *, bucket_sec: float = 5.0) -> list[dict[str, Any]]:
    """Parse k6 `--out json=file` NDJSON points into aggregated time buckets.

    Streams line-by-line and keeps only running aggregates per bucket so large
    metrics files cannot exhaust memory / freeze the API process (GIL).
    """
    if not path.is_file():
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= 0:
        return []
    if size > _MAX_K6_NDJSON_BYTES:
        # Prefer summary/synthetic series over hanging the whole API on huge files.
        return []

    buckets: dict[int, dict[str, Any]] = {}
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("type") != "Point":
                    continue
                data = row.get("data")
                if not isinstance(data, dict):
                    continue
                metric = str(data.get("metric") or "")
                if metric not in {"http_req_duration", "http_reqs", "http_req_failed"}:
                    continue
                t_raw = data.get("time")
                value = data.get("value")
                if value is None:
                    continue
                try:
                    if isinstance(t_raw, (int, float)):
                        t_sec = float(t_raw)
                    else:
                        t_sec = float(str(t_raw).replace("s", "").strip())
                except (TypeError, ValueError):
                    t_sec = 0.0
                bucket_key = int(t_sec // bucket_sec)
                slot = buckets.setdefault(
                    bucket_key,
                    {
                        "t_sec": round(bucket_key * bucket_sec, 1),
                        "rt_ms": 0.0,
                        "tps": 0.0,
                        "error_rate": 0.0,
                        "_rt_sum": 0.0,
                        "_rt_n": 0,
                        "_req": 0,
                        "_fail": 0,
                    },
                )
                val = float(value)
                if metric == "http_req_duration":
                    slot["_rt_sum"] += val * 1000 if val < 1000 else val
                    slot["_rt_n"] += 1
                elif metric == "http_reqs":
                    slot["_req"] += 1
                elif metric == "http_req_failed":
                    if val > 0:
                        slot["_fail"] += 1
    except OSError:
        return []

    series: list[dict[str, Any]] = []
    for key in sorted(buckets):
        slot = buckets[key]
        rt_n = int(slot.pop("_rt_n", 0) or 0)
        rt_sum = float(slot.pop("_rt_sum", 0.0) or 0.0)
        reqs = int(slot.pop("_req", 0) or 0)
        fails = int(slot.pop("_fail", 0) or 0)
        slot["rt_ms"] = round(rt_sum / rt_n, 2) if rt_n else 0.0
        slot["tps"] = round(reqs / bucket_sec, 3) if bucket_sec > 0 else 0.0
        slot["error_rate"] = round((fails / reqs) * 100, 3) if reqs else 0.0
        series.append(slot)
    return series


def build_monitor_time_series(
    summary: dict[str, Any],
    *,
    duration_sec: int = 60,
    points: int = 12,
) -> list[dict[str, Any]]:
    avg_rt = float(summary.get("avg_rt_ms") or summary.get("p95_rt_ms") or 0)
    tps = float(summary.get("tps") or 0)
    err = float(summary.get("error_rate") or 0)
    series: list[dict[str, Any]] = []
    for i in range(points):
        ratio = (i + 1) / points
        jitter = 0.85 + 0.3 * (i % 3) / 3
        series.append(
            {
                "t_sec": round(duration_sec * ratio, 1),
                "rt_ms": round(avg_rt * jitter, 2),
                "tps": round(tps * jitter, 3),
                "error_rate": round(err * (0.5 + 0.5 * ratio), 3),
            }
        )
    return series


def extract_k6_metrics(
    *,
    stdout: str,
    stderr: str = "",
    summary_path: Path | None = None,
    metrics_json_path: Path | None = None,
    duration_sec: int = 60,
) -> dict[str, Any]:
    summary = parse_k6_summary_json(summary_path) if summary_path else None
    if not summary:
        summary = parse_k6_text_summary(stdout, stderr)
    time_series = parse_k6_ndjson_timeseries(metrics_json_path) if metrics_json_path else []
    source = "k6_ndjson" if time_series else "synthetic_from_summary"
    if not time_series:
        time_series = build_monitor_time_series(summary, duration_sec=duration_sec)
    return {"summary": summary, "time_series": time_series, "time_series_source": source}
