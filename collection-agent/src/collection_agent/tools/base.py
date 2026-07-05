"""Base tools available from the first CLI boot: snapshot_status, start_sync.

(The analytics/browse/media/organize tools are registered by their own
modules; see contracts/agent-tools.md §1–§2.)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from collection_agent.agent import AgentSession, ToolDef
from collection_agent.models import SnapshotMeta
from collection_agent.snapshot.store import SnapshotStore


class _NoArgs(BaseModel):
    pass


class _SyncArgs(BaseModel):
    full: bool = False


def snapshot_status_payload(store: SnapshotStore) -> dict[str, Any]:
    snap = store.load()
    if snap is None:
        return {
            "snapshot": None,
            "warning": "no snapshot exists — a sync is required before any "
            "collection question can be answered",
        }
    age = store.sync_age()
    return {
        "snapshot": {
            "username": snap.meta.username,
            "synced_at": snap.meta.synced_at,
            "age_hours": round(age.total_seconds() / 3600, 1) if age else None,
            "completeness": snap.meta.completeness.value,
            "instance_count": snap.meta.instance_count,
            "unique_release_count": snap.meta.unique_release_count,
            "enriched_count": snap.meta.enriched_count,
            "collection_value": snap.meta.collection_value.model_dump(),
            "warnings": snap.meta.sync_stats.warnings,
            "folders": [
                {"folder_id": f.folder_id, "name": f.name, "count": f.count}
                for f in snap.folders
            ],
        }
    }


def make_base_tools(
    store: SnapshotStore, sync_runner: Callable[[bool], SnapshotMeta]
) -> list[ToolDef]:
    def snapshot_status(_s: AgentSession, _a: BaseModel) -> dict[str, Any]:
        return snapshot_status_payload(store)

    def start_sync(_s: AgentSession, args: _SyncArgs) -> dict[str, Any]:
        meta = sync_runner(args.full)
        return {
            "synced": True,
            "completeness": meta.completeness.value,
            "instance_count": meta.instance_count,
            "unique_release_count": meta.unique_release_count,
            "warnings": meta.sync_stats.warnings,
            "duration_s": meta.sync_stats.duration_s,
        }

    return [
        ToolDef(
            name="snapshot_status",
            description="Snapshot state: sync age, completeness, counts, folder "
            "list, collection value, and warnings. Use before answering when "
            "freshness matters, or when the user asks about sync state.",
            params_model=_NoArgs,
            fn=snapshot_status,
        ),
        ToolDef(
            name="start_sync",
            description="Run or resume the collection sync from Discogs (may take "
            "minutes; progress shows in the terminal). full=true re-enriches "
            "every release instead of reusing prior results.",
            params_model=_SyncArgs,
            fn=start_sync,
        ),
    ]
