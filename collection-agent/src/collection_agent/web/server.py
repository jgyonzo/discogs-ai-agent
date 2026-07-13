"""Web app composition (028, contracts/web-ui-api.md; research R1).

`create_web_app` calls the UNTOUCHED `scan.server.create_app` and
registers the chat/collection routes on the SAME app object — one
process, one port, one page. Every scan endpoint keeps its 022/026
contract verbatim; `/` keeps serving the (now tabbed) static page from
the scan package.

Write gate (amendment-017-agent-tools delta 12): the plan confirm route
is the second sanctioned runtime gate beside the CLI's y/N — it executes
ONLY the server-held WritePlan via the runtime-only `execute_plan`;
requests carry an id, never move data.

Secrets: nothing in any response (022 FR-017 discipline carries over).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from collection_agent.models import Completeness
from collection_agent.scan.server import create_app as create_scan_app
from collection_agent.scan.session import ScanSession
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.tools.base import snapshot_status_payload
from collection_agent.tools.common import collection_page_url
from collection_agent.web.chat import ChatBusyError, PlanGateError, TurnFailedError, WebChat
from collection_agent.web.models import (
    ChatRequest,
    CollectionStatusResponse,
    PlanActionRequest,
)
from collection_agent.web.syncrun import SyncRunner


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    # same envelope as scan.server (contract §"error envelope")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def create_web_app(
    settings: Settings,
    llm_client: Any,
    discogs_client: Any,
    store: SnapshotStore,
    scan_session: ScanSession,
    username: str,
    web_chat: WebChat,
    sync_runner: SyncRunner,
) -> FastAPI:
    app = create_scan_app(
        settings=settings,
        llm_client=llm_client,
        discogs_client=discogs_client,
        store=store,
        session=scan_session,
        username=username,
    )

    def _snapshot_state() -> str:
        snap = store.load()
        return snap.meta.completeness.value if snap else "missing"

    # -- chat (contract §2) ----------------------------------------------------

    @app.post("/api/chat")
    def chat(req: ChatRequest):
        text = req.text.strip()
        if not text:
            return _error(400, "empty_message", "Type a message first.")
        try:
            return web_chat.run_turn(text)
        except ChatBusyError:
            return _error(
                409,
                "chat_busy",
                "A turn is already being answered — wait for it to finish.",
            )
        except TurnFailedError as exc:
            return _error(
                502,
                "chat_error",
                f"That turn failed and was not kept: {exc}. Try again.",
            )

    @app.get("/api/chat/history")
    def chat_history():
        return web_chat.history(snapshot_state=_snapshot_state())

    @app.post("/api/chat/plan/confirm")
    def plan_confirm(req: PlanActionRequest):
        try:
            return web_chat.confirm_plan(req.plan_id)
        except ChatBusyError:
            return _error(
                409, "chat_busy", "A turn is running — try again when it finishes."
            )
        except PlanGateError as exc:
            return _error(409, exc.code, exc.message)

    @app.post("/api/chat/plan/cancel")
    def plan_cancel(req: PlanActionRequest):
        try:
            web_chat.cancel_plan(req.plan_id)
        except ChatBusyError:
            return _error(
                409, "chat_busy", "A turn is running — try again when it finishes."
            )
        except PlanGateError as exc:
            return _error(409, exc.code, exc.message)
        return {"status": "cancelled"}

    # -- collection status + sync (contract §3) ---------------------------------

    @app.get("/api/collection/status")
    def collection_status() -> CollectionStatusResponse:
        payload = snapshot_status_payload(store)
        return CollectionStatusResponse(
            snapshot=payload.get("snapshot"),
            collection_url=collection_page_url(settings, username),
            sync=sync_runner.status(),
        )

    @app.post("/api/sync")
    def trigger_sync():
        if not sync_runner.start():
            return _error(
                409,
                "sync_already_running",
                "A sync is already running — progress is on the Collection tab.",
            )
        return JSONResponse(status_code=202, content={"status": "started"})

    return app
