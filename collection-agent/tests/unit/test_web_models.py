"""028 T003: web wire models — shapes per contracts/web-ui-api.md."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from collection_agent.web.models import (
    ChatEntry,
    ChatResponse,
    CollectionStatusResponse,
    HistoryResponse,
    MoveOutcomeView,
    PendingPlanView,
    SyncStatusView,
)


def test_pending_plan_view_fields():
    view = PendingPlanView(
        plan_id="p-1",
        target_folder="Tango (new)",
        move_count=2,
        moves=["A – X", "B – Y"],
    )
    assert view.model_dump() == {
        "plan_id": "p-1",
        "target_folder": "Tango (new)",
        "move_count": 2,
        "moves": ["A – X", "B – Y"],
    }


def test_chat_entry_kinds_are_closed_set():
    for kind in ("user", "assistant", "error", "plan_result", "plan_cancelled"):
        assert ChatEntry(kind=kind, text="t").kind == kind
    with pytest.raises(ValidationError):
        ChatEntry(kind="system", text="t")


def test_plan_result_entry_carries_move_outcomes():
    entry = ChatEntry(
        kind="plan_result",
        text="Moved 1/2 record(s) to Tango",
        moves=[
            MoveOutcomeView(display="A – X", result="ok"),
            MoveOutcomeView(display="B – Y", result="failed", error="gone"),
        ],
    )
    assert entry.moves[0].error is None
    assert entry.moves[1].result == "failed"


def test_chat_response_defaults_no_pending_plan():
    assert ChatResponse(reply="hola").pending_plan is None


def test_history_requires_snapshot_state():
    with pytest.raises(ValidationError):
        HistoryResponse()
    h = HistoryResponse(snapshot_state="missing")
    assert h.entries == [] and h.pending_plan is None


def test_sync_status_view_states_and_defaults():
    idle = SyncStatusView(state="idle")
    assert idle.phase is None and idle.warnings == [] and idle.finished_at is None
    with pytest.raises(ValidationError):
        SyncStatusView(state="paused")


def test_collection_status_allows_null_snapshot():
    resp = CollectionStatusResponse(
        snapshot=None,
        collection_url="https://example.test/user/u/collection",
        sync=SyncStatusView(state="idle"),
    )
    assert resp.snapshot is None
