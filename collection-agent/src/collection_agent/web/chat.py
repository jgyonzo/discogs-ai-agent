"""Server-held web conversation (028 US1; contracts/web-ui-api.md §2).

ONE WebChat per server process (accepted v1 limitation): a lock serializes
turns and plan actions (busy ⇒ 409, never queued/interleaved — FR-004),
a process-lived transcript is the UI's record of the conversation, and
the pending `WritePlan` stays parked on the `AgentSession` exactly as in
the terminal runtime.

Error hygiene (research R2, load-bearing): `Agent.run_turn` appends the
user message first and may append an assistant message carrying
`tool_calls` BEFORE the tool results exist; an LLM exception mid-loop
would leave `session.messages` in a shape the provider rejects on the
next request. The turn wrapper therefore REWINDS `session.messages` to
its pre-turn length on any exception — the failed turn is typed data in
the transcript, never poison in the LLM context.

Write gate (delta 12): `confirm_plan` is the second sanctioned runtime
gate — it executes ONLY the server-held plan via the runtime-only
`execute_plan`, with the same per-move live re-validation and per-item
results as the CLI's y/N path. The request carries an id, never moves.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from collection_agent.agent import Agent
from collection_agent.models import PlanState
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.web.models import (
    ChatEntry,
    ChatResponse,
    HistoryResponse,
    MoveOutcomeView,
    PendingPlanView,
    PlanConfirmResponse,
)


class ChatBusyError(Exception):
    """The conversation lock is held (a turn or plan action is running)."""


class TurnFailedError(Exception):
    """The turn raised; the session was rewound and stays usable."""


class PlanGateError(Exception):
    """A plan action was refused; nothing was executed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class WebChat:
    def __init__(
        self,
        agent: Agent,
        settings: Settings,
        store: SnapshotStore,
        client_factory: Callable[[], Any] | None = None,
    ):
        self.agent = agent
        self._settings = settings
        self._store = store
        self._client_factory = client_factory
        self._lock = threading.Lock()
        self.transcript: list[ChatEntry] = []

    # -- views -------------------------------------------------------------------

    def pending_plan_view(self) -> PendingPlanView | None:
        plan = self.agent.session.pending_plan
        if plan is None or plan.state != PlanState.PROPOSED:
            return None
        target = plan.target_folder.name + (
            " (new)" if plan.target_folder.create else ""
        )
        return PendingPlanView(
            plan_id=plan.plan_id,
            target_folder=target,
            move_count=len(plan.moves),
            moves=[m.display for m in plan.moves],
        )

    def history(self, snapshot_state: str) -> HistoryResponse:
        return HistoryResponse(
            entries=list(self.transcript),
            pending_plan=self.pending_plan_view(),
            snapshot_state=snapshot_state,
        )

    # -- turn ---------------------------------------------------------------------

    def run_turn(self, text: str) -> ChatResponse:
        if not self._lock.acquire(blocking=False):
            raise ChatBusyError
        try:
            session = self.agent.session
            if (
                session.pending_plan is not None
                and session.pending_plan.state == PlanState.PROPOSED
            ):
                # web analogue of the CLI's anything-but-y-cancels (FR-006)
                session.expire_pending_plan()
                self.transcript.append(
                    ChatEntry(
                        kind="plan_cancelled",
                        text="Pending move plan cancelled — a new message "
                        "arrived before it was confirmed.",
                    )
                )
            rewind_to = len(session.messages)
            self.transcript.append(ChatEntry(kind="user", text=text))
            try:
                reply = self.agent.run_turn(text)
            except Exception as exc:
                del session.messages[rewind_to:]  # research R2
                self.transcript.append(
                    ChatEntry(kind="error", text=f"That turn failed: {exc}")
                )
                raise TurnFailedError(str(exc)) from exc
            self.transcript.append(ChatEntry(kind="assistant", text=reply))
            return ChatResponse(reply=reply, pending_plan=self.pending_plan_view())
        finally:
            self._lock.release()

    # -- plan gate ------------------------------------------------------------------

    def _gate(self, plan_id: str):
        plan = self.agent.session.pending_plan
        if plan is None or plan.state != PlanState.PROPOSED:
            raise PlanGateError(
                "no_pending_plan",
                "No move plan is awaiting confirmation — nothing was executed.",
            )
        if plan.plan_id != plan_id:
            raise PlanGateError(
                "plan_mismatch",
                "That plan is no longer the pending one — nothing was executed.",
            )
        return plan

    def confirm_plan(self, plan_id: str) -> PlanConfirmResponse:
        if not self._lock.acquire(blocking=False):
            raise ChatBusyError
        try:
            plan = self._gate(plan_id)
            plan.state = PlanState.CONFIRMED
            from collection_agent.tools.organize import execute_plan

            results = execute_plan(
                plan,
                self._settings,
                self._store,
                client_factory=self._client_factory,
            )
            self.agent.session.pending_plan = None
            target = plan.target_folder.name
            moves = [
                MoveOutcomeView(
                    display=m.display,
                    result="ok" if m.result == "ok" else "failed",
                    error=m.error,
                )
                for m in results.moves
            ]
            ok = sum(1 for m in moves if m.result == "ok")
            self.transcript.append(
                ChatEntry(
                    kind="plan_result",
                    text=f"Moved {ok}/{len(moves)} record(s) to {target}",
                    moves=moves,
                )
            )
            return PlanConfirmResponse(target_folder=target, moves=moves)
        finally:
            self._lock.release()

    def cancel_plan(self, plan_id: str) -> None:
        if not self._lock.acquire(blocking=False):
            raise ChatBusyError
        try:
            plan = self._gate(plan_id)
            plan.state = PlanState.CANCELLED
            self.agent.session.pending_plan = None
            self.transcript.append(
                ChatEntry(
                    kind="plan_cancelled",
                    text="Move plan cancelled — nothing sent to Discogs.",
                )
            )
        finally:
            self._lock.release()
