from __future__ import annotations

import logging

from backend.celery_app import process_execution_job_task

logger = logging.getLogger(__name__)


def enqueue_celery_job(job_id: int) -> str:
    async_result = process_execution_job_task.delay(job_id)
    logger.info("celery enqueued job_id=%s task_id=%s", job_id, async_result.id)
    return async_result.id
