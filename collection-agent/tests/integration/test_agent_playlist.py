"""020 US1 integration: filter_records → playlist_links(use_last_listing)
through the stubbed agent loop; the tool is registered read-only (no plan,
no gate) and consumes — never mutates — the session's last listing."""

from __future__ import annotations

import json

from collection_agent.agent import Agent
from collection_agent.models import MediaLink
from collection_agent.registry import build_registry
from collection_agent.tools.browse import make_browse_tools
from collection_agent.tools.playlist import make_playlist_tools
from tests.conftest import make_record, make_snapshot

from tests.integration.test_agent_loop import StubLLM


def build_agent(settings, store, script, snapshot):
    store.save(snapshot)
    agent = Agent(
        registry=build_registry(settings), model="stub-model", llm_client=StubLLM(script)
    )
    for tool in make_browse_tools(settings, store):
        agent.register(tool)
    for tool in make_playlist_tools(settings, store):
        agent.register(tool)
    return agent


def snapshot_with_videos():
    return make_snapshot([
        make_record(1, title="Simple Things", artist="Alex Smoke",
                    genres=["Electronic"], styles=["Minimal"],
                    videos=[MediaLink(uri="https://www.youtube.com/watch?v=aaaaaaaaaaa")]),
        make_record(2, title="Blue Album", artist="Jazz Cat", genres=["Jazz"],
                    videos=[MediaLink(uri="https://www.youtube.com/watch?v=bbbbbbbbbbb")]),
    ])


def tool_payloads(agent):
    return [
        json.loads(m["content"])
        for m in agent.session.messages
        if m["role"] == "tool"
    ]


def test_two_prompt_journey_via_last_listing(settings, store):
    agent = build_agent(
        settings, store,
        script=[
            ("tool", "filter_records",
             {"criteria": [{"attribute": "genre", "value": "Electronic"}]}),
            ("text", "here is your listing"),
            ("tool", "playlist_links",
             {"use_last_listing": True, "suggested_name": "discogs-minimal"}),
            ("text", "here is your play link"),
        ],
        snapshot=snapshot_with_videos(),
    )
    assert agent.run_turn("find electronic records with their links") == "here is your listing"
    listing_after_filter = list(agent.session.last_listing_instance_ids)
    assert listing_after_filter == [1]

    assert agent.run_turn("create a playlist called discogs-minimal") == "here is your play link"
    _, playlist_payload = tool_payloads(agent)
    (link,) = playlist_payload["links"]
    assert "watch_videos?video_ids=aaaaaaaaaaa" in link["url"]
    assert playlist_payload["suggested_name"] == "discogs-minimal"

    # read-only: no pending plan of any kind, listing consumed not mutated
    assert agent.session.pending_plan is None
    assert agent.session.last_listing_instance_ids == listing_after_filter


def test_playlist_links_registered_but_never_an_executor(settings, store):
    agent = build_agent(
        settings, store, script=[("text", "hi")], snapshot=snapshot_with_videos()
    )
    assert "playlist_links" in agent.tool_names()
    # nothing execute-shaped ships with the playlist surface (delta 9)
    assert not [n for n in agent.tool_names() if n.startswith("execute")]
