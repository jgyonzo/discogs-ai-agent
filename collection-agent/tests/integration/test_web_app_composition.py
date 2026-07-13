"""028 T007: the composed web app serves the scan surface unchanged
(research R1; amendment-022-scan-api-4). Collaborators fully stubbed."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from collection_agent.agent import Agent
from collection_agent.registry import build_registry
from collection_agent.scan.journal import ScanJournal
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
ONE_HIT = {"barcode": payloads.search_page([payloads.search_result(101)])}


def _fixed_clock():
    return datetime(2026, 7, 12, 18, 30, 0, tzinfo=timezone.utc)


def make_web_client(
    settings,
    store,
    vision_script=None,
    search_responses=None,
    chat_script=None,
    snapshot=None,
    run_sync_fn=None,
    session_id="20260712-183000Z",
):
    """TestClient over create_web_app + handles on every collaborator."""
    if snapshot is not None:
        store.save(snapshot)
    vision_llm = StubVisionLLM(
        vision_script if vision_script is not None else [EVIDENCE_JSON]
    )
    discogs = FakeDiscogsClient()
    if search_responses:
        discogs.search_responses.update(search_responses)
    scan_session = ScanSession(
        ScanJournal(settings.scan_journal_dir, session_id), clock=_fixed_clock
    )
    sync_runner = SyncRunner(
        settings,
        store,
        client_factory=lambda: FakeDiscogsClient(),
        run_sync_fn=run_sync_fn or (lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("no sync scripted for this test")
        )),
    )
    # web chat agent: same registry/tools, scripted chat LLM, web start_sync
    from collection_agent.web.agent_factory import build_web_agent

    chat_llm = StubLLM(chat_script if chat_script is not None else [])
    agent = build_web_agent(
        settings, store, chat_llm, sync_starter=sync_runner.start
    )
    web_chat = WebChat(
        agent, settings, store, client_factory=lambda: discogs
    )
    app = create_web_app(
        settings=settings,
        llm_client=vision_llm,
        discogs_client=discogs,
        store=store,
        scan_session=scan_session,
        username="test_user",
        web_chat=web_chat,
        sync_runner=sync_runner,
    )
    return TestClient(app), discogs, scan_session, sync_runner, web_chat, chat_llm


def post_photo(client, content=b"fake-jpeg-bytes", mime="image/jpeg"):
    return client.post("/api/scan", files={"photo": ("record.jpg", content, mime)})


class TestScanSurfaceUnchanged:
    def test_root_serves_the_tabbed_page(self, settings, store):
        client, *_ = make_web_client(settings, store)
        resp = client.get("/")
        assert resp.status_code == 200
        text = resp.text
        for section in ("tab-scan", "tab-chat", "tab-collection"):
            assert section in text

    def test_health_shape_unchanged(self, settings, store):
        client, *_ = make_web_client(settings, store)
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["snapshot"] == "missing"
        assert body["session_id"] == "20260712-183000Z"

    def test_scan_to_add_flow_works_through_composed_app(self, settings, store):
        client, discogs, session, *_ = make_web_client(
            settings, store, search_responses=ONE_HIT
        )
        scan = post_photo(client)
        assert scan.status_code == 200
        scan_id = scan.json()["scan_id"]
        assert [c["release_id"] for c in scan.json()["candidates"]] == [101]
        add = client.post(
            "/api/add",
            json={"scan_id": scan_id, "release_id": 101, "confirm_duplicate": False},
        )
        assert add.status_code == 200
        assert add.json()["status"] == "added"
        assert discogs.adds == [("test_user", 1, 101)]
        assert session.log[-1].outcome == "added"

    def test_unknown_candidate_gate_unchanged(self, settings, store):
        client, *_ = make_web_client(settings, store, search_responses=ONE_HIT)
        scan_id = post_photo(client).json()["scan_id"]
        resp = client.post(
            "/api/add",
            json={"scan_id": scan_id, "release_id": 999, "confirm_duplicate": False},
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "unknown_candidate"

    def test_manual_search_and_session_log_unchanged(self, settings, store):
        client, *_ = make_web_client(settings, store, search_responses={
            "q": payloads.search_page([payloads.search_result(202)])
        })
        resp = client.get("/api/search", params={"q": "alex smoke"})
        assert resp.status_code == 200
        assert resp.json()["source"] == "manual_search"
        log = client.get("/api/session").json()
        assert log["session_id"] == "20260712-183000Z"
