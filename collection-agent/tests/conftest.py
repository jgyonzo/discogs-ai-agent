"""Shared fixtures: isolated Settings (never reads the real .env), snapshot
stores on tmp paths, and prebuilt complete/partial/stale snapshots."""

from __future__ import annotations

import pytest

from collection_agent.models import (
    CollectionRecord,
    CollectionValue,
    Completeness,
    Folder,
    MediaLink,
    Snapshot,
    SnapshotMeta,
    SyncStats,
)
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore


@pytest.fixture()
def settings(tmp_path) -> Settings:
    """Isolated settings: dummy token, tmp snapshot path, no .env file read."""
    return Settings(
        _env_file=None,
        DISCOGS_USER_TOKEN="test-token-not-real",
        SNAPSHOT_PATH=tmp_path / "snapshot.json",
    )


@pytest.fixture()
def store(settings) -> SnapshotStore:
    return SnapshotStore(settings.snapshot_path)


def make_record(
    instance_id: int,
    release_id: int | None = None,
    title: str = "Test Record",
    artist: str = "Test Artist",
    year: int | None = 1995,
    folder_id: int = 1,
    genres: list[str] | None = None,
    styles: list[str] | None = None,
    labels: list[str] | None = None,
    country: str | None = "Germany",
    my_rating: int | None = None,
    community_have: int | None = 100,
    community_want: int | None = 50,
    community_rating_avg: float | None = 4.0,
    community_rating_count: int | None = 25,
    num_for_sale: int | None = 5,
    lowest_price: float | None = 10.0,
    videos: list[MediaLink] | None = None,
    enriched: bool = True,
) -> CollectionRecord:
    from collection_agent.models import LabelRef

    return CollectionRecord(
        instance_id=instance_id,
        release_id=release_id or instance_id,
        folder_id=folder_id,
        title=title,
        artists=[artist],
        year=year,
        my_rating=my_rating,
        genres=genres if genres is not None else ["Electronic"],
        styles=styles if styles is not None else ["Techno"],
        labels=[LabelRef(name=n) for n in (labels or ["Test Label"])],
        formats=["Vinyl", '12"'],
        country=country,
        community_have=community_have,
        community_want=community_want,
        community_rating_avg=community_rating_avg,
        community_rating_count=community_rating_count,
        num_for_sale=num_for_sale,
        lowest_price=lowest_price,
        videos=videos if videos is not None else [],
        enriched_at="2026-07-05T12:00:00Z" if enriched else None,
    )


def make_snapshot(
    records: list[CollectionRecord],
    completeness: Completeness = Completeness.COMPLETE,
    username: str = "test_user",
) -> Snapshot:
    unique = {r.release_id for r in records}
    return Snapshot(
        meta=SnapshotMeta(
            username=username,
            synced_at="2026-07-05T12:00:00Z",
            completeness=completeness,
            instance_count=len(records),
            unique_release_count=len(unique),
            enriched_count=len(unique),
            collection_value=CollectionValue(
                minimum="US$100.00", median="US$250.00", maximum="US$400.00"
            ),
            sync_stats=SyncStats(requests=10, duration_s=5.0),
        ),
        folders=[
            Folder(folder_id=0, name="All", count=len(records)),
            Folder(folder_id=1, name="Uncategorized", count=0),
            Folder(folder_id=3, name="Techno", count=0),
        ],
        records=records,
    )


@pytest.fixture()
def complete_snapshot() -> Snapshot:
    return make_snapshot(
        [
            make_record(1, genres=["Electronic"], styles=["Minimal"], year=2005,
                        my_rating=4, videos=[MediaLink(uri="https://youtu.be/a", title="A")]),
            make_record(2, genres=["Electronic"], year=2011, country="Canada",
                        community_have=40, community_want=200, num_for_sale=0,
                        lowest_price=None, community_rating_avg=4.8,
                        community_rating_count=12),
            make_record(3, genres=["Jazz"], styles=["Hard Bop"], year=1974,
                        country="US", labels=["Blue Note"], community_have=2000,
                        community_want=5000, num_for_sale=1, lowest_price=150.0,
                        community_rating_avg=4.9, community_rating_count=800),
            make_record(4, release_id=1, genres=["Electronic"], styles=["Minimal"],
                        year=2005),  # duplicate copy of release 1
            make_record(5, genres=[], year=None, country=None, community_have=None,
                        community_want=None, community_rating_avg=None,
                        community_rating_count=None, num_for_sale=None,
                        lowest_price=None),  # missing-everything record
        ]
    )


@pytest.fixture()
def partial_snapshot(complete_snapshot) -> Snapshot:
    snap = complete_snapshot.model_copy(deep=True)
    snap.meta.completeness = Completeness.PARTIAL
    snap.meta.enriched_count = 2
    return snap


@pytest.fixture()
def stale_snapshot(complete_snapshot) -> Snapshot:
    snap = complete_snapshot.model_copy(deep=True)
    snap.meta.completeness = Completeness.STALE
    return snap
