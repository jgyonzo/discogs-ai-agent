"""028 T012: the web agent presents the CLI's exact tool surface; only
`start_sync` behavior differs (delta 13 — background delegation)."""

from __future__ import annotations

import json

from collection_agent.cli import _build_llm_client  # noqa: F401 (parity import guard)
from collection_agent.web.agent_factory import build_web_agent
from tests.conftest import make_record, make_snapshot
from tests.integration.test_agent_loop import StubLLM, build_agent as build_cli_agent


def make_web(settings, store, sync_starter, script=None):
    return build_web_agent(
        settings, store, StubLLM(script or []), sync_starter=sync_starter
    )


def test_tool_names_match_the_terminal_agent(settings, store, complete_snapshot):
    store.save(complete_snapshot)
    web_agent = make_web(settings, store, sync_starter=lambda: True)
    cli_agent, _ = build_cli_agent(settings, store, script=[])
    # the CLI test helper registers base+analytics only; the web factory
    # registers the FULL story set — assert it as a superset containing
    # every base tool plus organize/browse/media/playlist
    assert set(cli_agent.tool_names()) <= set(web_agent.tool_names())
    for name in ("snapshot_status", "start_sync", "propose_moves",
                 "filter_records", "media_links", "playlist_links"):
        assert name in web_agent.tool_names()


def test_start_sync_delegates_nonblocking_started(settings, store, complete_snapshot):
    calls = []

    def starter():
        calls.append(True)
        return True

    store.save(complete_snapshot)
    agent = make_web(
        settings, store, starter,
        script=[("tool", "start_sync", {}), ("text", "sync started")],
    )
    assert agent.run_turn("sync my collection") == "sync started"
    assert calls == [True]
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert payload["started"] is True
    assert "Collection tab" in payload["detail"]
    assert "note" not in payload


def test_start_sync_reports_already_running(settings, store, complete_snapshot):
    store.save(complete_snapshot)
    agent = make_web(
        settings, store, lambda: False,
        script=[("tool", "start_sync", {}), ("text", "already running")],
    )
    agent.run_turn("sync now")
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert payload["already_running"] is True


def test_start_sync_full_flag_ignored_with_honest_note(settings, store, complete_snapshot):
    store.save(complete_snapshot)
    agent = make_web(
        settings, store, lambda: True,
        script=[("tool", "start_sync", {"full": True}), ("text", "ok")],
    )
    agent.run_turn("full re-sync please")
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert payload["started"] is True  # a STANDARD sync ran
    assert "full re-sync is not available from the web page" in payload["note"]
