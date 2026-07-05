"""Pydantic entities for the collection agent (see specs/017 data-model.md).

Normalization rules from the data model / snapshot contract:
- Discogs uses 0 for "unrated" and "unknown year" → stored as None.
- Missing data is None / [] — never 0, "", or a guessed value.
- Multi-valued fields are lists, never comma-joined strings.
- Derived values (decade, scarcity, percentages) are NEVER persisted;
  the attribute registry computes them at read time.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = 1


class MediaLink(BaseModel):
    uri: str  # stored/returned verbatim — signed URLs must not be edited
    title: str | None = None
    duration_s: int | None = None


class LabelRef(BaseModel):
    name: str
    catno: str | None = None


class CollectionRecord(BaseModel):
    """One entry per collection INSTANCE (clarification Q4: every copy counts)."""

    # instance pass
    instance_id: int
    release_id: int
    folder_id: int
    date_added: str | None = None
    my_rating: int | None = None  # 1–5; Discogs 0 (unrated) → None
    title: str
    artists: list[str] = Field(default_factory=list)
    year: int | None = None  # Discogs 0 → None
    labels: list[LabelRef] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)

    # enrichment pass (GET /releases/{id}); null/[] until enriched
    genres: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    country: str | None = None
    community_have: int | None = None
    community_want: int | None = None
    community_rating_avg: float | None = None
    community_rating_count: int | None = None
    num_for_sale: int | None = None
    lowest_price: float | None = None
    videos: list[MediaLink] = Field(default_factory=list)
    enriched_at: str | None = None  # None ⇒ not yet enriched

    @field_validator("my_rating", mode="before")
    @classmethod
    def _zero_rating_is_null(cls, v):
        return None if v in (0, "0") else v

    @field_validator("year", mode="before")
    @classmethod
    def _zero_year_is_null(cls, v):
        return None if v in (0, "0") else v


class Folder(BaseModel):
    folder_id: int  # 0 = "All" (virtual; invalid move target), 1 = "Uncategorized" (valid)
    name: str
    count: int = 0


class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"


class CollectionValue(BaseModel):
    # verbatim Discogs currency strings; basis is always "Discogs estimate"
    minimum: str | None = None
    median: str | None = None
    maximum: str | None = None


class SyncStats(BaseModel):
    requests: int = 0
    duration_s: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class SnapshotMeta(BaseModel):
    schema_version: int = SCHEMA_VERSION
    username: str
    synced_at: str  # ISO-8601 UTC
    completeness: Completeness = Completeness.PARTIAL
    instance_count: int = 0
    unique_release_count: int = 0
    enriched_count: int = 0
    collection_value: CollectionValue = Field(default_factory=CollectionValue)
    sync_stats: SyncStats = Field(default_factory=SyncStats)


class Snapshot(BaseModel):
    meta: SnapshotMeta
    folders: list[Folder] = Field(default_factory=list)
    records: list[CollectionRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_instance_ids_unique(self):
        ids = [r.instance_id for r in self.records]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate instance_id(s) in snapshot: {dupes[:5]}")
        return self


# --- Write path (session-scoped, never persisted — data-model §5) ---


class PlannedMove(BaseModel):
    instance_id: int
    release_id: int
    display: str  # "Artist – Title"
    from_folder_id: int
    result: Literal["pending", "ok", "failed"] = "pending"
    error: str | None = None


class TargetFolder(BaseModel):
    folder_id: int | None = None  # None ⇒ to be created
    name: str
    create: bool = False


class PlanState(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class WritePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_folder: TargetFolder
    moves: list[PlannedMove] = Field(default_factory=list)
    state: PlanState = PlanState.PROPOSED
