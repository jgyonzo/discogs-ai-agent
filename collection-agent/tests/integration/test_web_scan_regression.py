"""028 T024: the full 022/026 scan cycle through the composed app,
byte-equal to the bare scan app (FR-002; amendment-022-scan-api-4).

The same request sequence runs against `scan.server.create_app` and
`web.server.create_web_app` with identically-scripted collaborators;
every response body must match exactly."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from collection_agent.scan.journal import ScanJournal
from collection_agent.scan.server import create_app as create_scan_app
from collection_agent.scan.session import ScanSession
from collection_agent.web.chat import WebChat
from collection_agent.web.server import create_web_app
from collection_agent.web.syncrun import SyncRunner

from tests.fixtures import discogs_payloads as payloads
from tests.fixtures.fake_client import FakeDiscogsClient
from tests.integration.test_agent_loop import StubLLM
from tests.unit.test_scan_vision import StubVisionLLM

EVIDENCE_JSON = json.dumps(
    {"artist": "Alex Smoke", "title": "Simple Things", "barcode": "720642442524"}
)


def _fixed_clock():
    return datetime(2026, 7, 12, 20, 0, 0, tzinfo=timezone.utc)


def scripted_discogs():
    discogs = FakeDiscogsClient()
    discogs.search_responses.update({
        "barcode": payloads.search_page(
            [payloads.search_result(101), payloads.search_result(102)]
        ),
        "q": payloads.search_page([payloads.search_result(303)]),
    })
    return discogs


def make_bare(settings, store):
    session = ScanSession(
        ScanJournal(settings.scan_journal_dir, "bare-session"), clock=_fixed_clock
    )
    app = create_scan_app(
        settings=settings,
        llm_client=StubVisionLLM([EVIDENCE_JSON, EVIDENCE_JSON]),
        discogs_client=scripted_discogs(),
        store=store,
        session=session,
        username="test_user",
    )
    return TestClient(app)


def make_composed(settings, store):
    session = ScanSession(
        ScanJournal(settings.scan_journal_dir, "bare-session"), clock=_fixed_clock
    )
    runner = SyncRunner(
        settings, store,
        client_factory=FakeDiscogsClient,
        run_sync_fn=lambda *a, **k: None,
    )
    from collection_agent.web.agent_factory import build_web_agent

    agent = build_web_agent(
        settings, store, StubLLM([]), sync_starter=runner.start
    )
    app = create_web_app(
        settings=settings,
        llm_client=StubVisionLLM([EVIDENCE_JSON, EVIDENCE_JSON]),
        discogs_client=scripted_discogs(),
        store=store,
        scan_session=session,
        username="test_user",
        web_chat=WebChat(agent, settings, store),
        sync_runner=runner,
    )
    return TestClient(app)


def drive_scan_cycle(client):
    """The 022/026 flow: photo scan → duplicate double-confirm add →
    manual search → skip → session log. Returns every response body."""
    out = []
    scan = client.post(
        "/api/scan", files={"photo": ("r.jpg", b"fake-jpeg", "image/jpeg")}
    )
    out.append((scan.status_code, scan.json()))
    scan_id = scan.json()["scan_id"]

    add = client.post(
        "/api/add",
        json={"scan_id": scan_id, "release_id": 101, "confirm_duplicate": False},
    )
    out.append((add.status_code, add.json()))

    # duplicate double-confirmation on a second add of the same release
    scan2 = client.post(
        "/api/scan", files={"photo": ("r2.jpg", b"fake-jpeg-2", "image/jpeg")}
    )
    out.append((scan2.status_code, scan2.json()))
    scan2_id = scan2.json()["scan_id"]
    dup = client.post(
        "/api/add",
        json={"scan_id": scan2_id, "release_id": 101, "confirm_duplicate": False},
    )
    out.append((dup.status_code, dup.json()))
    dup2 = client.post(
        "/api/add",
        json={"scan_id": scan2_id, "release_id": 101, "confirm_duplicate": True},
    )
    out.append((dup2.status_code, dup2.json()))

    search = client.get("/api/search", params={"q": "something else"})
    out.append((search.status_code, search.json()))
    skip = client.post(
        "/api/skip", json={"scan_id": search.json()["scan_id"], "release_id": None}
    )
    out.append((skip.status_code, skip.json()))

    # supersede gate: adding to the (auto-closed) FIRST cycle's candidate
    # not registered anymore is still allowlisted by session — assert the
    # session log instead, identical on both apps
    log = client.get("/api/session")
    out.append((log.status_code, log.json()))
    return out


def test_scan_cycle_byte_equal_between_bare_and_composed(settings, store, tmp_path):
    bare = drive_scan_cycle(make_bare(settings, store))
    # separate journal dir so the two runs don't share a journal file
    settings2 = settings.model_copy(
        update={"scan_journal_dir": tmp_path / "scan-sessions-composed"}
    )
    composed = drive_scan_cycle(make_composed(settings2, store))
    assert bare == composed
