"""Snapshot serving guard shared by every read tool (contracts/agent-tools.md §1).

Serving rules (FR-003b/c, US1 scenario 8, edge case №1):
- no snapshot        → blocked: "sync required" signal
- synced but empty   → blocked: explicit empty-collection signal (never a
                       zero-bucket distribution / division by zero)
- partial            → served WITH a partial-data warning on every result
- stale              → served with a staleness note (age disclosed)
- complete           → served; age available on request
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from collection_agent.models import CollectionRecord, Completeness, Snapshot
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore


@dataclass
class ServeContext:
    snapshot: Snapshot | None
    warnings: list[str] = field(default_factory=list)
    blocked: dict[str, Any] | None = None  # tool must return this verbatim


def load_for_serving(store: SnapshotStore) -> ServeContext:
    snap = store.load()
    if snap is None:
        return ServeContext(
            snapshot=None,
            blocked={
                "error": "sync_required",
                "detail": "No collection snapshot exists yet. Offer to run a "
                "sync (start_sync) — it reads the whole collection from "
                "Discogs and takes minutes.",
            },
        )
    if snap.meta.instance_count == 0 or not snap.records:
        return ServeContext(
            snapshot=snap,
            blocked={
                "error": "empty_collection",
                "detail": "The synced collection contains 0 records. Explain "
                "that there is nothing to analyze (the account's collection "
                "is empty or not visible to this token) — do not present "
                "zero-valued statistics.",
            },
        )

    warnings: list[str] = []
    age = _age_hours(store)
    if snap.meta.completeness == Completeness.PARTIAL:
        warnings.append(
            f"snapshot is PARTIAL ({snap.meta.enriched_count}/"
            f"{snap.meta.unique_release_count} releases enriched) — results "
            "may be incomplete; recommend finishing the sync"
        )
    elif snap.meta.completeness == Completeness.STALE:
        warnings.append(
            f"snapshot is STALE (synced {age}h ago; the collection changed "
            "since) — recommend a refresh"
        )
    return ServeContext(snapshot=snap, warnings=warnings)


def _age_hours(store: SnapshotStore) -> float | None:
    age = store.sync_age()
    return round(age.total_seconds() / 3600, 1) if age else None


def release_page_url(settings: Settings, record: CollectionRecord) -> str:
    """The record's Discogs release-page URL (019, agent-tools deltas 6–8).

    Built from `release_id` (sync instance pass — present in every snapshot
    state), NEVER `instance_id`: the two live in different id spaces, and
    pasting an instance id into this path was exactly the 018-replay
    invented-URL incident. Every listing entry carries this field so the
    LLM never constructs a URL itself (ground rule 1).
    """
    return f"{settings.discogs_web_base_url.rstrip('/')}/release/{record.release_id}"


def with_warnings(ctx: ServeContext, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach serving warnings to a tool payload (relayed by the LLM per the
    system prompt's ground rule 2)."""
    if ctx.warnings:
        payload["warnings"] = [*ctx.warnings, *payload.get("warnings", [])]
    return payload
