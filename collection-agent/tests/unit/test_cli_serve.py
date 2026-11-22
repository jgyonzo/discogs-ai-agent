"""028 T015: `serve` is the subcommand, `scan` a fully working alias
(agent-tools delta 14; FR-015 — the 027 container CMD must keep working)."""

from __future__ import annotations

import pytest

from collection_agent import cli


@pytest.fixture()
def env_token(monkeypatch, tmp_path):
    # load_settings() needs the token; keep every path tmp-isolated
    monkeypatch.setenv("DISCOGS_USER_TOKEN", "test-token-not-real")
    monkeypatch.setenv("SNAPSHOT_PATH", str(tmp_path / "snapshot.json"))
    monkeypatch.setenv(
        "COLLECTION_AGENT_SCAN_JOURNAL_DIR", str(tmp_path / "scan-sessions")
    )


@pytest.mark.parametrize("command", ["serve", "scan"])
def test_both_names_dispatch_to_the_same_server(command, env_token, monkeypatch):
    calls = []

    def fake_serve(settings, host, port):
        calls.append((host, port))
        return 0

    monkeypatch.setattr(cli, "_cmd_serve", fake_serve)
    assert cli.main([command]) == 0
    assert calls == [(None, None)]


@pytest.mark.parametrize("command", ["serve", "scan"])
def test_host_port_options_work_on_both_names(command, env_token, monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli, "_cmd_serve", lambda settings, host, port: calls.append((host, port)) or 0
    )
    assert cli.main([command, "--host", "127.0.0.1", "--port", "9000"]) == 0
    assert calls == [("127.0.0.1", 9000)]


def test_serve_without_openai_key_exits_config(settings):
    # the conftest settings fixture has no OPENAI_API_KEY and reads no .env
    assert settings.openai_api_key is None
    assert cli._cmd_serve(settings, host=None, port=None) == cli.EXIT_CONFIG
