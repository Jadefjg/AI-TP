from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import K6DispatchJob, K6WorkerNode
from backend.services.engines.perf_k6 import dispatch_k6_run, plan_to_k6_script, write_k6_script


def _merge_node_metrics(node_results: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summaries = [r.get("summary_metrics") for r in node_results if isinstance(r.get("summary_metrics"), dict)]
    if not summaries:
        return {}, []
    avg_rt = sum(float(s.get("avg_rt_ms") or 0) for s in summaries) / len(summaries)
    p95 = max(float(s.get("p95_rt_ms") or 0) for s in summaries)
    tps = sum(float(s.get("tps") or 0) for s in summaries)
    err = max(float(s.get("error_rate") or 0) for s in summaries)
    merged = {"avg_rt_ms": round(avg_rt, 2), "p95_rt_ms": round(p95, 2), "tps": round(tps, 3), "error_rate": round(err, 3)}
    series = node_results[0].get("time_series") if node_results else []
    return merged, series if isinstance(series, list) else []


def _scale_plan_for_shard(plan: dict[str, Any], shard_index: int, shard_total: int) -> dict[str, Any]:
    scaled = dict(plan)
    start = int(plan.get("start_concurrency") or 1)
    max_c = int(plan.get("max_concurrency") or start)
    if shard_total <= 1:
        return scaled
    part = max(1, max_c // shard_total)
    scaled["start_concurrency"] = max(1, start // shard_total)
    scaled["max_concurrency"] = part
    scaled["shard_index"] = shard_index
    scaled["shard_total"] = shard_total
    return scaled


def _run_on_local(
    script_path: Path,
    *,
    timeout_sec: int,
    duration_sec: int = 60,
    execution_segment: tuple[int, int] | None = None,
) -> dict[str, Any]:
    return dispatch_k6_run(
        script_path,
        timeout_sec=timeout_sec,
        duration_sec=duration_sec,
        execution_segment=execution_segment,
    )


def _run_on_http_worker(
    node: K6WorkerNode,
    *,
    script: str,
    timeout_sec: int,
) -> dict[str, Any]:
    settings = get_settings()
    url = f"{node.endpoint.rstrip('/')}/internal/k6/run"
    headers = {"Content-Type": "application/json"}
    if settings.k6_worker_token:
        headers["X-Worker-Token"] = settings.k6_worker_token
    try:
        with httpx.Client(timeout=timeout_sec + 30) as client:
            resp = client.post(
                url,
                json={"script": script, "timeout_sec": timeout_sec},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            data["worker"] = node.name
            data["mode"] = "http"
            return data
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "worker": node.name,
            "mode": "http",
            "detail": {"reason": str(exc)},
            "stdout": "",
            "stderr": str(exc),
        }


def list_active_workers(db: Session) -> list[K6WorkerNode]:
    return (
        db.query(K6WorkerNode)
        .filter(K6WorkerNode.enabled.is_(True))
        .order_by(K6WorkerNode.weight.desc(), K6WorkerNode.id.asc())
        .all()
    )


def seed_default_worker(db: Session) -> None:
    if db.query(K6WorkerNode).count() > 0:
        return
    settings = get_settings()
    db.add(
        K6WorkerNode(
            name="local-primary",
            endpoint=settings.k6_local_worker_endpoint,
            mode="local",
            weight=100,
            enabled=True,
        )
    )
    db.commit()


def dispatch_perf_plan_distributed(
    db: Session,
    plan: dict[str, Any],
    *,
    project_id: int,
    artifact_id: int,
    base_url: str,
) -> dict[str, Any]:
    settings = get_settings()
    workers = list_active_workers(db)
    if not workers:
        seed_default_worker(db)
        workers = list_active_workers(db)

    master_script = plan_to_k6_script(plan, default_base_url=base_url)
    master_path = write_k6_script(project_id, artifact_id, master_script)

    job = K6DispatchJob(
        project_id=project_id,
        artifact_id=artifact_id,
        status="running",
        plan_snapshot=plan,
        node_results=[],
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    node_results: list[dict[str, Any]] = []
    timeout_sec = settings.default_test_timeout_sec

    duration_sec = int(plan.get("duration") or 60)
    segments_meta = [{"index": i, "total": len(workers), "worker": w.name} for i, w in enumerate(workers)]

    def _run_shard(index: int, node: K6WorkerNode) -> dict[str, Any]:
        shard_plan = _scale_plan_for_shard(plan, index, len(workers))
        segment = (index, len(workers))
        script = plan_to_k6_script(shard_plan, default_base_url=base_url, execution_segment=segment)
        if node.mode == "http":
            result = _run_on_http_worker(node, script=script, timeout_sec=timeout_sec)
        else:
            shard_path = write_k6_script(project_id, artifact_id * 1000 + index, script)
            result = _run_on_local(
                shard_path,
                timeout_sec=timeout_sec,
                duration_sec=duration_sec,
                execution_segment=segment,
            )
            result["script_path"] = str(shard_path)
        result["worker"] = node.name
        result["mode"] = node.mode
        result["execution_segment"] = list(segment)
        return result

    if len(workers) == 1 and workers[0].mode == "local":
        single = _run_shard(0, workers[0])
        node_results.append(single)
        single_status = str(single.get("status") or "failed")
        if single_status in {"passed", "skipped"}:
            job.status = "completed" if single_status == "passed" else "skipped"
        else:
            job.status = "failed"
        job.node_results = node_results
        job.master_script_path = str(master_path)
        job.summary_metrics = single.get("summary_metrics")
        job.time_series = single.get("time_series")
        job.execution_segments = segments_meta
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "status": single_status,
            "mode": "local",
            "job_id": job.id,
            "node_results": node_results,
            "summary_metrics": job.summary_metrics,
            "time_series": job.time_series,
            "execution_segments": job.execution_segments,
            "generated_script_preview": master_script[:1200],
            "detail": single.get("detail") or {},
            "reason": (single.get("detail") or {}).get("reason"),
        }

    with ThreadPoolExecutor(max_workers=min(len(workers), 8)) as pool:
        futures = {pool.submit(_run_shard, i, w): w for i, w in enumerate(workers)}
        for fut in as_completed(futures):
            node_results.append(fut.result())

    statuses = [r.get("status") for r in node_results]
    if all(s == "passed" for s in statuses):
        agg_status = "passed"
    elif any(s == "failed" for s in statuses):
        agg_status = "failed"
    elif any(s == "skipped" for s in statuses):
        agg_status = "skipped"
    else:
        agg_status = "error"

    job.status = "completed" if agg_status in {"passed", "skipped"} else "failed"
    job.node_results = node_results
    job.master_script_path = str(master_path)
    merged_summary, merged_series = _merge_node_metrics(node_results)
    job.summary_metrics = merged_summary
    job.time_series = merged_series
    job.execution_segments = segments_meta
    job.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": agg_status,
        "mode": "distributed",
        "job_id": job.id,
        "worker_count": len(workers),
        "node_results": node_results,
        "summary_metrics": job.summary_metrics,
        "time_series": job.time_series,
        "execution_segments": job.execution_segments,
        "generated_script_preview": master_script[:1200],
    }


def run_internal_k6_script(script: str, *, timeout_sec: int = 600) -> dict[str, Any]:
    k6_bin = shutil.which("k6")
    if not k6_bin:
        return {"status": "skipped", "detail": {"reason": "k6 not found"}, "stdout": "", "stderr": ""}
    tmp = Path("data") / "k6" / "worker-inline.js"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(script, encoding="utf-8")
    proc = subprocess.run([k6_bin, "run", str(tmp)], capture_output=True, text=True, timeout=timeout_sec)
    status = "passed" if proc.returncode == 0 else "failed"
    return {
        "status": status,
        "detail": {"exit_code": proc.returncode},
        "stdout": (proc.stdout or "")[-8000:],
        "stderr": (proc.stderr or "")[-8000:],
    }
