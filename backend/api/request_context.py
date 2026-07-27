from __future__ import annotations

from contextvars import ContextVar

from backend.models.entities import User

current_user_ctx: ContextVar[User | None] = ContextVar("current_user", default=None)


def get_current_user_optional() -> User | None:
    return current_user_ctx.get()
