"""028 T018: post-sync freshness is structural (research R6; FR-010).

In ONE app instance: a scripted sync atomically writes a fresh snapshot ⇒
the NEXT status read, chat snapshot answer, and scan duplicate check all
reflect it — no restart, no reload bus. This test is the guard against a
future SnapshotStore cache silently breaking the web contract."""

from __future__ import annotations

import json

from tests.conftest import make_record, make_snapshot
from tests.fixtures import discogs_payloads as payloads
from tests.integration.test_web_app_composition import make_web_client


def test_completed_sync_visible_to_status_chat_and_duplicate_check(settings, store):
    old = make_snapshot([make_record(1, release_id=101)])
    fresh = make_snapshot(
        [make_record(1, release_id=101), make_record(2, release_id=555)]
    )

    def scripted_sync(client, st, se, full, on_progress, notify):
        st.save(fresh)  # the real run_sync's final atomic write
        return fresh.meta

    client, discogs, _, runner, web_chat, _ = make_web_client(
        settings, store,
        snapshot=old,
        run_sync_fn=scripted_sync,
        chat_script=[("tool", "snapshot_status", {}), ("text", "2 unique releases")],
        search_responses={"q": payloads.search_page([payloads.search_result(555)])},
    )

    # before: 1 unique release; 555 is not a duplicate
    assert client.get("/api/collection/status").json()["snapshot"][
        "unique_release_count"
    ] == 1
    pre = client.get("/api/search", params={"q": "new record"}).json()
    assert pre["candidates"][0]["duplicate"]["state"] == "not_in_collection"

    assert client.post("/api/sync").status_code == 202
    runner.join(timeout=5)
    assert client.get("/api/collection/status").json()["sync"]["state"] == "complete"

    # status reflects the fresh snapshot, same process
    assert client.get("/api/collection/status").json()["snapshot"][
        "unique_release_count"
    ] == 2

    # chat's snapshot_status tool reads the fresh snapshot
    client.post("/api/chat", json={"text": "how fresh is my snapshot?"})
    tool_payload = json.loads(next(
        m for m in web_chat.agent.session.messages if m["role"] == "tool"
    )["content"])
    assert tool_payload["snapshot"]["unique_release_count"] == 2

    # scan duplicate checker sees release 555 in the collection now
    post = client.get("/api/search", params={"q": "new record again"}).json()
    dup = post["candidates"][0]["duplicate"]
    assert dup["state"] == "in_collection"
    assert dup["copies"] == 1
