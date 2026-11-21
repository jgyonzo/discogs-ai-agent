"""028 replay addendum 4 (T030): the live-write marker + per-path write lock.

FR-017 / contracts/amendment-017-snapshot-schema.md: every snapshot-
affecting live write bumps a durable marker beside the snapshot (so a
running sync — this process or another — can tell a write landed after
its instance pass), and the store's read-modify-write paths are
serialized with the sync's final compare-and-save."""

from __future__ import annotations

import threading

from collection_agent.models import Completeness
from collection_agent.snapshot.store import SnapshotStore
from tests.conftest import make_record, make_snapshot


def test_marker_absent_until_a_live_write(store):
    assert store.live_write_marker() is None
    assert not store.live_writes_path.exists()


def test_marker_lives_beside_the_snapshot(store):
    assert store.live_writes_path.parent == store.path.parent
    assert store.live_writes_path.name == store.path.name + ".live-writes"


def test_mark_stale_bumps_marker(store, complete_snapshot):
    store.save(complete_snapshot)
    store.mark_stale()
    first = store.live_write_marker()
    assert first
    store.mark_stale()  # already stale: still a live write ⇒ still a bump
    assert store.live_write_marker() not in (None, first)


def test_patch_bumps_marker_and_still_stays_complete_without_a_sync(
    store, complete_snapshot
):
    store.save(complete_snapshot)
    store.patch_moved_instances([(1, 3)])
    assert store.live_write_marker()
    # unchanged pre-028 semantics: patched in place, stays complete
    assert store.load().meta.completeness == Completeness.COMPLETE


def test_writes_bump_marker_even_without_a_snapshot(store):
    """An add during the very first sync must still be detectable."""
    assert store.load() is None
    store.mark_stale()
    after_add = store.live_write_marker()
    assert after_add
    store.patch_moved_instances([(1, 3)])
    assert store.live_write_marker() not in (None, after_add)
    assert store.load() is None  # still no snapshot fabricated


def test_marker_is_shared_across_store_instances(settings, complete_snapshot):
    a = SnapshotStore(settings.snapshot_path)
    b = SnapshotStore(settings.snapshot_path)
    a.save(complete_snapshot)
    a.mark_stale()
    assert b.live_write_marker() == a.live_write_marker()


def test_write_lock_is_per_path_and_shared_across_instances(settings, tmp_path):
    a = SnapshotStore(settings.snapshot_path)
    b = SnapshotStore(settings.snapshot_path)
    other = SnapshotStore(tmp_path / "elsewhere" / "snapshot.json")
    assert a.write_lock() is b.write_lock()
    assert a.write_lock() is not other.write_lock()


def test_patch_blocked_on_lock_applies_over_the_fresher_snapshot(
    settings, complete_snapshot
):
    """The RMW interleaving the lock closes: a patch must never overwrite a
    snapshot written while it waited (e.g. the sync's final save)."""
    sync_side = SnapshotStore(settings.snapshot_path)
    chat_side = SnapshotStore(settings.snapshot_path)
    sync_side.save(complete_snapshot)

    fresh = make_snapshot(
        [make_record(1), make_record(99, release_id=999)]  # the sync's result
    )
    patcher = threading.Thread(
        target=chat_side.patch_moved_instances, args=([(1, 3)],)
    )
    with sync_side.write_lock():
        patcher.start()
        patcher.join(timeout=0.3)
        assert patcher.is_alive()  # blocked: the lock serializes the RMW
        sync_side.save(fresh)
    patcher.join(timeout=5)
    assert not patcher.is_alive()

    snap = sync_side.load()
    by_iid = {r.instance_id: r for r in snap.records}
    assert 99 in by_iid  # the fresher snapshot survived
    assert by_iid[1].folder_id == 3  # and the patch landed on top of it
