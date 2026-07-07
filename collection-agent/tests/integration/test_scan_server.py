"""Scan server end-to-end against the injected app factory (022 T022):
photo -> candidates -> confirmed add; gates (size, media type, allowlist);
honest no-match and failure payloads; secrets never on the wire.
All collaborators stubbed — TestClient in-process, zero live calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from collection_agent.scan.journal import ScanJournal
from collection_agent.scan.server import create_app
from collection_agent.scan.session import ScanSession

from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient
from tests.unit.test_scan_vision import StubVisionLLM

TOKEN = "test-token-not-real"
FAKE_KEY = "sk-test-not-real"

EVIDENCE_JSON = json.dumps(
    {"artist": "Alex Smoke", "title": "Simple Things", "barcode": "720642442524"}
)


def _fixed_clock():
    return datetime(2026, 7, 7, 18, 30, 0, tzinfo=timezone.utc)


def make_client(
    settings,
    store,
    vision_script=None,
    search_responses=None,
    add_failures=None,
    snapshot=None,
):
    """TestClient + handles on the injected collaborators."""
    if snapshot is not None:
        store.save(snapshot)
    llm = StubVisionLLM(vision_script if vision_script is not None else [EVIDENCE_JSON])
    discogs = FakeDiscogsClient()
    if search_responses:
        discogs.search_responses.update(search_responses)
    if add_failures:
        discogs.add_failures.update(add_failures)
    session = ScanSession(
        ScanJournal(settings.scan_journal_dir, "20260707-183000Z"),
        clock=_fixed_clock,
    )
    app = create_app(
        settings=settings,
        llm_client=llm,
        discogs_client=discogs,
        store=store,
        session=session,
        username="test_user",
    )
    return TestClient(app), discogs, session


def post_photo(client, content=b"fake-jpeg-bytes", mime="image/jpeg"):
    return client.post(
        "/api/scan", files={"photo": ("record.jpg", content, mime)}
    )


ONE_HIT = {"barcode": payloads.search_page([payloads.search_result(101)])}


class TestHappyPath:
    def test_scan_returns_candidates(self, settings, store):
        client, discogs, _ = make_client(
            settings, store, search_responses=ONE_HIT
        )
        resp = post_photo(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "photo"
        assert body["evidence_summary"]["kinds"] == ["barcode", "artist_title"]
        assert [c["release_id"] for c in body["candidates"]] == [101]
        assert body["candidates"][0]["duplicate"]["state"] == "unknown"
        assert body["more_matches"] is False

    def test_confirmed_add_writes_exactly_once(self, settings, store):
        client, discogs, session = make_client(
            settings, store, search_responses=ONE_HIT
        )
        scan_id = post_photo(client).json()["scan_id"]
        resp = client.post(
            "/api/add",
            json={"scan_id": scan_id, "release_id": 101, "confirm_duplicate": False},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "added"
        assert body["instance_id"] == 90002
        assert discogs.adds == [
            ("test_user", settings.scan_target_folder_id, 101)
        ]
        # journaled + session updated
        assert session.log[-1].outcome == "added"
        assert session.log[-1].release_id == 101
        assert session.added_release_ids == {101: 1}

    def test_add_uses_configured_folder(self, settings, store, tmp_path):
        from collection_agent.settings import Settings

        custom = Settings(
            _env_file=None,
            DISCOGS_USER_TOKEN=TOKEN,
            SNAPSHOT_PATH=tmp_path / "snapshot.json",
            COLLECTION_AGENT_SCAN_JOURNAL_DIR=tmp_path / "scan-sessions",
            COLLECTION_AGENT_SCAN_FOLDER_ID=3,
        )
        client, discogs, _ = make_client(custom, store, search_responses=ONE_HIT)
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": scan_id, "release_id": 101})
        assert discogs.adds[0][1] == 3


class TestGates:
    def test_oversized_upload_rejected_before_vision(self, settings, store, tmp_path):
        from collection_agent.settings import Settings

        small_cap = Settings(
            _env_file=None,
            DISCOGS_USER_TOKEN=TOKEN,
            SNAPSHOT_PATH=tmp_path / "snapshot.json",
            COLLECTION_AGENT_SCAN_JOURNAL_DIR=tmp_path / "scan-sessions",
            COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES=10,
        )
        client, _, _ = make_client(small_cap, store, vision_script=[])
        resp = post_photo(client, content=b"x" * 11)
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "image_too_large"
        # vision never ran: the empty script would have raised on any call

    def test_non_image_rejected(self, settings, store):
        client, _, _ = make_client(settings, store, vision_script=[])
        resp = post_photo(client, mime="application/pdf")
        assert resp.status_code == 415
        assert resp.json()["error"]["code"] == "unsupported_media_type"

    def test_unknown_candidate_rejected_without_discogs_call(self, settings, store):
        client, discogs, _ = make_client(settings, store)
        resp = client.post(
            "/api/add", json={"scan_id": "x-1", "release_id": 999}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "unknown_candidate"
        assert discogs.adds == []


class TestHonestFailures:
    def test_vision_failure_maps_to_502(self, settings, store):
        client, _, session = make_client(
            settings, store, vision_script=[RuntimeError("model down")]
        )
        resp = post_photo(client)
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "vision_unavailable"
        assert session.log == []  # no completed cycle journaled

    def test_discogs_search_failure_maps_to_502(self, settings, store):
        from collection_agent.discogs.client import DiscogsServerError

        client, discogs, _ = make_client(settings, store)
        discogs.search_releases = lambda params: (_ for _ in ()).throw(
            DiscogsServerError("Discogs 5xx after retries")
        )
        resp = post_photo(client)
        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == "discogs_unavailable"

    def test_empty_evidence_is_honest_no_match(self, settings, store):
        client, discogs, session = make_client(
            settings, store, vision_script=["{}"]
        )
        resp = post_photo(client)
        assert resp.status_code == 200
        body = resp.json()
        assert body["candidates"] == []
        assert "manual search" in body["message"].lower()
        assert discogs.searches == []  # no Discogs call without evidence
        assert session.log[-1].outcome == "no_match"

    def test_zero_results_is_honest_no_match(self, settings, store):
        client, _, session = make_client(settings, store)  # all rungs empty
        body = post_photo(client).json()
        assert body["candidates"] == []
        assert body["message"] is not None
        assert session.log[-1].outcome == "no_match"

    def test_add_failure_reported_and_journaled(self, settings, store):
        from collection_agent.discogs.client import DiscogsServerError

        client, discogs, session = make_client(
            settings,
            store,
            search_responses=ONE_HIT,
            add_failures={101: DiscogsServerError("Discogs 5xx after retries")},
        )
        scan_id = post_photo(client).json()["scan_id"]
        resp = client.post("/api/add", json={"scan_id": scan_id, "release_id": 101})
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        assert "5xx" in resp.json()["detail"]
        assert discogs.adds == []
        assert session.log[-1].outcome == "failed"
        # snapshot untouched (no file existed; mark_stale of nothing is a no-op)
        assert not settings.snapshot_path.exists()


class TestSkip:
    def test_skip_with_candidates_journals_skipped(self, settings, store):
        client, _, session = make_client(settings, store, search_responses=ONE_HIT)
        scan_id = post_photo(client).json()["scan_id"]
        resp = client.post("/api/skip", json={"scan_id": scan_id, "release_id": 101})
        assert resp.json()["status"] == "skipped"
        assert session.log[-1].outcome == "skipped"
        assert session.log[-1].release_id == 101

    def test_skip_is_idempotent_per_cycle(self, settings, store):
        client, _, session = make_client(settings, store, search_responses=ONE_HIT)
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/skip", json={"scan_id": scan_id})
        client.post("/api/skip", json={"scan_id": scan_id})
        assert len(session.log) == 1


class TestPageAndSecrets:
    def test_index_served(self, settings, store):
        client, _, _ = make_client(settings, store)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "capture=" in resp.text  # native camera input

    def test_health(self, settings, store, complete_snapshot):
        client, _, _ = make_client(settings, store, snapshot=complete_snapshot)
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["snapshot"] == "complete"

    def test_no_secrets_on_any_wire_surface(self, settings, store):
        """FR-017: token/key appear in no response body — page, scan,
        candidates, errors, session log."""
        client, _, _ = make_client(settings, store, search_responses=ONE_HIT)
        surfaces = [
            client.get("/").text,
            post_photo(client).text,
            client.get("/api/session").text,
            client.get("/api/health").text,
            client.post("/api/add", json={"scan_id": "x", "release_id": 999}).text,
        ]
        for body in surfaces:
            assert TOKEN not in body
            assert FAKE_KEY not in body


class TestDuplicateFlow:
    """US2 T027: server-enforced double confirmation, mark_stale on success
    only, session overlay, degraded-snapshot markers."""

    def test_duplicate_marked_in_candidates(
        self, settings, store, complete_snapshot
    ):
        # release 1 is in the snapshot twice (instances 1 and 4)
        client, _, _ = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(1)])
            },
            snapshot=complete_snapshot,
        )
        body = post_photo(client).json()
        dup = body["candidates"][0]["duplicate"]
        assert dup["state"] == "in_collection"
        assert dup["copies"] == 2

    def test_duplicate_add_requires_second_confirmation(
        self, settings, store, complete_snapshot
    ):
        client, discogs, session = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(1)])
            },
            snapshot=complete_snapshot,
        )
        scan_id = post_photo(client).json()["scan_id"]

        first = client.post(
            "/api/add", json={"scan_id": scan_id, "release_id": 1}
        ).json()
        assert first["status"] == "needs_duplicate_confirmation"
        assert "2 copies" in first["detail"]
        assert discogs.adds == []          # NO write on the first attempt
        assert session.log == []           # and nothing journaled

        second = client.post(
            "/api/add",
            json={"scan_id": scan_id, "release_id": 1, "confirm_duplicate": True},
        ).json()
        assert second["status"] == "added"
        assert len(discogs.adds) == 1      # exactly one write
        assert session.log[-1].duplicate_add is True

    def test_non_duplicate_needs_single_confirmation(
        self, settings, store, complete_snapshot
    ):
        client, discogs, session = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(999)])
            },
            snapshot=complete_snapshot,
        )
        scan_id = post_photo(client).json()["scan_id"]
        body = client.post(
            "/api/add", json={"scan_id": scan_id, "release_id": 999}
        ).json()
        assert body["status"] == "added"
        assert len(discogs.adds) == 1
        assert session.log[-1].duplicate_add is False

    def test_mark_stale_on_success_only(
        self, settings, store, complete_snapshot
    ):
        from collection_agent.models import Completeness

        client, _, _ = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(999)])
            },
            snapshot=complete_snapshot,
        )
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": scan_id, "release_id": 999})
        assert store.load().meta.completeness == Completeness.STALE

    def test_failed_add_leaves_snapshot_complete(
        self, settings, store, complete_snapshot
    ):
        from collection_agent.discogs.client import DiscogsServerError
        from collection_agent.models import Completeness

        client, _, _ = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(999)])
            },
            add_failures={999: DiscogsServerError("boom")},
            snapshot=complete_snapshot,
        )
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": scan_id, "release_id": 999})
        assert store.load().meta.completeness == Completeness.COMPLETE

    def test_same_release_again_shows_session_add(
        self, settings, store, complete_snapshot
    ):
        client, _, _ = make_client(
            settings, store,
            vision_script=[EVIDENCE_JSON, EVIDENCE_JSON],  # two scans
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(999)])
            },
            snapshot=complete_snapshot,
        )
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": scan_id, "release_id": 999})

        # scanning the same record again: now marked via the session overlay
        body = post_photo(client).json()
        dup = body["candidates"][0]["duplicate"]
        assert dup["state"] == "in_collection"
        assert dup["added_this_session"] is True
        assert dup["copies"] == 1

        # and adding it again needs the extra confirmation
        again = client.post(
            "/api/add",
            json={"scan_id": body["scan_id"], "release_id": 999},
        ).json()
        assert again["status"] == "needs_duplicate_confirmation"

    def test_stale_snapshot_absence_shows_unknown_marker(
        self, settings, store, stale_snapshot
    ):
        client, _, _ = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(999)])
            },
            snapshot=stale_snapshot,
        )
        dup = post_photo(client).json()["candidates"][0]["duplicate"]
        assert dup["state"] == "unknown"
        assert dup["reason"] == "snapshot stale"
