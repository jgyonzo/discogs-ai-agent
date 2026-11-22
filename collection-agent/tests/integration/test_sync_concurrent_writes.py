"""028 replay addendum 4 (T031): a live write landing mid-sync never yields
a `complete` snapshot (FR-017; contracts/amendment-017-snapshot-schema.md).

Owner incident 2026-11-20: a scan add during a page sync was overwritten by
the sync's final save — built from the pre-add instance listing — which
claimed `complete`. The live write is simulated at the exact store seam the
scan add (`mark_stale`) and chat moves (`patch_moved_instances`) use, fired
from inside the enrichment pass (i.e. after the instance pass already ran).
No live API — FakeDiscogsClient at the interface level."""

from __future__ import annotations

from collections.abc import Callable

from collection_agent.models import Completeness
from collection_agent.snapshot.sync import run_sync
from tests.conftest import make_record, make_snapshot
from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient

CAUSE = "during this sync"  # stable fragment of the cause warning


class MidEnrichmentWriteClient(FakeDiscogsClient):
    """Fires `hook` (a live write) once, right after the Nth release fetch."""

    def __init__(self, hook: Callable[[], None], after_fetches: int = 1, **kw):
        super().__init__(**kw)
        self._hook = hook
        self._after = after_fetches
        self._fired = False

    def get_release(self, release_id):
        detail = super().get_release(release_id)
        if not self._fired and len(self.release_fetches) >= self._after:
            self._fired = True
            self._hook()
        return detail


def collection_with_new_add():
    """Discogs as listed AFTER the owner's add: default collection + 105."""
    instances, details = payloads.default_collection()
    instances = instances + [
        payloads.instance(9006, 105, "Scanned Mid-Sync", "New Artist")
    ]
    details = {**details, 105: payloads.release_detail(105)}
    return instances, details


def test_add_during_enrichment_ends_stale_with_warning_and_kept_journal(
    settings, store
):
    store.save(make_snapshot([make_record(1)]))  # an existing complete snapshot
    notified: list[str] = []

    meta = run_sync(
        MidEnrichmentWriteClient(store.mark_stale), store, settings,
        notify=notified.append,
    )

    assert meta.completeness == Completeness.STALE
    assert store.load().meta.completeness == Completeness.STALE  # persisted
    assert meta.enriched_count == meta.unique_release_count == 4  # enrichment finished
    assert any(CAUSE in w for w in meta.sync_stats.warnings)
    assert any(CAUSE in m for m in notified)  # terminal + page see it live
    assert store.journal_path.exists()  # kept ⇒ the follow-up sync is quick


def test_move_during_enrichment_ends_stale(settings, store):
    store.save(make_snapshot([make_record(9001, release_id=101, folder_id=3)]))

    meta = run_sync(
        MidEnrichmentWriteClient(lambda: store.patch_moved_instances([(9001, 1)])),
        store, settings,
    )

    assert meta.completeness == Completeness.STALE
    assert store.load().meta.completeness == Completeness.STALE
    assert store.journal_path.exists()


def test_add_during_first_ever_sync_ends_stale(settings, store):
    assert store.load() is None

    meta = run_sync(MidEnrichmentWriteClient(store.mark_stale), store, settings)

    assert meta.completeness == Completeness.STALE


def test_write_before_sync_started_is_not_a_false_positive(settings, store):
    store.save(make_snapshot([make_record(1)]))
    store.mark_stale()  # the SC-003 order: add first, then sync

    meta = run_sync(FakeDiscogsClient(), store, settings)

    assert meta.completeness == Completeness.COMPLETE
    assert not any(CAUSE in w for w in meta.sync_stats.warnings)
    assert not store.journal_path.exists()  # cleared on complete, as before


def test_concurrent_write_plus_failed_enrichment_stays_partial(settings, store):
    meta = run_sync(
        MidEnrichmentWriteClient(store.mark_stale, release_failures={104: "5xx"}),
        store, settings,
    )

    assert meta.completeness == Completeness.PARTIAL  # the stronger warning wins
    assert any(CAUSE in w for w in meta.sync_stats.warnings)
    assert store.journal_path.exists()


def test_follow_up_sync_enriches_only_the_new_release_and_completes(
    settings, store
):
    store.save(make_snapshot([make_record(1)]))
    first = run_sync(MidEnrichmentWriteClient(store.mark_stale), store, settings)
    assert first.completeness == Completeness.STALE

    instances, details = collection_with_new_add()
    second_client = FakeDiscogsClient(instances=instances, details=details)
    second = run_sync(second_client, store, settings)

    assert second.completeness == Completeness.COMPLETE
    assert second_client.release_fetches == [105]  # journal reused: quick
    assert any(r.release_id == 105 for r in store.load().records)
    assert not store.journal_path.exists()
