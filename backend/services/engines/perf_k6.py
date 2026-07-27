from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.services.engines.k6_metrics import extract_k6_metrics
from backend.core.defaults import DEFAULT_BASE_URL


def plan_to_k6_script(
    plan: dict[str, Any],
    *,
    default_base_url: str = DEFAULT_BASE_URL,
    execution_segment: tuple[int, int] | None = None,
) -> str:
    press_mode = str(plan.get("press_mode") or "step")
    start_c = int(plan.get("start_concurrency") or 1)
    max_c = int(plan.get("max_concurrency") or start_c)
    step = int(plan.get("step") or 1)
    duration = int(plan.get("duration") or 60)
    warmup = int(plan.get("warmup") or 0)
    weights = plan.get("api_weight") or []
    if not isinstance(weights, list) or not weights:
        weights = [{"api_path": "/system/health", "weight": 100}]
    first = weights[0] if isinstance(weights[0], dict) else {"api_path": "/system/health"}
    path = str(first.get("api_path") or "/system/health")
    target_url = f"{default_base_url.rstrip('/')}{path}"

    wr = plan.get("warning_rule") if isinstance(plan.get("warning_rule"), dict) else {}
    err_rate = float(wr.get("err_rate_limit", 1)) / 100.0
    rt_limit = int(wr.get("rt_limit", 500))

    segment_comment = ""
    if execution_segment:
        seg_idx, seg_total = execution_segment
        segment_comment = f"// k6 execution segment {seg_idx}/{seg_total}\n"

    return f"""import http from 'k6/http';
import {{ check }} from 'k6';

{segment_comment}// AI plan: mode={press_mode}, step={step}, warmup={warmup}s
export const options = {{
  stages: [
    {{ duration: '{warmup}s', target: {start_c} }},
    {{ duration: '{duration}s', target: {max_c} }},
  ],
  thresholds: {{
    http_req_failed: ['rate<{err_rate}'],
    http_req_duration: ['p(95)<{rt_limit}'],
  }},
}};

export default function () {{
  const res = http.get('{target_url}');
  check(res, {{ 'status is 200': (r) => r.status === 200 }});
}}
"""


def write_k6_script(project_id: int, artifact_id: int, script: str) -> Path:
    out_dir = Path("data") / "k6" / f"project-{project_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"artifact-{artifact_id}.js"
    path.write_text(script, encoding="utf-8")
    return path


def _segment_env(segment: tuple[int, int] | None) -> dict[str, str]:
    if not segment:
        return {}
    idx, total = segment
    return {
        "K6_EXECUTION_SEGMENT": f"{idx}/{total}",
        "K6_EXECUTION_SEGMENT_SEQUENCE": str(idx),
        "K6_EXECUTION_SEGMENT_SIZE": str(total),
    }


def dispatch_k6_run(
    script_path: Path,
    *,
    timeout_sec: int = 600,
    duration_sec: int = 60,
    execution_segment: tuple[int, int] | None = None,
) -> dict[str, Any]:
    k6_bin = shutil.which("k6")
    if not k6_bin:
        return {
            "status": "skipped",
            "detail": {"reason": "k6 未安装或不在 PATH"},
            "stdout": "",
            "stderr": "k6 not found",
            "script_path": str(script_path),
            "summary_metrics": None,
            "time_series": [],
        }
    summary_path = script_path.with_suffix(".summary.json")
    metrics_path = script_path.with_suffix(".metrics.json")
    cmd = [
        k6_bin,
        "run",
        str(script_path),
        "--summary-export",
        str(summary_path),
        "--out",
        f"json={metrics_path}",
    ]
    env = {**os.environ, **_segment_env(execution_segment)}
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "detail": {"reason": "k6 执行超时"},
            "stdout": "",
            "stderr": "timeout",
            "script_path": str(script_path),
            "summary_metrics": None,
            "time_series": [],
        }
    status = "passed" if proc.returncode == 0 else "failed"
    if proc.returncode == 127:
        status = "skipped"
    metrics_bundle = extract_k6_metrics(
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        summary_path=summary_path,
        metrics_json_path=metrics_path,
        duration_sec=duration_sec,
    )
    # Drop raw NDJSON after aggregation — these files can grow to multi-GB and freeze the API.
    try:
        if metrics_path.is_file():
            metrics_path.unlink()
    except OSError:
        pass
    return {
        "status": status,
        "detail": {
            "exit_code": proc.returncode,
            "execution_segment": list(execution_segment) if execution_segment else None,
            "time_series_source": metrics_bundle.get("time_series_source"),
            "metrics_json_path": str(metrics_path),
        },
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-8000:],
        "script_path": str(script_path),
        "summary_metrics": metrics_bundle.get("summary"),
        "time_series": metrics_bundle.get("time_series"),
    }


def dispatch_perf_plan(
    plan: dict[str, Any],
    *,
    project_id: int,
    artifact_id: int,
    base_url: str = "http://127.0.0.1:8002",
    interactive: bool = False,
) -> dict[str, Any]:
    effective = dict(plan) if isinstance(plan, dict) else {}
    # Interactive UI dispatch: keep runtime short so browser clients do not abort.
    if interactive:
        effective["duration"] = min(int(effective.get("duration") or 15), 15)
        effective["warmup"] = min(int(effective.get("warmup") or 0), 3)
        effective["max_concurrency"] = min(int(effective.get("max_concurrency") or 5), 10)
    script = plan_to_k6_script(effective, default_base_url=base_url)
    path = write_k6_script(project_id, artifact_id, script)
    duration_sec = int(effective.get("duration") or 60) + int(effective.get("warmup") or 0)
    # Allow process slightly longer than stages; hard-cap for interactive paths.
    timeout_sec = min(max(duration_sec + 30, 60), 120 if interactive else 600)
    result = dispatch_k6_run(path, timeout_sec=timeout_sec, duration_sec=duration_sec)
    result["generated_script_preview"] = script[:1200]
    if interactive:
        detail = dict(result.get("detail") or {})
        detail["interactive_capped"] = True
        detail["effective_duration"] = effective.get("duration")
        result["detail"] = detail
    return result