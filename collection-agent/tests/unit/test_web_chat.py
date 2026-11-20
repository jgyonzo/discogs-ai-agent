"""028 T008: WebChat unit behavior — lock, plan expiry, message rewind
(research R2), transcript entries, pending-plan view."""

from __future__ import annotations

import threading

import pytest

from collection_agent.agent import AgentSession
from collection_agent.models import PlannedMove, PlanState, TargetFolder, WritePlan
from collection_agent.web.chat import (
    ChatBusyError,
    PlanGateError,
    TurnFailedError,
    WebChat,
)


class FakeAgent:
    """Just the surface WebChat touches: .session + .run_turn. Mimics the
    real loop's message appends (user first, then assistant/tool debris)."""

    def __init__(self, replies=None, error=None, debris=0, plan_factory=None):
        self.session = AgentSession()
        self._replies = list(replies or [])
        self._error = error
        self._debris = debris  # extra messages appended before a failure
        self._plan_factory = plan_factory

    def run_turn(self, text):
        self.session.messages.append({"role": "user", "content": text})
        for i in range(self._debris):
            self.session.messages.append(
                {"role": "assistant", "content": None, "tool_calls": [{"id": str(i)}]}
            )
        if self._error is not None:
            raise self._error
        if self._plan_factory is not None:
            self.session.pending_plan = self._plan_factory()
        reply = self._replies.pop(0)
        self.session.messages.append({"role": "assistant", "content": reply})
        return reply


def make_plan(plan_id="plan-1", create=False):
    return WritePlan(
        plan_id=plan_id,
        target_folder=TargetFolder(folder_id=3, name="Techno", create=create),
        moves=[
            PlannedMove(
                instance_id=11, release_id=101, display="A – X", from_folder_id=1
            )
        ],
    )


def make_chat(agent, settings, store):
    return WebChat(agent, settings, store, client_factory=lambda: None)


def test_turn_appends_user_and_assistant_entries(settings, store):
    chat = make_chat(FakeAgent(replies=["hola"]), settings, store)
    resp = chat.run_turn("hola?")
    assert resp.reply == "hola"
    assert [(e.kind, e.text) for e in chat.transcript] == [
        ("user", "hola?"),
        ("assistant", "hola"),
    ]
    assert resp.pending_plan is None


def test_busy_lock_raises_never_queues(settings, store):
    chat = make_chat(FakeAgent(replies=["x"]), settings, store)
    assert chat._lock.acquire(blocking=False)
    try:
        with pytest.raises(ChatBusyError):
            chat.run_turn("second")
    finally:
        chat._lock.release()
    assert chat.transcript == []  # the refused turn left no trace


def test_failed_turn_rewinds_messages_and_stays_usable(settings, store):
    agent = FakeAgent(error=RuntimeError("provider down"), debris=2)
    chat = make_chat(agent, settings, store)
    before = len(agent.session.messages)  # just the system prompt
    with pytest.raises(TurnFailedError):
        chat.run_turn("question")
    # research R2: user msg + tool_calls debris rewound — session is clean
    assert len(agent.session.messages) == before
    assert [e.kind for e in chat.transcript] == ["user", "error"]
    # lock released — a next turn works
    agent._error = None
    agent._replies = ["recovered"]
    assert chat.run_turn("again").reply == "recovered"


def test_new_turn_expires_pending_plan(settings, store):
    agent = FakeAgent(replies=["proposed", "next"], plan_factory=make_plan)
    chat = make_chat(agent, settings, store)
    resp = chat.run_turn("move stuff")
    assert resp.pending_plan is not None
    plan = agent.session.pending_plan
    agent._plan_factory = None
    resp2 = chat.run_turn("actually, how many records do I have?")
    assert resp2.pending_plan is None
    assert plan.state == PlanState.EXPIRED
    assert agent.session.pending_plan is None
    assert "plan_cancelled" in [e.kind for e in chat.transcript]
    # a confirm for the expired plan is refused
    with pytest.raises(PlanGateError) as exc:
        chat.confirm_plan(plan.plan_id)
    assert exc.value.code == "no_pending_plan"


def test_pending_plan_view_shapes(settings, store):
    agent = FakeAgent(replies=["proposed"], plan_factory=lambda: make_plan(create=True))
    chat = make_chat(agent, settings, store)
    view = chat.run_turn("move it").pending_plan
    assert view.target_folder == "Techno (new)"
    assert view.move_count == 1
    assert view.moves == ["A – X"]


def test_cancel_sets_cancelled_and_clears(settings, store):
    agent = FakeAgent(replies=["proposed"], plan_factory=make_plan)
    chat = make_chat(agent, settings, store)
    plan_id = chat.run_turn("move it").pending_plan.plan_id
    plan = agent.session.pending_plan
    chat.cancel_plan(plan_id)
    assert plan.state == PlanState.CANCELLED
    assert agent.session.pending_plan is None
    assert chat.transcript[-1].kind == "plan_cancelled"


def test_plan_mismatch_and_none_pending_codes(settings, store):
    agent = FakeAgent(replies=["proposed"], plan_factory=make_plan)
    chat = make_chat(agent, settings, store)
    with pytest.raises(PlanGateError) as exc:
        chat.confirm_plan("nope")
    assert exc.value.code == "no_pending_plan"
    chat.run_turn("move it")
    with pytest.raises(PlanGateError) as exc:
        chat.confirm_plan("some-other-id")
    assert exc.value.code == "plan_mismatch"
    # the mismatch refusal left the real plan pending and untouched
    assert agent.session.pending_plan.state == PlanState.PROPOSED


def test_history_lists_transcript_and_pending_plan(settings, store):
    agent = FakeAgent(replies=["proposed"], plan_factory=make_plan)
    chat = make_chat(agent, settings, store)
    chat.run_turn("move it")
    h = chat.history(snapshot_state="stale")
    assert h.snapshot_state == "stale"
    assert [e.kind for e in h.entries] == ["user", "assistant"]
    assert h.pending_plan is not None


def test_plan_actions_respect_the_busy_lock(settings, store):
    agent = FakeAgent(replies=["proposed"], plan_factory=make_plan)
    chat = make_chat(agent, settings, store)
    plan_id = chat.run_turn("move it").pending_plan.plan_id
    assert chat._lock.acquire(blocking=False)
    try:
        with pytest.raises(ChatBusyError):
            chat.confirm_plan(plan_id)
        with pytest.raises(ChatBusyError):
            chat.cancel_plan(plan_id)
    finally:
        chat._lock.release()
