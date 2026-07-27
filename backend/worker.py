"""Standalone execution job worker.

Usage:
  JOB_WORKER_IN_API=false JOB_WORKER_ENABLED=true python -m backend.worker

Queue backends:
  db / redis  — DB 认领轮询或 Redis BRPOP + 认领
  rq          — RQ Worker（需 REDIS_URL，pip install -e ".[worker]"）
  celery      — 请用: celery -A backend.celery_app worker -l info -Q ai_tp_execution
"""

from __future__ import annotations

import logging
import os
import signal
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("backend.worker")

_shutdown = False


def _handle_signal(*_args) -> None:
    global _shutdown
    _shutdown = True
    logger.info("shutdown requested")


def main() -> None:
    os.environ.setdefault("JOB_WORKER_IN_API", "false")
    from backend.core.config import get_settings
    from backend.db.bootstrap import bootstrap_schema

    settings = get_settings()
    if not settings.job_worker_enabled:
        logger.error("JOB_WORKER_ENABLED=false, exiting")
        sys.exit(1)

    bootstrap_schema()
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    backend = (settings.job_queue_backend or "db").strip().lower()
    logger.info(
        "worker starting (queue=%s, redis=%s)",
        backend,
        "yes" if settings.redis_url else "no",
    )

    if backend == "rq":
        from backend.services.job_queue_rq import run_rq_worker

        run_rq_worker(burst=False)
        return

    if backend == "celery":
        logger.error(
            "JOB_QUEUE_BACKEND=celery: start Celery worker instead, e.g.\n"
            "  celery -A backend.celery_app worker -l info -Q %s",
            settings.celery_queue_name,
        )
        sys.exit(2)

    from backend.services.job_queue import run_worker_forever

    run_worker_forever(stop_flag=lambda: _shutdown)


if __name__ == "__main__":
    main()
