"""Celery 应用（broker/backend 使用 REDIS_URL）。"""

from __future__ import annotations

from celery import Celery

from backend.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_tp",
    broker=settings.redis_url or "redis://127.0.0.1:6379/0",
    backend=settings.redis_url or "redis://127.0.0.1:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.celery_queue_name,
    task_routes={
        "backend.celery_app.process_execution_job_task": {"queue": settings.celery_queue_name},
        "backend.celery_app.process_ai_async_job_task": {"queue": settings.celery_queue_name},
    },
)


@celery_app.task(name="backend.celery_app.process_execution_job_task", bind=True, max_retries=0)
def process_execution_job_task(self, job_id: int) -> str:
    from backend.services.job_tasks import process_execution_job

    return process_execution_job(job_id)


@celery_app.task(name="backend.celery_app.process_ai_async_job_task", bind=True, max_retries=0)
def process_ai_async_job_task(self, job_id: int) -> str:
    from backend.services.job_tasks import process_ai_async_job

    return process_ai_async_job(job_id)
