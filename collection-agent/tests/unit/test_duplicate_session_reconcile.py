"""028 replay addendum 5 (T035): the duplicate overlay counts each owned
copy once (FR-018; amendment-022-scan-api-4.md delta).

Owner observation 2026-11-21 (SC-004): after add → same-process page Sync
→ scan the same record again, the badge read "2 copies (incl. this
session)" for ONE owned copy — the snapshot already held the add's
instance and the session counted it again. Reconciliation is exact: a
session add is absorbed iff the `instance_id` Discogs returned for it is
a snapshot record's instance_id. Real ScanSession here (its log carries
the instance ids); 022's log-less-fake tests stay the conservative pin."""

from __future__ import annotations

from collection_agent.models import Completeness
from collection_agent.scan.journal import ScanJournal
from collection_agent.scan.search import snapshot_duplicate_checker
from collection_agent.scan.session import ScanSession
from tests.conftest import make_record, make_snapshot


def session_with_adds(settings, adds):
    """adds: list of (release_id, instance_id | None) recorded as the
    server's add handler does (record_outcome "added" + record_add)."""
    session = ScanSession(ScanJournal(settings.scan_journal_dir, "20261121-120000Z"))
    for release_id, instance_id in adds:
        scan_id = session.next_scan_id()
        session.record_outcome(
            scan_id, "added", "photo", release_id=release_id,
            instance_id=instance_id,
        )
        session.record_add(release_id)
    return session


def test_add_absorbed_by_a_later_sync_is_counted_once(settings, store):
    # the owner case: one copy, added this run, then synced into the snapshot
    session = session_with_adds(settings, [(555, 7001)])
    store.save(make_snapshot([make_record(1), make_record(7001, release_id=555)]))

    dup = snapshot_duplicate_checker(store, session)(555)

    assert dup.state == "in_collection"
    assert dup.copies == 1  # was 2: snapshot 1 + the same add again
    assert dup.added_this_session is True


def test_add_not_yet_in_the_snapshot_still_stacks(settings, store):
    session = session_with_adds(settings, [(555, 7001)])
    stale = make_snapshot(
        [make_record(1), make_record(6000, release_id=555)],  # an older copy
        completeness=Completeness.STALE,
    )
    store.save(stale)

    dup = snapshot_duplicate_checker(store, session)(555)

    assert dup.copies == 2  # older copy in snapshot + this run's add (not synced)
    assert dup.added_this_session is True


def test_two_adds_one_absorbed_counts_snapshot_plus_the_other(settings, store):
    # synced after the first add only (e.g. the second landed mid-sync)
    session = session_with_adds(settings, [(555, 7001), (555, 7002)])
    store.save(make_snapshot([make_record(7001, release_id=555)]))

    dup = snapshot_duplicate_checker(store, session)(555)

    assert dup.copies == 2  # 7001 (snapshot) + 7002 (session, not yet synced)


def test_add_with_unknown_instance_id_stays_counted(settings, store):
    """Discogs response without instance_id ⇒ cannot reconcile ⇒ the
    conservative pre-fix arithmetic (may over-count, never under-count)."""
    session = session_with_adds(settings, [(555, None)])
    store.save(make_snapshot([make_record(7001, release_id=555)]))

    dup = snapshot_duplicate_checker(store, session)(555)

    assert dup.copies == 2
    assert dup.added_this_session is True


def test_reconciliation_is_per_release(settings, store):
    # one release's adds never affect another release's status
    session = session_with_adds(settings, [(555, 7001)])
    store.save(make_snapshot([make_record(7001, release_id=555)]))
    check = snapshot_duplicate_checker(store, session)

    assert check(1).state == "not_in_collection"  # untouched release
    assert check(555).copies == 1
