from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import get_settings
from backend.services.oidc_state_store import consume_oidc_state, store_oidc_state


@pytest.fixture(autouse=True)
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_oidc_state_memory_roundtrip(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    get_settings.cache_clear()

    import backend.services.oidc_state_store as mod

    mod._REDIS_CHECKED = False
    mod._REDIS_CLIENT = None
    mod._MEMORY.clear()

    store_oidc_state("state-abc")
    assert consume_oidc_state("state-abc") is True
    assert consume_oidc_state("state-abc") is False


def test_oidc_state_redis_roundtrip(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    get_settings.cache_clear()

    import backend.services.oidc_state_store as mod

    fake = MagicMock()
    fake.ping.return_value = True
    fake.delete.return_value = 1

    with patch.object(mod, "_redis_client", return_value=fake):
        store_oidc_state("state-redis")
        fake.setex.assert_called_once()
        assert consume_oidc_state("state-redis") is True
        fake.delete.assert_called()
