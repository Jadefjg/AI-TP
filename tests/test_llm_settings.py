"""LLM provider resolution (OpenAI / DeepSeek / local)."""

from backend.core.config import Settings, get_settings


def test_deepseek_used_when_openai_key_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_API", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.resolved_llm_provider() == "deepseek"
    assert settings.resolved_base_url() == "https://api.deepseek.com/v1"
    assert settings.resolved_high_precision_model() == "deepseek-chat"
    get_settings.cache_clear()


def test_openai_preferred_when_both_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.resolved_llm_provider() == "openai"
    assert settings.resolved_api_key() == "sk-openai"
    get_settings.cache_clear()


def test_profile_model_chain_maps_openai_names_to_deepseek(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("AI_HIGH_PRECISION_MODEL", "gpt-4o")
    get_settings.cache_clear()
    from backend.services.ai.llm_settings import profile_model_chain

    settings = Settings()
    models = profile_model_chain(settings, "high")
    assert models[0] == "deepseek-chat"
    get_settings.cache_clear()
