from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.core.config import get_settings
from backend.db import session as db_session
from backend.db.bootstrap import bootstrap_schema


@pytest.fixture(autouse=True)
def _clear_settings(monkeypatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_alembic_mode_requires_tables(monkeypatch):
    monkeypatch.setenv("SCHEMA_BOOTSTRAP_MODE", "alembic")
    get_settings.cache_clear()

    with patch("backend.db.bootstrap.inspect") as mock_inspect:
        mock_inspect.return_value.get_table_names.return_value = ["users", "projects"]
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            bootstrap_schema()


def test_session_schema_has_execution_jobs():
    from sqlalchemy import inspect

    tables = set(inspect(db_session.engine).get_table_names())
    assert "execution_jobs" in tables
    assert "users" in tables
