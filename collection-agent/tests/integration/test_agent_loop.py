"""Agent loop with a stubbed LLM (T023): tool dispatch for the 7 US1
analytics, warning relay, sync-required and empty-collection narration,
and prompt rendering from the registry."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from collection_agent.agent import Agent, render_system_prompt
from collection_agent.registry import build_registry
from collection_agent.tools.analytics import make_analytics_tools
from collection_agent.tools.base import make_base_tools
from tests.conftest import make_snapshot


class StubLLM:
    """OpenAI-shaped stub: replays a scripted sequence of turns. Each script
    entry is either ("tool", name, args_dict) or ("text", content).
    Records every request so tests can inspect messages/tools sent."""

    def __init__(self, script):
        self._script = list(script)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        kind, *rest = self._script.pop(0)
        if kind == "text":
            msg = SimpleNamespace(content=rest[0], tool_calls=None)
        else:
            name, args = rest
            msg = SimpleNamespace(
                content=None,
                tool_calls=[
                    SimpleNamespace(
                        id="call_1",
                        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
                    )
                ],
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def build_agent(settings, store, script, snapshot=None):
    if snapshot is not None:
        store.save(snapshot)
    registry = build_registry(settings)
    llm = StubLLM(script)
    agent = Agent(registry=registry, model="stub-model", llm_client=llm)
    for tool in make_base_tools(store, sync_runner=lambda full: (_ for _ in ()).throw(RuntimeError("no sync in tests"))):
        agent.register(tool)
    for tool in make_analytics_tools(settings, store):
        agent.register(tool)
    return agent, llm


ANALYTIC_CALLS = [
    ("aggregate_by", {"attribute": "genre"}),        # genres %
    ("aggregate_by", {"attribute": "label"}),        # top labels
    ("top_n", {"basis": "community_rating"}),        # top rated
    ("aggregate_by", {"attribute": "country"}),      # by country
    ("top_n", {"basis": "rarest"}),                  # rarest / most wanted
    ("collection_value", {}),                        # collection value
    ("top_n", {"basis": "most_expensive"}),          # most expensive
]


@pytest.mark.parametrize(("tool_name", "tool_args"), ANALYTIC_CALLS)
def test_each_analytic_dispatches_and_returns_grounded_payload(
    settings, store, complete_snapshot, tool_name, tool_args
):
    agent, llm = build_agent(
        settings, store,
        script=[("tool", tool_name, tool_args), ("text", "narrated answer")],
        snapshot=complete_snapshot,
    )
    answer = agent.run_turn("analytic question")
    assert answer == "narrated answer"

    # the tool result the LLM narrated from:
    tool_msg = next(m for m in agent.session.messages if m["role"] == "tool")
    payload = json.loads(tool_msg["content"])
    assert "error" not in payload
    if "basis" in payload:
        assert payload["basis"]  # rankings/value always state their basis
    if "buckets" in payload:
        assert payload["total_records"] == 5


def test_partial_snapshot_warning_reaches_the_llm(settings, store, partial_snapshot):
    agent, _ = build_agent(
        settings, store,
        script=[("tool", "aggregate_by", {"attribute": "genre"}), ("text", "ok")],
        snapshot=partial_snapshot,
    )
    agent.run_turn("¿qué géneros tengo?")
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert any("PARTIAL" in w for w in payload["warnings"])


def test_no_snapshot_surfaces_sync_required(settings, store):
    agent, _ = build_agent(
        settings, store,
        script=[("tool", "aggregate_by", {"attribute": "genre"}),
                ("text", "you need to sync first")],
    )
    answer = agent.run_turn("what genres do I have?")
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert payload["error"] == "sync_required"
    assert answer  # the model gets to narrate the limitation (scenario 8 analog)


def test_empty_collection_narrated_as_limitation(settings, store):
    agent, _ = build_agent(
        settings, store,
        script=[("tool", "aggregate_by", {"attribute": "genre"}),
                ("text", "your collection is empty")],
        snapshot=make_snapshot([]),
    )
    agent.run_turn("what genres do I have?")
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert payload["error"] == "empty_collection"
    assert "do not present" in payload["detail"]


def test_unknown_tool_and_bad_args_return_errors_not_crashes(settings, store, complete_snapshot):
    agent, _ = build_agent(
        settings, store,
        script=[("tool", "nonexistent_tool", {}), ("text", "sorry")],
        snapshot=complete_snapshot,
    )
    assert agent.run_turn("hm") == "sorry"

    agent2, _ = build_agent(
        settings, store,
        script=[("tool", "top_n", {"basis": "not_a_basis"}), ("text", "sorry")],
        snapshot=complete_snapshot,
    )
    assert agent2.run_turn("hm") == "sorry"
    payload = json.loads(
        next(m for m in agent2.session.messages if m["role"] == "tool")["content"]
    )
    assert "invalid arguments" in payload["error"]


def test_system_prompt_rendered_from_registry(settings):
    registry = build_registry(settings)
    prompt = render_system_prompt(registry)
    assert "{attribute_block}" not in prompt  # placeholder resolved
    assert "`genre`" in prompt and "`scarcity`" in prompt
    # VII(b) analog: the attribute docs come from the registry, and the
    # registry's thresholds (settings-sourced) surface in the prompt
    assert str(settings.rarity_want_have_ratio) in prompt


def test_system_prompt_has_locate_record_guidance(settings):
    """018 FR-006: presence-check procedure is in the standing instructions.
    Asserts on stable phrases, not exact prose."""
    prompt = render_system_prompt(build_registry(settings)).lower()
    # (a) artist + title-substring filtering
    assert "artist" in prompt and "title" in prompt and "contains" in prompt
    # (b) strip format noise from the queried title
    assert "2xlp" in prompt
    # (c) no reduced limit on presence checks
    assert "limit" in prompt
    # (d) artist-only retry before declaring absence
    assert "retry" in prompt and "artist only" in prompt
    # (e) contains-never-eq, with a SHORT distinctive substring
    assert "never `eq`" in prompt and "short" in prompt
    # (f) affirm near-matches as THE record, not "related"
    assert "is the requested record" in prompt and "related" in prompt


def test_all_expected_tools_registered(settings, store, complete_snapshot):
    agent, llm = build_agent(
        settings, store, script=[("text", "hi")], snapshot=complete_snapshot
    )
    assert agent.tool_names() == sorted(
        ["snapshot_status", "start_sync", "aggregate_by", "top_n", "collection_value"]
    )
    agent.run_turn("hola")
    sent_tools = {t["function"]["name"] for t in llm.requests[0]["tools"]}
    assert "aggregate_by" in sent_tools
    assert "execute_plan" not in sent_tools  # write execution is never an LLM tool
