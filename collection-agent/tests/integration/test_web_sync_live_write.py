"""028 replay addendum 4 (T032): the owner incident, reproduced end to end.

2026-11-20, server session `20261120-214751Z`: a page sync was running; the
owner scanned and added a record (journaled `added`, 2 min into the sync);
the sync then saved its pre-add listing as `complete` — the record was on
Discogs, missing locally, and the snapshot claimed complete.

Here: the REAL `run_sync` runs in the SyncRunner thread and is held open
mid-enrichment (after its instance pass); `/api/search` → `/api/add` go
through the composed app (UNTOUCHED scan server, `mark_stale` seam) while
it waits. FR-017: the run must end `stale` (never `complete`), and a second
Sync — Discogs now listing the add — completes quickly with the record."""

from __future__ import annotations

import threading

from collection_agent.snapshot.sync import run_sync
from tests.conftest import make_record, make_snapshot
from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient
from tests.integration.test_web_app_composition import make_web_client

CAUSE = "during this sync"


class HeldOpenSyncClient(FakeDiscogsClient):
    """Pauses the enrichment pass after its first release fetch."""

    def __init__(self, reached: threading.Event, release: threading.Event, **kw):
        super().__init__(**kw)
        self._reached = reached
        self._release = release

    def get_release(self, release_id):
        detail = super().get_release(release_id)
        if len(self.release_fetches) == 1:
            self._reached.set()
            assert self._release.wait(timeout=5), "test never released the sync"
        return detail


def listing_after_add():
    instances, details = payloads.default_collection()
    instances = instances + [
        payloads.instance(9006, 555, "Scanned Mid-Sync", "New Artist")
    ]
    return instances, {**details, 555: payloads.release_detail(555)}


def test_scan_add_during_page_sync_never_claims_complete(settings, store):
    reached, release = threading.Event(), threading.Event()
    instances, details = listing_after_add()
    sync_clients = [
        HeldOpenSyncClient(reached, release),             # run 1: pre-add listing
        FakeDiscogsClient(instances=instances, details=details),  # run 2
    ]
    runs: list[FakeDiscogsClient] = []

    def real_sync(_client, st, se, full, on_progress, notify):
        client = sync_clients[len(runs)]
        runs.append(client)
        return run_sync(client, st, se, full=full,
                        on_progress=on_progress, notify=notify)

    client, discogs, _, runner, _, _ = make_web_client(
        settings, store,
        snapshot=make_snapshot([make_record(1, release_id=101)]),
        run_sync_fn=real_sync,
        search_responses={"q": payloads.search_page([payloads.search_result(555)])},
    )

    # --- run 1: the incident --------------------------------------------------
    assert client.post("/api/sync").status_code == 202
    assert reached.wait(timeout=5)  # instance pass done; enrichment under way
    assert client.get("/api/collection/status").json()["sync"]["state"] == "running"

    found = client.get("/api/search", params={"q": "scanned mid-sync"}).json()
    add = client.post(
        "/api/add",
        json={"scan_id": found["scan_id"], "release_id": 555,
              "confirm_duplicate": False},
    )
    assert add.status_code == 200 and add.json()["status"] == "added"
    assert discogs.adds  # the live write really happened

    release.set()
    runner.join(timeout=5)

    status = client.get("/api/collection/status").json()
    assert status["sync"]["state"] == "stale"
    assert any(CAUSE in w for w in status["sync"]["warnings"])
    assert status["snapshot"]["completeness"] == "stale"  # the bug said "complete"
    assert all(r.release_id != 555 for r in store.load().records)  # honest: flagged

    # --- run 2: Sync again — Discogs now lists the add ---------------------------
    assert client.post("/api/sync").status_code == 202
    runner.join(timeout=5)

    status = client.get("/api/collection/status").json()
    assert status["sync"]["state"] == "complete"
    assert status["snapshot"]["completeness"] == "complete"
    assert runs[1].release_fetches == [555]  # kept journal ⇒ only the new release
    assert any(r.release_id == 555 for r in store.load().records)
