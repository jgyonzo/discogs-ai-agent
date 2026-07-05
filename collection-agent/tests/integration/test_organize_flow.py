"""US4 organize flow (T034): propose → confirm → execute with live
re-validation, folder creation/collision, per-item failure reporting,
and the gate proof: execute_plan is not an LLM tool and a plan cannot
execute unconfirmed."""

from __future__ import annotations

import json

import pytest

from collection_agent.agent import AgentSession
from collection_agent.models import Completeness, PlanState
from collection_agent.snapshot.sync import run_sync
from collection_agent.tools.organize import execute_plan, make_organize_tools
from tests.fixtures.fake_client import FakeDiscogsClient


@pytest.fixture()
def fake():
    return FakeDiscogsClient()


@pytest.fixture()
def synced_store(settings, store, fake):
    """A snapshot synced from the fake client, so usernames/instances match."""
    run_sync(fake, store, settings)
    return store


@pytest.fixture()
def propose(settings, synced_store, fake):
    (tool,) = make_organize_tools(settings, synced_store, client_factory=lambda: fake)
    def _propose(session, **kwargs):
        return tool.fn(session, tool.params_model(**kwargs))
    return _propose


def _confirm_and_execute(session, settings, store, fake):
    plan = session.pending_plan
    plan.state = PlanState.CONFIRMED  # what the CLI does after 'y'
    return execute_plan(plan, settings, store, client_factory=lambda: fake)


# --- propose is a dry run -----------------------------------------------------


def test_propose_parks_plan_and_touches_nothing(propose, settings):
    session = AgentSession()
    res = propose(session, record_refs=["9003"], target_folder_name="Techno")
    assert res["requires_confirmation"] is True
    assert res["move_count"] == 1
    assert session.pending_plan is not None
    assert session.pending_plan.state == PlanState.PROPOSED


def test_propose_makes_no_moves(propose, fake):
    propose(AgentSession(), record_refs=["9003"], target_folder_name="Techno")
    assert fake.moves == [] and fake.created_folders == []


def test_new_propose_expires_prior_plan(propose):
    session = AgentSession()
    propose(session, record_refs=["9003"], target_folder_name="Techno")
    first = session.pending_plan
    propose(session, record_refs=["9002"], target_folder_name="Techno")
    assert first.state == PlanState.EXPIRED
    assert session.pending_plan is not first


# --- execute: happy paths ---------------------------------------------------


def test_move_to_existing_folder(propose, settings, synced_store, fake):
    session = AgentSession()
    propose(session, record_refs=["9003"], target_folder_name="Techno")
    plan = _confirm_and_execute(session, settings, synced_store, fake)

    assert plan.state == PlanState.EXECUTED
    assert plan.moves[0].result == "ok"
    assert fake.moves == [(1, 103, 9003, 3)]  # from folder 1 → Techno (3)
    snap = synced_store.load()
    assert next(r for r in snap.records if r.instance_id == 9003).folder_id == 3
    assert snap.meta.completeness == Completeness.COMPLETE  # patched in place


def test_move_to_new_folder_creates_it(propose, settings, synced_store, fake):
    session = AgentSession()
    res = propose(session, record_refs=["9003", "9005"],
                  target_folder_name="Jazz Crate", create_if_missing=True)
    assert "(will be created)" in res["target_folder"]
    plan = _confirm_and_execute(session, settings, synced_store, fake)

    assert fake.created_folders == ["Jazz Crate"]
    new_id = plan.target_folder.folder_id
    assert all(m.result == "ok" for m in plan.moves)
    assert {(m[2], m[3]) for m in fake.moves} == {(9003, new_id), (9005, new_id)}
    snap = synced_store.load()
    assert any(f.folder_id == new_id and f.name == "Jazz Crate" for f in snap.folders)


def test_already_in_target_is_idempotent_ok(propose, settings, synced_store, fake):
    session = AgentSession()
    propose(session, record_refs=["9001"], target_folder_name="Techno")  # already in 3
    plan = _confirm_and_execute(session, settings, synced_store, fake)
    assert plan.moves[0].result == "ok"
    assert fake.moves == []  # no pointless API write


# --- validation & failure paths ------------------------------------------------


def test_folder_collision_uses_existing(propose):
    res = propose(AgentSession(), record_refs=["9003"],
                  target_folder_name="techno", create_if_missing=True)
    assert "already exists" in res["notes"][0]
    assert "(will be created)" not in res["target_folder"]


def test_folder_zero_rejected(propose):
    res = propose(AgentSession(), record_refs=["9003"], target_folder_name="All")
    assert res["error"] == "invalid_target_folder"


def test_missing_folder_without_create_flag(propose):
    res = propose(AgentSession(), record_refs=["9003"], target_folder_name="Nope")
    assert res["error"] == "folder_not_found"
    assert "Techno" in res["existing_folders"]


def test_live_revalidation_failure_is_per_item(propose, settings, synced_store, fake):
    session = AgentSession()
    propose(session, record_refs=["9003", "9005"], target_folder_name="Techno")
    del fake.live_instances[9003]  # removed on Discogs since the sync
    plan = _confirm_and_execute(session, settings, synced_store, fake)

    by_iid = {m.instance_id: m for m in plan.moves}
    assert by_iid[9003].result == "failed"
    assert "no longer found" in by_iid[9003].error
    assert by_iid[9005].result == "ok"          # others proceed (FR-020)
    assert (1, 104, 9005, 3) in fake.moves
    # failed item's snapshot state untouched:
    snap = synced_store.load()
    assert next(r for r in snap.records if r.instance_id == 9003).folder_id == 1


def test_unresolvable_records_error(propose):
    res = propose(AgentSession(), record_refs=["totally unknown"],
                  target_folder_name="Techno")
    assert res["error"] == "no_records_resolved"


# --- the gate (FR-019) ------------------------------------------------------------


def test_unconfirmed_plan_cannot_execute(propose, settings, synced_store, fake):
    session = AgentSession()
    propose(session, record_refs=["9003"], target_folder_name="Techno")
    with pytest.raises(ValueError, match="only a confirmed plan"):
        execute_plan(session.pending_plan, settings, synced_store,
                     client_factory=lambda: fake)
    assert fake.moves == []


def test_execute_plan_is_not_an_llm_tool(settings, synced_store, fake):
    """Gate proof: the model can propose, never execute."""
    from collection_agent.registry import build_registry
    from collection_agent.tools.analytics import make_analytics_tools
    from collection_agent.tools.base import make_base_tools
    from collection_agent.tools.browse import make_browse_tools
    from collection_agent.tools.media import make_media_tools
    from collection_agent.agent import Agent
    from tests.integration.test_agent_loop import StubLLM

    llm = StubLLM([("tool", "execute_plan", {"plan_id": "x"}), ("text", "cannot")])
    agent = Agent(registry=build_registry(settings), model="stub", llm_client=llm)
    for make in (
        lambda: make_base_tools(synced_store, lambda full: None),
        lambda: make_analytics_tools(settings, synced_store),
        lambda: make_browse_tools(settings, synced_store),
        lambda: make_media_tools(settings, synced_store),
        lambda: make_organize_tools(settings, synced_store, client_factory=lambda: fake),
    ):
        for tool in make():
            agent.register(tool)

    assert "propose_moves" in agent.tool_names()
    assert "execute_plan" not in agent.tool_names()

    agent.run_turn("execute the plan directly")  # LLM tries anyway
    payload = json.loads(
        next(m for m in agent.session.messages if m["role"] == "tool")["content"]
    )
    assert "unknown tool" in payload["error"]
    assert fake.moves == []
