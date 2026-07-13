"""028 T010: the HTTP write gate (contract §2; agent-tools delta 12).

The full propose → card → confirm/cancel loop over the composed app with
a scripted LLM and FakeDiscogsClient: confirm executes ONLY the
server-held plan (live re-validation, per-item outcomes, snapshot patch);
every refusal path executes nothing."""

from __future__ import annotations

from collection_agent.models import Completeness
from tests.conftest import make_record, make_snapshot
from tests.integration.test_web_app_composition import make_web_client

# propose_moves resolves "A – X"-style records from the snapshot; folder
# "Techno" (id 3) exists in the fixture folders payload
PROPOSE_SCRIPT = [
    ("tool", "filter_records", {"criteria": [{"attribute": "artist", "value": "Test Artist"}]}),
    ("tool", "propose_moves", {"use_last_listing": True, "target_folder_name": "Techno"}),
    ("text", "I prepared a plan — confirm in the app."),
]


def snapshot_for_moves():
    return make_snapshot([
        make_record(11, release_id=101, title="Alpha EP"),
        make_record(12, release_id=102, title="Beta LP"),
    ])


def propose(client):
    return client.post("/api/chat", json={"text": "move my Test Artist records to Techno"})


def test_confirm_executes_plan_with_outcomes_and_patch(settings, store):
    client, discogs, *_ = make_web_client(
        settings, store, chat_script=list(PROPOSE_SCRIPT),
        snapshot=snapshot_for_moves(),
    )
    # the fake's live instances must cover the snapshot's records
    discogs.live_instances = {11: (101, 1), 12: (102, 1)}

    plan = propose(client).json()["pending_plan"]
    assert plan is not None
    assert plan["move_count"] == 2
    assert plan["target_folder"] == "Techno"

    resp = client.post("/api/chat/plan/confirm", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_folder"] == "Techno"
    assert [(m["result"]) for m in body["moves"]] == ["ok", "ok"]
    # both writes went to Discogs, targeting folder 3
    assert [(m[2], m[3]) for m in discogs.moves] == [(11, 3), (12, 3)]
    # snapshot patched in place — stays complete (FR-007)
    snap = store.load()
    assert snap.meta.completeness == Completeness.COMPLETE
    assert {r.folder_id for r in snap.records} == {3}
    # transcript recorded the outcome
    entries = client.get("/api/chat/history").json()["entries"]
    assert entries[-1]["kind"] == "plan_result"
    assert entries[-1]["moves"][0]["result"] == "ok"
    # the plan is spent: confirming again is refused, executes nothing
    again = client.post("/api/chat/plan/confirm", json={"plan_id": plan["plan_id"]})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "no_pending_plan"
    assert len(discogs.moves) == 2


def test_cancel_writes_nothing(settings, store):
    client, discogs, *_ = make_web_client(
        settings, store, chat_script=list(PROPOSE_SCRIPT),
        snapshot=snapshot_for_moves(),
    )
    discogs.live_instances = {11: (101, 1), 12: (102, 1)}
    plan = propose(client).json()["pending_plan"]
    resp = client.post("/api/chat/plan/cancel", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 200
    assert resp.json() == {"status": "cancelled"}
    assert discogs.moves == []
    # confirm after cancel: refused
    resp = client.post("/api/chat/plan/confirm", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_pending_plan"


def test_confirm_with_wrong_plan_id_is_mismatch_and_plan_survives(settings, store):
    client, discogs, *_ = make_web_client(
        settings, store, chat_script=list(PROPOSE_SCRIPT),
        snapshot=snapshot_for_moves(),
    )
    discogs.live_instances = {11: (101, 1), 12: (102, 1)}
    plan = propose(client).json()["pending_plan"]
    resp = client.post("/api/chat/plan/confirm", json={"plan_id": "stale-id"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "plan_mismatch"
    assert discogs.moves == []
    # the real plan is still confirmable
    resp = client.post("/api/chat/plan/confirm", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 200


def test_confirm_without_any_plan_is_refused(settings, store, complete_snapshot):
    client, discogs, *_ = make_web_client(settings, store, snapshot=complete_snapshot)
    resp = client.post("/api/chat/plan/confirm", json={"plan_id": "anything"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_pending_plan"
    assert discogs.moves == []


def test_new_turn_expires_plan_then_confirm_refused(settings, store):
    script = list(PROPOSE_SCRIPT) + [("text", "3 records")]
    client, discogs, *_ = make_web_client(
        settings, store, chat_script=script, snapshot=snapshot_for_moves()
    )
    discogs.live_instances = {11: (101, 1), 12: (102, 1)}
    plan = propose(client).json()["pending_plan"]
    # a new user turn cancels the pending plan (FR-006)
    client.post("/api/chat", json={"text": "how many records do I have?"})
    resp = client.post("/api/chat/plan/confirm", json={"plan_id": plan["plan_id"]})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_pending_plan"
    assert discogs.moves == []
    kinds = [e["kind"] for e in client.get("/api/chat/history").json()["entries"]]
    assert "plan_cancelled" in kinds


def test_request_body_cannot_inject_move_data(settings, store):
    """FR-005 pin: extra fields in the confirm body are ignored — only the
    server-held plan executes."""
    client, discogs, *_ = make_web_client(
        settings, store, chat_script=list(PROPOSE_SCRIPT),
        snapshot=snapshot_for_moves(),
    )
    discogs.live_instances = {11: (101, 1), 12: (102, 1)}
    plan = propose(client).json()["pending_plan"]
    resp = client.post(
        "/api/chat/plan/confirm",
        json={
            "plan_id": plan["plan_id"],
            "moves": [{"instance_id": 999, "release_id": 666}],
            "target_folder_id": 99,
        },
    )
    assert resp.status_code == 200
    # exactly the held plan's instances moved, to the held plan's folder
    assert sorted((m[2], m[3]) for m in discogs.moves) == [(11, 3), (12, 3)]


def test_live_revalidation_partial_failure_reported_per_item(settings, store):
    client, discogs, *_ = make_web_client(
        settings, store, chat_script=list(PROPOSE_SCRIPT),
        snapshot=snapshot_for_moves(),
    )
    # instance 12 vanished on Discogs since the snapshot
    discogs.live_instances = {11: (101, 1)}
    plan = propose(client).json()["pending_plan"]
    body = client.post(
        "/api/chat/plan/confirm", json={"plan_id": plan["plan_id"]}
    ).json()
    results = {m["display"]: m["result"] for m in body["moves"]}
    assert list(results.values()).count("ok") == 1
    assert list(results.values()).count("failed") == 1
    failed = next(m for m in body["moves"] if m["result"] == "failed")
    assert "no longer found" in failed["error"]
    # only the surviving instance moved
    assert [(m[2], m[3]) for m in discogs.moves] == [(11, 3)]
