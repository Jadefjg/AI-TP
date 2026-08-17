"""RQ/Celery 可导入的任务入口（须在独立模块，避免循环依赖）。"""

from __future__ import annotations

import logging

from backend.db.session import SessionLocal
from backend.services.ai_job_queue import process_ai_job
from backend.services.job_queue import process_job

logger = logging.getLogger(__name__)


def process_execution_job(job_id: int) -> str:
    """执行单条 execution_jobs 记录，供 RQ/Celery 调用。"""
    db = SessionLocal()
    try:
        process_job(db, job_id, auto_claim=True)
        return f"ok:{job_id}"
    except Exception:  # noqa: BLE001
        logger.exception("process_execution_job failed job_id=%s", job_id)
        raise
    finally:
        db.close()


def process_ai_async_job(job_id: int) -> str:
    """执行单条 ai_async_jobs 记录，供 RQ/Celery 调用。"""
    db = SessionLocal()
    try:
        process_ai_job(db, job_id, auto_claim=True)
        return f"ok:ai:{job_id}"
    except Exception:  # noqa: BLE001
        logger.exception("process_ai_async_job failed job_id=%s", job_id)
        raise
    finally:
        db.close()
