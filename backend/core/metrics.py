from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "ai_tp_http_requests_total",
    "HTTP requests",
    ["method", "path_template", "status"],
)
HTTP_LATENCY = Histogram(
    "ai_tp_http_request_duration_seconds",
    "HTTP latency",
    ["method", "path_template"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
RUNS_TOTAL = Counter("ai_tp_test_runs_total", "Test runs created", ["status"])
JOBS_TOTAL = Counter(
    "ai_tp_execution_jobs_total",
    "Execution jobs processed",
    ["status", "backend"],
)
JOBS_IN_FLIGHT = Gauge("ai_tp_execution_jobs_in_flight", "Running execution jobs")


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def record_run_created(status: str) -> None:
    RUNS_TOTAL.labels(status=status).inc()


def record_job_finished(*, status: str, backend: str) -> None:
    JOBS_TOTAL.labels(status=status, backend=backend).inc()
    if status == "running":
        JOBS_IN_FLIGHT.inc()
    else:
        JOBS_IN_FLIGHT.dec()
