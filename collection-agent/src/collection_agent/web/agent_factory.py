"""Web chat agent construction (028; amendment-017-agent-tools delta 13).

Same registry, same model knob, same story tools as the terminal `chat`
runtime — the ONE deliberate difference is `start_sync`: the CLI variant
runs the sync inline in the turn (terminal progress bars); here it would
freeze the conversation for minutes and fight the single-occupancy rule,
so the web variant delegates NON-BLOCKING to the shared SyncRunner and
answers honestly (`started` / `already_running`). `full=true` is ignored
with a note: the web sync is standard-only (028 clarification
2026-07-12; `--full` stays terminal).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from collection_agent.agent import Agent, AgentSession, ToolDef
from collection_agent.registry import build_registry
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore

# deliberately the CLI tools' own schemas (same package): the web variant
# must present the LLM an IDENTICAL tool surface, only behavior differs
from collection_agent.tools.base import _NoArgs, _SyncArgs, snapshot_status_payload
from collection_agent.tools.registration import register_story_tools

from pydantic import BaseModel


def build_web_agent(
    settings: Settings,
    store: SnapshotStore,
    llm_client: Any,
    sync_starter: Callable[[], bool],
) -> Agent:
    """`sync_starter` is `SyncRunner.start` (True = a run began;
    False = one is already running)."""
    registry = build_registry(settings)
    agent = Agent(
        registry=registry,
        model=settings.collection_agent_model,
        llm_client=llm_client,
        session=AgentSession(),
    )

    def snapshot_status(_s: AgentSession, _a: BaseModel) -> dict[str, Any]:
        return snapshot_status_payload(store)

    def start_sync(_s: AgentSession, args: _SyncArgs) -> dict[str, Any]:
        payload: dict[str, Any]
        if sync_starter():
            payload = {
                "started": True,
                "detail": "Sync started in the background — progress is on "
                "the Collection tab. Answers reflect the fresh snapshot "
                "once it completes.",
            }
        else:
            payload = {
                "already_running": True,
                "detail": "A sync is already running — progress is on the "
                "Collection tab.",
            }
        if args.full:
            payload["note"] = (
                "full re-sync is not available from the web page; the "
                "standard sync ran instead (resume/refresh). Use the "
                "terminal `sync --full` for a full re-enrichment."
            )
        return payload

    agent.register(
        ToolDef(
            name="snapshot_status",
            description="Snapshot state: sync age, completeness, counts, folder "
            "list, collection value, and warnings. Use before answering when "
            "freshness matters, or when the user asks about sync state.",
            params_model=_NoArgs,
            fn=snapshot_status,
        )
    )
    agent.register(
        ToolDef(
            name="start_sync",
            description="Run or resume the collection sync from Discogs in the "
            "background (progress appears on the Collection tab; answers use "
            "the fresh snapshot once it completes). At most one sync runs at "
            "a time.",
            params_model=_SyncArgs,
            fn=start_sync,
        )
    )
    register_story_tools(agent, settings, store)
    return agent
