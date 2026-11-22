"""028 T017: collection status + sync endpoints (contract §3).

Stubbed run_sync with events makes running/terminal states deterministic;
occupancy is asserted across BOTH triggers (endpoint + chat tool)."""

from __future__ import annotations

import json
import threading

from collection_agent.models import Completeness
from tests.conftest import make_record, make_snapshot
from tests.integration.test_web_app_composition import make_web_client


def completed_meta(completeness=Completeness.COMPLETE):
    return make_snapshot([make_record(1)], completeness=completeness).meta


class GatedSync:
    """A run_sync stand-in the test can hold open and release."""

    def __init__(self, result=None, error=None):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.result = result or completed_meta()
        self.error = error
        self.calls = 0

    def __call__(self, client, store, settings, full, on_progress, notify):
        self.calls += 1
        assert full is False
        self.entered.set()
        assert self.release.wait(timeout=5)
        if self.error is not None:
            raise self.error
        on_progress("enriching releases", 5, 5)
        notify("governor: pacing")
        return self.result


class TestStatus:
    def test_status_shape_with_complete_snapshot(self, settings, store, complete_snapshot):
        client, *_ = make_web_client(settings, store, snapshot=complete_snapshot)
        body = client.get("/api/collection/status").json()
        snap = body["snapshot"]
        assert snap["username"] == "test_user"
        assert snap["completeness"] == "complete"
        assert snap["instance_count"] == complete_snapshot.meta.instance_count
        assert snap["unique_release_count"] == complete_snapshot.meta.unique_release_count
        assert "collection_value" in snap and "folders" in snap
        assert body["collection_url"].endswith("/user/test_user/collection")
        assert body["sync"] == {
            "state": "idle", "phase": None, "done": None, "total": None,
            "warnings": [], "error": None, "finished_at": None,
        }

    def test_status_with_no_snapshot_is_null(self, settings, store):
        client, *_ = make_web_client(settings, store)
        body = client.get("/api/collection/status").json()
        assert body["snapshot"] is None
        assert body["collection_url"].endswith("/user/test_user/collection")


class TestSyncTrigger:
    def test_start_conflict_progress_and_completion(self, settings, store):
        gate = GatedSync()
        client, _, _, runner, *_ = make_web_client(
            settings, store, run_sync_fn=gate
        )
        assert client.post("/api/sync").status_code == 202
        assert gate.entered.wait(timeout=5)
        # single occupancy: the second trigger is refused
        again = client.post("/api/sync")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "sync_already_running"
        assert client.get("/api/collection/status").json()["sync"]["state"] == "running"
        gate.release.set()
        runner.join(timeout=5)
        sync = client.get("/api/collection/status").json()["sync"]
        assert sync["state"] == "complete"
        assert (sync["phase"], sync["done"], sync["total"]) == ("enriching releases", 5, 5)
        assert sync["warnings"] == ["governor: pacing"]
        assert sync["finished_at"] is not None
        assert gate.calls == 1

    def test_partial_and_failed_states_reported_honestly(self, settings, store):
        gate = GatedSync(result=completed_meta(Completeness.PARTIAL))
        client, _, _, runner, *_ = make_web_client(settings, store, run_sync_fn=gate)
        client.post("/api/sync")
        gate.release.set()
        runner.join(timeout=5)
        assert client.get("/api/collection/status").json()["sync"]["state"] == "partial"

        gate2 = GatedSync(error=RuntimeError("Discogs 5xx after retries"))
        client2, _, _, runner2, *_ = make_web_client(
            settings, store, run_sync_fn=gate2, session_id="20260712-191500Z"
        )
        client2.post("/api/sync")
        gate2.release.set()
        runner2.join(timeout=5)
        sync = client2.get("/api/collection/status").json()["sync"]
        assert sync["state"] == "failed"
        assert "Discogs 5xx" in sync["error"]
        # re-trigger resumes (journal semantics live in run_sync itself)
        gate2.error = None
        assert client2.post("/api/sync").status_code == 202
        gate2.release.set()
        runner2.join(timeout=5)
        assert client2.get("/api/collection/status").json()["sync"]["state"] == "complete"

    def test_chat_tool_and_endpoint_share_one_occupancy(self, settings, store, complete_snapshot):
        gate = GatedSync()
        client, _, _, runner, web_chat, _ = make_web_client(
            settings, store, run_sync_fn=gate,
            chat_script=[("tool", "start_sync", {}), ("text", "already going")],
            snapshot=complete_snapshot,
        )
        assert client.post("/api/sync").status_code == 202
        assert gate.entered.wait(timeout=5)
        resp = client.post("/api/chat", json={"text": "sync my collection"})
        assert resp.status_code == 200
        tool_payload = json.loads(next(
            m for m in web_chat.agent.session.messages if m["role"] == "tool"
        )["content"])
        assert tool_payload["already_running"] is True
        gate.release.set()
        runner.join(timeout=5)
        assert gate.calls == 1  # the chat tool never started a second run
