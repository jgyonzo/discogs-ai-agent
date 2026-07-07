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


class TestSessionLog:
    """US3 T030: mixed-outcome ordering, on-disk journal contract, and the
    interruption guarantee (every completed cycle on disk, immediately)."""

    def _run_mixed_session(self, settings, store, complete_snapshot):
        """added -> skipped -> no_match -> failed, in that order."""
        from collection_agent.discogs.client import DiscogsServerError

        client, discogs, session = make_client(
            settings, store,
            vision_script=[EVIDENCE_JSON] * 4,
            search_responses={
                "barcode": payloads.search_page(
                    [payloads.search_result(201), payloads.search_result(202)]
                )
            },
            snapshot=complete_snapshot,
        )
        # cycle 1: added
        s1 = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": s1, "release_id": 201})
        # cycle 2: skipped
        s2 = post_photo(client).json()["scan_id"]
        client.post("/api/skip", json={"scan_id": s2, "release_id": 202})
        # cycle 3: no_match (empty search for this one)
        discogs.search_responses["barcode"] = payloads.search_page([])
        post_photo(client)
        # cycle 4: failed add
        discogs.search_responses["barcode"] = payloads.search_page(
            [payloads.search_result(203)]
        )
        discogs.add_failures[203] = DiscogsServerError("boom")
        s4 = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": s4, "release_id": 203})
        return client, session

    def test_session_endpoint_orders_newest_first(
        self, settings, store, complete_snapshot
    ):
        client, _ = self._run_mixed_session(settings, store, complete_snapshot)
        body = client.get("/api/session").json()
        assert [e["outcome"] for e in body["entries"]] == [
            "failed", "no_match", "skipped", "added",
        ]
        assert body["session_id"] == "20260707-183000Z"

    def test_journal_file_matches_contract_line_by_line(
        self, settings, store, complete_snapshot
    ):
        from collection_agent.scan.models import ScanCycleOutcome

        _, session = self._run_mixed_session(settings, store, complete_snapshot)
        lines = session.journal.path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 4  # one line per completed cycle, no more
        parsed = [ScanCycleOutcome.model_validate(json.loads(l)) for l in lines]
        assert [e.outcome for e in parsed] == [
            "added", "skipped", "no_match", "failed",
        ]
        assert [e.seq for e in parsed] == [1, 2, 3, 4]  # strictly increasing
        assert all(e.source == "photo" for e in parsed)
        assert parsed[0].release_id == 201 and parsed[0].instance_id is not None
        assert parsed[3].detail and "boom" in parsed[3].detail

    def test_journal_durable_without_shutdown(
        self, settings, store, complete_snapshot
    ):
        """SC-007: the file accounts for every completed cycle at all times —
        killing the server needs no flush/close step."""
        client, session = self._run_mixed_session(
            settings, store, complete_snapshot
        )
        on_disk = session.journal.path.read_text(encoding="utf-8")
        assert len(on_disk.splitlines()) == len(session.log) == 4
        # earlier bytes never rewritten by later appends
        first_line = on_disk.splitlines()[0]
        assert json.loads(first_line)["outcome"] == "added"

    def test_journal_write_failure_surfaces_loudly(
        self, settings, store, complete_snapshot
    ):
        client, _, session = make_client(
            settings, store,
            search_responses={
                "barcode": payloads.search_page([payloads.search_result(201)])
            },
            snapshot=complete_snapshot,
        )
        scan_id = post_photo(client).json()["scan_id"]
        # sabotage the journal dir AFTER the scan: replace it with a file
        import shutil
        shutil.rmtree(settings.scan_journal_dir, ignore_errors=True)
        settings.scan_journal_dir.parent.mkdir(parents=True, exist_ok=True)
        settings.scan_journal_dir.write_text("not a directory")
        resp = client.post("/api/skip", json={"scan_id": scan_id})
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "journal_error"


class TestManualSearchFlow:
    """US4 T033: shape parity with /api/scan, empty-query 400, journaling
    with source=manual_search, no-match + skip -> no_match."""

    def test_response_shape_parity_with_scan(
        self, settings, store, complete_snapshot
    ):
        client, _, _ = make_client(
            settings, store,
            search_responses={
                "q": payloads.search_page([payloads.search_result(1)])
            },
            snapshot=complete_snapshot,
        )
        body = client.get("/api/search", params={"q": "simple things"}).json()
        assert body["source"] == "manual_search"
        assert body["evidence_summary"]["kinds"] == ["text"]
        assert set(body.keys()) == {
            "scan_id", "source", "evidence_summary", "candidates",
            "more_matches", "message",
        }
        candidate = body["candidates"][0]
        # identical candidate shape incl. the duplicate overlay (release 1
        # is in the snapshot twice)
        assert candidate["duplicate"]["state"] == "in_collection"
        assert candidate["duplicate"]["copies"] == 2

    def test_empty_query_rejected(self, settings, store):
        client, _, _ = make_client(settings, store)
        resp = client.get("/api/search", params={"q": "   "})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "empty_query"

    def test_manual_add_journals_manual_search_source(self, settings, store):
        client, discogs, session = make_client(
            settings, store,
            search_responses={
                "q": payloads.search_page([payloads.search_result(301)])
            },
        )
        scan_id = client.get(
            "/api/search", params={"q": "some record"}
        ).json()["scan_id"]
        body = client.post(
            "/api/add", json={"scan_id": scan_id, "release_id": 301}
        ).json()
        assert body["status"] == "added"
        assert discogs.adds == [("test_user", 1, 301)]
        assert session.log[-1].source == "manual_search"
        assert session.log[-1].evidence_kinds == ["text"]

    def test_no_match_manual_search_then_skip_journals_no_match(
        self, settings, store
    ):
        client, _, session = make_client(settings, store)  # empty q rung
        body = client.get("/api/search", params={"q": "white label promo"}).json()
        assert body["candidates"] == []
        assert body["message"] is not None
        assert session.log == []  # search itself is side-effect-free
        client.post("/api/skip", json={"scan_id": body["scan_id"]})
        assert session.log[-1].outcome == "no_match"
        assert session.log[-1].source == "manual_search"


class TestReplayRound1:
    """Addendum 1 (session 20260707-130810Z): end-to-end replays of the
    live failures with the verbatim vision replies, plus FR-021 evidence
    values in the journal."""

    LIVE_CYCLE_2 = json.dumps({
        "artist": "dj silversurfer",
        "label": "CROSSTOWNREBELS",
        "catno": "81824 11306",
        "notes": "a. ace of spades/ ft. kiki\naa. dirty dishes",
    })
    LIVE_CYCLE_1 = json.dumps({"label": "Crosstown Rebels"})

    def test_cycle_2_reply_now_reaches_barcode_and_text_rungs(
        self, settings, store
    ):
        client, discogs, session = make_client(
            settings, store,
            vision_script=[self.LIVE_CYCLE_2],
            search_responses={
                "q": payloads.search_page([payloads.search_result(601)])
            },
        )
        body = post_photo(client).json()
        # digit run reclassified: barcode rung queried, never catno
        rungs = [
            "barcode" if "barcode" in p else
            "catno" if "catno" in p else
            "artist_title" if "artist" in p else "q"
            for p in discogs.searches
        ]
        assert rungs == ["barcode", "q"]
        assert discogs.searches[0]["barcode"] == "8182411306"
        # composed fallback found the record
        assert [c["release_id"] for c in body["candidates"]] == [601]

    def test_cycle_1_label_only_now_queries_discogs(self, settings, store):
        client, discogs, session = make_client(
            settings, store,
            vision_script=[self.LIVE_CYCLE_1],
            search_responses={
                "q": payloads.search_page([payloads.search_result(602)])
            },
        )
        body = post_photo(client).json()
        assert discogs.searches[0]["q"] == "Crosstown Rebels"
        assert [c["release_id"] for c in body["candidates"]] == [602]

    def test_no_match_journal_carries_evidence_values(self, settings, store):
        client, _, session = make_client(
            settings, store, vision_script=[self.LIVE_CYCLE_2],
        )  # all searches empty -> no_match
        post_photo(client)
        line = json.loads(
            session.journal.path.read_text(encoding="utf-8").splitlines()[-1]
        )
        assert line["outcome"] == "no_match"
        assert line["evidence_kinds"] == ["barcode", "text"]  # rungs tried
        assert line["evidence"]["artist"] == "dj silversurfer"
        assert line["evidence"]["barcode"] == "8182411306"
        assert line["evidence"]["label"] == "CROSSTOWNREBELS"
        assert "catno" not in line["evidence"]  # reclassified away

    def test_added_journal_carries_evidence_values(self, settings, store):
        client, _, session = make_client(
            settings, store, search_responses=ONE_HIT,
        )
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": scan_id, "release_id": 101})
        entry = session.log[-1]
        assert entry.outcome == "added"
        assert entry.evidence["barcode"] == "720642442524"
        assert entry.evidence_kinds == ["barcode"]  # first rung hit

    def test_manual_search_journal_carries_query(self, settings, store):
        client, _, session = make_client(settings, store)
        body = client.get("/api/search", params={"q": "white label"}).json()
        client.post("/api/skip", json={"scan_id": body["scan_id"]})
        assert session.log[-1].evidence == {"q": "white label"}


class TestReplayRound2:
    """Addendum 2: FR-022 auto-close of abandoned cycles, FR-023
    supersession of in-flight identification."""

    def test_new_scan_autocloses_abandoned_cycle(self, settings, store):
        client, _, session = make_client(
            settings, store,
            vision_script=[EVIDENCE_JSON, EVIDENCE_JSON],
            search_responses=ONE_HIT,
        )
        first = post_photo(client).json()
        assert first["candidates"]  # cycle A open, owner never taps anything
        second = post_photo(client).json()
        assert second["candidates"]
        # cycle A journaled skipped with the auto-close detail
        entry = next(e for e in session.log if e.scan_id == first["scan_id"])
        assert entry.outcome == "skipped"
        assert entry.detail == "auto-closed: superseded by a new scan"
        assert entry.evidence["barcode"] == "720642442524"  # FR-021 kept
        # cycle B is the only open cycle
        assert not session.is_closed(second["scan_id"])

    def test_manual_search_autocloses_abandoned_cycle(self, settings, store):
        client, _, session = make_client(
            settings, store, search_responses=ONE_HIT,
        )
        first = post_photo(client).json()
        client.get("/api/search", params={"q": "something else"})
        entry = next(e for e in session.log if e.scan_id == first["scan_id"])
        assert entry.outcome == "skipped"
        assert entry.detail == "auto-closed: superseded by a new scan"

    def test_autoclose_is_not_triggered_for_closed_cycles(self, settings, store):
        client, _, session = make_client(
            settings, store,
            vision_script=[EVIDENCE_JSON, EVIDENCE_JSON],
            search_responses=ONE_HIT,
        )
        scan_id = post_photo(client).json()["scan_id"]
        client.post("/api/add", json={"scan_id": scan_id, "release_id": 101})
        post_photo(client)  # must NOT double-journal cycle A
        entries_for_a = [e for e in session.log if e.scan_id == scan_id]
        assert [e.outcome for e in entries_for_a] == ["added"]

    def test_inflight_scan_superseded_and_discarded(self, settings, store):
        """FR-023: scan A blocks in vision; scan B lands meanwhile. A must
        return 409 superseded, journal nothing for itself, register no
        candidates; B owns the cycle."""
        import threading

        release_gate = threading.Event()
        entered = threading.Event()

        class BlockingVisionLLM(StubVisionLLM):
            def _create(self, **kwargs):
                self.requests.append(kwargs)
                if len(self.requests) == 1:  # scan A blocks until released
                    entered.set()
                    assert release_gate.wait(timeout=10)
                from types import SimpleNamespace
                msg = SimpleNamespace(content=EVIDENCE_JSON, tool_calls=None)
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        llm = BlockingVisionLLM([])
        discogs = FakeDiscogsClient()
        discogs.search_responses.update(ONE_HIT)
        session = ScanSession(
            ScanJournal(settings.scan_journal_dir, "20260707-180000Z"),
            clock=_fixed_clock,
        )
        app = create_app(
            settings=settings, llm_client=llm, discogs_client=discogs,
            store=store, session=session, username="test_user",
        )
        client = TestClient(app)

        result_a: dict = {}

        def scan_a():
            result_a["resp"] = post_photo(client)

        t = threading.Thread(target=scan_a)
        t.start()
        assert entered.wait(timeout=10)      # A is inside its vision call
        resp_b = post_photo(client)          # B supersedes A
        assert resp_b.status_code == 200
        assert resp_b.json()["candidates"]
        release_gate.set()                   # let A's vision return
        t.join(timeout=10)

        assert result_a["resp"].status_code == 409
        assert result_a["resp"].json()["error"]["code"] == "superseded"
        # A journaled nothing for itself and registered nothing:
        # exactly one open cycle (B's), zero journal entries so far
        assert session.log == []
        assert len(session.seen_release_ids) == 1  # only B's candidate set


class TestPhotoRetention:
    """023 US3 (T023): opt-in retention through the real endpoint —
    save-then-rename on the happy path, honest pending-* on vision failure,
    non-fatal retention failure, and byte-identical behavior when off."""

    @staticmethod
    def retain(settings):
        return settings.model_copy(update={"scan_retain_photos": True})

    def session_dir(self, settings):
        return settings.scan_retention_dir / "20260707-183000Z"

    def test_flag_on_saves_and_renames_to_scan_id(self, settings, store):
        client, _, _ = make_client(
            self.retain(settings), store, search_responses=ONE_HIT
        )
        resp = post_photo(client, content=b"original-photo-bytes")
        scan_id = resp.json()["scan_id"]
        retained = self.session_dir(settings) / f"{scan_id}.jpg"
        assert retained.read_bytes() == b"original-photo-bytes"
        assert not list(self.session_dir(settings).glob("pending-*"))

    def test_no_match_cycle_also_renames(self, settings, store):
        client, _, _ = make_client(
            self.retain(settings), store, vision_script=["{}"]
        )
        resp = post_photo(client)
        scan_id = resp.json()["scan_id"]
        assert (self.session_dir(settings) / f"{scan_id}.jpg").exists()

    def test_vision_failure_leaves_pending_file(self, settings, store):
        client, _, _ = make_client(
            self.retain(settings), store,
            vision_script=[RuntimeError("provider down")],
        )
        resp = post_photo(client, content=b"photo-that-broke-vision")
        assert resp.status_code == 502
        pending = self.session_dir(settings) / "pending-1.jpg"
        assert pending.read_bytes() == b"photo-that-broke-vision"

    def test_retention_failure_never_breaks_the_scan(self, settings, store):
        # a FILE where the retention dir should be makes every save fail
        settings.scan_retention_dir.parent.mkdir(parents=True, exist_ok=True)
        settings.scan_retention_dir.write_text("not a directory")
        client, _, _ = make_client(
            self.retain(settings), store, search_responses=ONE_HIT
        )
        resp = post_photo(client)
        assert resp.status_code == 200
        assert resp.json()["candidates"]  # scan fully functional

    def test_flag_off_never_touches_the_retention_dir(self, settings, store):
        client, _, _ = make_client(settings, store, search_responses=ONE_HIT)
        resp = post_photo(client)
        assert resp.status_code == 200
        assert not settings.scan_retention_dir.exists()
