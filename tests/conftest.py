from __future__ import annotations

import os
import tempfile
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.auth_helpers import login_with_encrypted_password

# Configure isolated DB before backend modules bind the default engine.
_test_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_file.name}"
os.environ["JOB_WORKER_ENABLED"] = "false"
os.environ.setdefault("SCHEMA_BOOTSTRAP_MODE", "bootstrap")

from backend.core.config import get_settings  # noqa: E402
from backend.db import session as db_session  # noqa: E402
from backend.db.bootstrap import bootstrap_schema  # noqa: E402
from backend.db.session import Base, get_db  # noqa: E402
from backend.main import app  # noqa: E402

get_settings.cache_clear()
_settings = get_settings()
_test_engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False},
)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)
db_session.engine = _test_engine
db_session.SessionLocal = _TestSessionLocal


@pytest.fixture(scope="session", autouse=True)
def _init_schema() -> None:
    Base.metadata.drop_all(bind=_test_engine)
    bootstrap_schema()


@pytest.fixture()
def db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db) -> Generator[TestClient, None, None]:
    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    settings = get_settings()
    res = login_with_encrypted_password(
        client,
        username=settings.bootstrap_admin_username,
        password=settings.bootstrap_admin_password,
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
