"""Web wire models (028, contracts/web-ui-api.md).

Display-only views over existing domain models: `PendingPlanView` renders
a parked `WritePlan` (the page can echo back ONLY `plan_id` — never move
data, FR-005), `MoveOutcomeView` renders per-item `execute_plan` results.
The contract's JSON object names drop the `View` suffix; these are the
Python classes behind them. Error envelope stays the scan shape
(`{"error": {"code", "message"}}`) built by the server, not modeled here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PendingPlanView(BaseModel):
    """Display view of the server-held PROPOSED WritePlan."""

    plan_id: str
    # rendered like the CLI table: name + " (new)" when it will be created
    target_folder: str
    move_count: int
    moves: list[str] = Field(default_factory=list)


class MoveOutcomeView(BaseModel):
    display: str
    result: Literal["ok", "failed"]
    error: str | None = None


class ChatEntry(BaseModel):
    """One transcript line (process-lived; the UI's record of the
    conversation, incl. events the LLM context never sees)."""

    kind: Literal["user", "assistant", "error", "plan_result", "plan_cancelled"]
    text: str
    moves: list[MoveOutcomeView] | None = None  # plan_result only


class ChatRequest(BaseModel):
    text: str


class ChatResponse(BaseModel):
    reply: str
    pending_plan: PendingPlanView | None = None


class HistoryResponse(BaseModel):
    entries: list[ChatEntry] = Field(default_factory=list)
    pending_plan: PendingPlanView | None = None
    # scan-health vocabulary: complete | partial | stale | missing —
    # drives the Chat tab's stale/absent banner (FR-011)
    snapshot_state: str


class PlanActionRequest(BaseModel):
    plan_id: str


class PlanConfirmResponse(BaseModel):
    target_folder: str
    moves: list[MoveOutcomeView] = Field(default_factory=list)


class SyncStatusView(BaseModel):
    state: Literal["idle", "running", "complete", "partial", "failed"]
    phase: str | None = None
    done: int | None = None
    total: int | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    finished_at: str | None = None


class CollectionStatusResponse(BaseModel):
    # exactly snapshot_status_payload(store)["snapshot"] — dict passthrough,
    # None when no snapshot exists (contract §3)
    snapshot: dict | None = None
    collection_url: str
    sync: SyncStatusView
