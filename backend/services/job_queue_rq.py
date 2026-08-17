from __future__ import annotations

import logging

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

QUEUE_NAME = "ai_tp_execution"


def get_redis_connection():
    settings = get_settings()
    url = (settings.redis_url or "").strip()
    if not url:
        raise RuntimeError("REDIS_URL is required for RQ job queue")
    from redis import Redis

    return Redis.from_url(url)


def get_rq_queue():
    from rq import Queue

    return Queue(QUEUE_NAME, connection=get_redis_connection())


def enqueue_rq_job(job_id: int) -> str | None:
    settings = get_settings()
    queue = get_rq_queue()
    job = queue.enqueue(
        "backend.services.job_tasks.process_execution_job",
        job_id,
        job_timeout=settings.rq_job_timeout_sec,
        failure_ttl=settings.rq_failure_ttl_sec,
        result_ttl=settings.rq_result_ttl_sec,
        description=f"execution_job:{job_id}",
    )
    logger.info("rq enqueued job_id=%s rq_job=%s", job_id, job.id)
    return job.id


def enqueue_rq_ai_job(job_id: int) -> str | None:
    settings = get_settings()
    queue = get_rq_queue()
    # AI LLM calls can exceed default run timeouts; allow up to 2x run timeout.
    timeout = max(int(settings.rq_job_timeout_sec or 600), 1200)
    job = queue.enqueue(
        "backend.services.job_tasks.process_ai_async_job",
        job_id,
        job_timeout=timeout,
        failure_ttl=settings.rq_failure_ttl_sec,
        result_ttl=settings.rq_result_ttl_sec,
        description=f"ai_async_job:{job_id}",
    )
    logger.info("rq enqueued ai_job_id=%s rq_job=%s", job_id, job.id)
    return job.id


def run_rq_worker(*, burst: bool = False) -> None:
    from rq import Worker

    conn = get_redis_connection()
    worker = Worker([QUEUE_NAME], connection=conn)
    logger.info("rq worker listening on queue=%s burst=%s", QUEUE_NAME, burst)
    worker.work(burst=burst)
