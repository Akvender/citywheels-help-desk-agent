import pytest

from helpdesk.config import load_llm_settings


def test_settings_are_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("LLM_MODEL", "some-model")

    settings = load_llm_settings()

    assert (settings.base_url, settings.api_key, settings.model) == ("http://llm.example/v1", "key", "some-model")


def test_missing_variable_is_named_in_the_error(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        load_llm_settings()
