"""Distributed scheduler lease with Redis-first and database fallback."""
from __future__ import annotations

import logging
import socket
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert, update
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import SessionLocal
from backend.models.entities import SchedulerLease

logger = logging.getLogger(__name__)
LOCK_KEY = "ai_tp:lock:ops_scheduler"


def _token() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex}"


class SchedulerLeaseLock:
    def __init__(self, ttl_seconds: int = 45):
        self.ttl_seconds = max(10, ttl_seconds)
        self.token = _token()
        self.redis = None
        self.db: Session | None = None
        self.backend = "none"

    def acquire(self) -> bool:
        settings = get_settings()
        if (settings.redis_url or "").strip():
            try:
                import redis  # type: ignore[import-untyped]

                self.redis = redis.from_url(settings.redis_url, decode_responses=True)
                if self.redis.set(LOCK_KEY, self.token, nx=True, ex=self.ttl_seconds):
                    self.backend = "redis"
                    return True
                return False
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler Redis lock unavailable, using database lease: %s", exc)
        self.db = SessionLocal()
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(seconds=self.ttl_seconds)
        try:
            self.db.execute(delete(SchedulerLease).where(SchedulerLease.expires_at <= now))
            self.db.execute(insert(SchedulerLease).values(lease_key=LOCK_KEY, owner_token=self.token, expires_at=expiry))
            self.db.commit()
            self.backend = "database"
            return True
        except Exception:
            self.db.rollback()
            row = self.db.query(SchedulerLease).filter(SchedulerLease.lease_key == LOCK_KEY).first()
            if row and row.expires_at <= now:
                row.owner_token, row.expires_at = self.token, expiry
                self.db.commit()
                self.backend = "database"
                return True
            self.db.close()
            self.db = None
            return False

    def release(self) -> None:
        try:
            if self.backend == "redis" and self.redis:
                script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
                self.redis.eval(script, 1, LOCK_KEY, self.token)
            elif self.backend == "database" and self.db:
                self.db.query(SchedulerLease).filter(
                    SchedulerLease.lease_key == LOCK_KEY, SchedulerLease.owner_token == self.token
                ).delete(synchronize_session=False)
                self.db.commit()
        finally:
            if self.db:
                self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.release()
