"""028 replay addendum 5 (T036): the owner's SC-004 observation, end to end.

Same server run: scan-add a record → page Sync (its snapshot now holds the
add's instance) → scan the same record again. FR-018: the badge counts
the one owned copy once ("1 copy (incl. this session)", not 2) — and the
duplicate double-confirm gate still fires on a re-add (unchanged)."""

from __future__ import annotations

from tests.conftest import make_record, make_snapshot
from tests.fixtures import discogs_payloads as payloads
from tests.integration.test_web_app_composition import make_web_client


def test_synced_session_add_counts_once_and_gate_still_fires(settings, store):
    added: dict[str, int] = {}

    def scripted_sync(client, st, se, full, on_progress, notify):
        # Discogs now lists the add under the instance id it returned
        fresh = make_snapshot([
            make_record(1, release_id=101),
            make_record(added["instance_id"], release_id=555),
        ])
        st.save(fresh)
        return fresh.meta

    client, discogs, _, runner, _, _ = make_web_client(
        settings, store,
        snapshot=make_snapshot([make_record(1, release_id=101)]),
        run_sync_fn=scripted_sync,
        search_responses={"q": payloads.search_page([payloads.search_result(555)])},
    )

    first = client.get("/api/search", params={"q": "new record"}).json()
    assert first["candidates"][0]["duplicate"]["state"] == "not_in_collection"
    add = client.post(
        "/api/add",
        json={"scan_id": first["scan_id"], "release_id": 555,
              "confirm_duplicate": False},
    ).json()
    assert add["status"] == "added"
    added["instance_id"] = add["instance_id"]

    assert client.post("/api/sync").status_code == 202
    runner.join(timeout=5)
    assert client.get("/api/collection/status").json()["sync"]["state"] == "complete"

    again = client.get("/api/search", params={"q": "same record again"}).json()
    dup = again["candidates"][0]["duplicate"]
    assert dup["state"] == "in_collection"
    assert dup["copies"] == 1  # the bug showed 2 for one owned copy
    assert dup["added_this_session"] is True

    # safety unchanged: a re-add still needs the explicit duplicate confirm
    readd = client.post(
        "/api/add",
        json={"scan_id": again["scan_id"], "release_id": 555,
              "confirm_duplicate": False},
    ).json()
    assert readd["status"] == "needs_duplicate_confirmation"
    assert len(discogs.adds) == 1  # nothing written by the unconfirmed re-add
