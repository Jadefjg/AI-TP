from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        # timeout: wait on locked DB instead of hanging the API worker forever
        return {"check_same_thread": False, "timeout": 30}
    return {}


settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args(settings.database_url),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
