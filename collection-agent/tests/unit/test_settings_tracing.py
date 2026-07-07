"""Settings surface for LangSmith tracing (021, data-model §2).

Defaults must mean "tracing off"; the project name must come from the
component-dedicated var, never from agent/'s LANGSMITH_PROJECT.
"""

from __future__ import annotations

from pydantic import SecretStr

from collection_agent.settings import Settings


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, DISCOGS_USER_TOKEN="test-token-not-real", **kwargs)


def test_defaults_mean_tracing_off():
    s = _settings()
    assert s.langsmith_tracing is False
    assert s.langsmith_api_key is None
    assert s.langsmith_endpoint is None
    assert s.langsmith_project == "discogs-collection-agent"


def test_env_aliases_populate_fields(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-secret-key")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://smith.example.test")
    monkeypatch.setenv("COLLECTION_AGENT_LANGSMITH_PROJECT", "my-collection")
    s = _settings()
    assert s.langsmith_tracing is True
    assert s.langsmith_api_key is not None
    assert s.langsmith_api_key.get_secret_value() == "ls-secret-key"
    assert s.langsmith_endpoint == "https://smith.example.test"
    assert s.langsmith_project == "my-collection"


def test_langsmith_project_env_is_ignored(monkeypatch):
    """LANGSMITH_PROJECT belongs to the agent/ component (research R2):
    the collection agent must not inherit it."""
    monkeypatch.setenv("LANGSMITH_PROJECT", "discogs-analytics-agent")
    s = _settings()
    assert s.langsmith_project == "discogs-collection-agent"


def test_api_key_is_secret_and_does_not_leak_in_repr():
    s = _settings(LANGSMITH_API_KEY="ls-super-secret")
    assert isinstance(s.langsmith_api_key, SecretStr)
    assert "ls-super-secret" not in repr(s)
    assert "ls-super-secret" not in str(s)
