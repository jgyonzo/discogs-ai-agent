"""Tracing zero-footprint guarantees (021 US1/US3, contracts/tracing.md §3).

Two surfaces: (a) the instrumented loop behaves byte-identically with
tracing unconfigured — answers, dispatch payloads, all four error shapes,
the tool-budget fallback; (b) the CLI construction site wraps the client
only when tracing is effective, bridges settings → os.environ only then,
and degrades flag-without-key to a notice, never an exit.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from collection_agent import cli
from collection_agent.agent import MAX_TOOL_ROUNDS, ToolDef
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from tests.integration.test_agent_loop import build_agent

_LS_VARS = (
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_ENDPOINT",
    "LANGSMITH_PROJECT",
)


def _assert_no_langsmith_env():
    assert not [v for v in _LS_VARS if v in os.environ]


# --- (a) instrumented loop, tracing unconfigured (autouse scrub) ----------


def test_turn_and_payloads_unchanged_with_tracing_off(
    settings, store, complete_snapshot
):
    agent, llm = build_agent(
        settings, store,
        script=[("tool", "aggregate_by", {"attribute": "genre"}), ("text", "ok")],
        snapshot=complete_snapshot,
    )
    assert agent.run_turn("what genres do I have?") == "ok"
    assert len(llm.requests) == 2
    _assert_no_langsmith_env()  # a traced turn must not conjure tracing env


def test_all_four_dispatch_error_shapes_unchanged(settings, store, complete_snapshot):
    agent, _ = build_agent(
        settings, store, script=[("text", "unused")], snapshot=complete_snapshot
    )

    class _NoParams(BaseModel):
        pass

    agent.register(
        ToolDef(
            name="boom",
            description="always raises (tests the tool-bug shape)",
            params_model=_NoParams,
            fn=lambda session, args: 1 / 0,
        )
    )

    unknown = agent._dispatch("nonexistent_tool", "{}")
    assert "unknown tool" in unknown["error"]
    assert "available:" in unknown["error"]

    bad_json = agent._dispatch("top_n", "{not json")
    assert "invalid JSON arguments" in bad_json["error"]

    invalid = agent._dispatch("top_n", '{"basis": "not_a_basis"}')
    assert "invalid arguments" in invalid["error"]

    crashed = agent._dispatch("boom", "{}")
    assert crashed["error"].startswith("tool boom failed")


def test_tool_budget_fallback_unchanged(settings, store, complete_snapshot):
    agent, llm = build_agent(
        settings, store,
        script=[("tool", "aggregate_by", {"attribute": "genre"})] * MAX_TOOL_ROUNDS,
        snapshot=complete_snapshot,
    )
    answer = agent.run_turn("loop forever")
    assert answer == (
        "I could not complete that request within the tool budget — please rephrase."
    )
    assert len(llm.requests) == MAX_TOOL_ROUNDS


# --- (b) construction-site wiring (cli._build_llm_client via _build_agent) --


def _cli_settings(tmp_path, **extra) -> Settings:
    return Settings(
        _env_file=None,
        DISCOGS_USER_TOKEN="test-token-not-real",
        OPENAI_API_KEY="sk-test-not-real",
        SNAPSHOT_PATH=tmp_path / "snapshot.json",
        **extra,
    )


def test_unconfigured_builds_plain_unwrapped_client(tmp_path, monkeypatch):
    from openai import OpenAI

    def _fail_wrap(client, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("wrap_openai must not be called when unconfigured")

    monkeypatch.setattr("langsmith.wrappers.wrap_openai", _fail_wrap)
    settings = _cli_settings(tmp_path)
    agent = cli._build_agent(settings, SnapshotStore(settings.snapshot_path))
    assert isinstance(agent.llm, OpenAI)
    _assert_no_langsmith_env()


def test_flag_without_key_notices_and_stays_unwrapped(tmp_path, monkeypatch, capsys):
    from openai import OpenAI

    def _fail_wrap(client, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("wrap_openai must not be called without an API key")

    monkeypatch.setattr("langsmith.wrappers.wrap_openai", _fail_wrap)
    settings = _cli_settings(tmp_path, LANGSMITH_TRACING="true")
    agent = cli._build_agent(settings, SnapshotStore(settings.snapshot_path))
    assert isinstance(agent.llm, OpenAI)
    _assert_no_langsmith_env()
    out = capsys.readouterr().out
    assert "LANGSMITH_API_KEY" in out
    assert "continuing without tracing" in out


def test_configured_wraps_client_and_bridges_env(tmp_path, monkeypatch):
    from openai import OpenAI

    sentinel = object()
    wrapped = []

    def _fake_wrap(client, **kwargs):
        wrapped.append(client)
        return sentinel

    monkeypatch.setattr("langsmith.wrappers.wrap_openai", _fake_wrap)
    settings = _cli_settings(
        tmp_path, LANGSMITH_TRACING="true", LANGSMITH_API_KEY="ls-test-key"
    )
    try:
        agent = cli._build_agent(settings, SnapshotStore(settings.snapshot_path))
        assert agent.llm is sentinel
        assert len(wrapped) == 1 and isinstance(wrapped[0], OpenAI)
        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert os.environ["LANGSMITH_API_KEY"] == "ls-test-key"
        # the COMPONENT's project, never agent/'s LANGSMITH_PROJECT (R2)
        assert os.environ["LANGSMITH_PROJECT"] == "discogs-collection-agent"
        # endpoint unset in settings ⇒ not exported (SDK default applies)
        assert "LANGSMITH_ENDPOINT" not in os.environ
    finally:
        # the bridge writes os.environ directly (not via monkeypatch):
        # scrub so nothing leaks past this test
        for var in _LS_VARS:
            os.environ.pop(var, None)
