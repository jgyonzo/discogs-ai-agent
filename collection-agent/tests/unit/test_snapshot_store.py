"""SnapshotStore: atomicity, journal round-trip, state transitions,
partial-never-complete, instance uniqueness (T014)."""

from __future__ import annotations

import json

import pytest

from collection_agent.models import Completeness, Snapshot
from collection_agent.snapshot.store import SnapshotStore
from tests.conftest import make_record, make_snapshot


def test_save_and_load_round_trip(store, complete_snapshot):
    store.save(complete_snapshot)
    loaded = store.load()
    assert loaded is not None
    assert loaded.meta.instance_count == 5
    assert loaded.records[0].instance_id == 1
    assert loaded.meta.completeness == Completeness.COMPLETE


def test_atomic_write_leaves_no_tmp(store, complete_snapshot):
    store.save(complete_snapshot)
    leftovers = list(store.path.parent.glob("*.tmp"))
    assert leftovers == []


def test_save_survives_preexisting_torn_tmp(store, complete_snapshot):
    """A crash that left a garbage tmp file must not break the next save."""
    store.path.parent.mkdir(parents=True, exist_ok=True)
    tmp = store.path.with_name(store.path.name + ".tmp")
    tmp.write_text("{ torn json", encoding="utf-8")
    store.save(complete_snapshot)
    assert store.load() is not None


def test_load_missing_returns_none(store):
    assert store.load() is None
    assert store.sync_age() is None


def test_journal_round_trip(store):
    journal = {101: {"country": "UK"}, 102: {"_404": True}}
    store.save_journal(journal)
    assert store.load_journal() == journal  # int keys restored
    store.clear_journal()
    assert store.load_journal() == {}


def test_torn_journal_treated_as_empty(store):
    store.journal_path.parent.mkdir(parents=True, exist_ok=True)
    store.journal_path.write_text("{ not json", encoding="utf-8")
    assert store.load_journal() == {}


def test_mark_stale_flips_only_complete(store, complete_snapshot, partial_snapshot):
    store.save(partial_snapshot)
    store.mark_stale()
    assert store.load().meta.completeness == Completeness.PARTIAL  # unchanged

    store.save(complete_snapshot)
    store.mark_stale()
    assert store.load().meta.completeness == Completeness.STALE


def test_partial_meta_is_preserved_verbatim(store, partial_snapshot):
    """The store must never silently upgrade a partial snapshot."""
    store.save(partial_snapshot)
    raw = json.loads(store.path.read_text())
    assert raw["meta"]["completeness"] == "partial"


def test_duplicate_instance_ids_rejected():
    records = [make_record(1), make_record(1)]
    with pytest.raises(ValueError, match="duplicate instance_id"):
        make_snapshot(records)


def test_patch_moved_instances(store, complete_snapshot):
    store.save(complete_snapshot)
    store.patch_moved_instances([(1, 3), (4, 3)])
    snap = store.load()
    moved = {r.instance_id: r.folder_id for r in snap.records}
    assert moved[1] == 3 and moved[4] == 3
    assert snap.meta.completeness == Completeness.COMPLETE  # patched in place
    techno = next(f for f in snap.folders if f.folder_id == 3)
    assert techno.count == 2


def test_patch_with_new_folder_adds_it(store, complete_snapshot):
    store.save(complete_snapshot)
    store.patch_moved_instances([(2, 42)], new_folder=(42, "New Crate"))
    snap = store.load()
    assert any(f.folder_id == 42 and f.name == "New Crate" for f in snap.folders)
