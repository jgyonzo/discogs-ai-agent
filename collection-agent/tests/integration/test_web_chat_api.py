"""028 T009: chat endpoints over the composed app (contract §2).

TestClient + scripted StubLLM. Turn flow, empty/busy/error typed
responses, pending-plan payload, history, restart-empties."""

from __future__ import annotations

import threading

from tests.conftest import make_record, make_snapshot
from tests.integration.test_web_app_composition import make_web_client


def chat(client, text):
    return client.post("/api/chat", json={"text": text})


def test_turn_returns_reply_no_plan(settings, store, complete_snapshot):
    client, *_ = make_web_client(
        settings, store,
        chat_script=[("tool", "snapshot_status", {}), ("text", "you have 3 records")],
        snapshot=complete_snapshot,
    )
    resp = chat(client, "how many records do I have?")
    assert resp.status_code == 200
    assert resp.json() == {"reply": "you have 3 records", "pending_plan": None}


def test_empty_message_is_400_and_spends_no_llm_call(settings, store):
    client, *rest = make_web_client(settings, store, chat_script=[])
    chat_llm = rest[-1]
    resp = chat(client, "   ")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "empty_message"
    assert chat_llm.requests == []


def test_llm_failure_is_typed_502_and_session_survives(settings, store, complete_snapshot):
    class ExplodingThenFine:
        def __init__(self):
            from types import SimpleNamespace

            self.calls = 0
            self.requests = []
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def _create(self, **kwargs):
            from types import SimpleNamespace

            self.requests.append(kwargs)
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider 500")
            msg = SimpleNamespace(content="fine now", tool_calls=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    from collection_agent.web.agent_factory import build_web_agent
    from collection_agent.web.chat import WebChat
    from collection_agent.web.server import create_web_app
    from collection_agent.web.syncrun import SyncRunner
    from collection_agent.scan.journal import ScanJournal
    from collection_agent.scan.session import ScanSession
    from fastapi.testclient import TestClient
    from tests.fixtures.fake_client import FakeDiscogsClient
    from tests.unit.test_scan_vision import StubVisionLLM

    store.save(complete_snapshot)
    llm = ExplodingThenFine()
    runner = SyncRunner(settings, store, client_factory=FakeDiscogsClient,
                        run_sync_fn=lambda *a, **k: None)
    agent = build_web_agent(settings, store, llm, sync_starter=runner.start)
    web_chat = WebChat(agent, settings, store)
    app = create_web_app(
        settings=settings, llm_client=StubVisionLLM([]),
        discogs_client=FakeDiscogsClient(), store=store,
        scan_session=ScanSession(ScanJournal(settings.scan_journal_dir, "s1")),
        username="test_user", web_chat=web_chat, sync_runner=runner,
    )
    client = TestClient(app)

    resp = chat(client, "hola")
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "chat_error"
    # rewound: only the system prompt remains in the LLM context
    assert [m["role"] for m in agent.session.messages] == ["system"]
    # the conversation is still usable
    resp2 = chat(client, "hola otra vez")
    assert resp2.status_code == 200
    assert resp2.json()["reply"] == "fine now"
    # transcript kept the failed attempt as typed data
    kinds = [e["kind"] for e in client.get("/api/chat/history").json()["entries"]]
    assert kinds == ["user", "error", "user", "assistant"]


def test_busy_turn_is_409(settings, store, complete_snapshot):
    """Hold the lock as a concurrent in-flight turn would; a second POST
    must be refused, not queued."""
    client, *rest = make_web_client(
        settings, store, chat_script=[("text", "late answer")],
        snapshot=complete_snapshot,
    )
    web_chat = rest[-2]
    assert web_chat._lock.acquire(blocking=False)
    try:
        resp = chat(client, "second question")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "chat_busy"
    finally:
        web_chat._lock.release()


def test_history_reports_snapshot_state_for_banner(settings, store, complete_snapshot):
    client, *_ = make_web_client(settings, store, snapshot=complete_snapshot)
    assert client.get("/api/chat/history").json()["snapshot_state"] == "complete"

    client2, *_ = make_web_client(settings, store)  # store already has snapshot
    store.mark_stale()
    assert client2.get("/api/chat/history").json()["snapshot_state"] == "stale"


def test_history_missing_snapshot_state(settings, store):
    client, *_ = make_web_client(settings, store)
    body = client.get("/api/chat/history").json()
    assert body == {"entries": [], "pending_plan": None, "snapshot_state": "missing"}


def test_new_app_instance_starts_with_empty_transcript(settings, store, complete_snapshot):
    client, *_ = make_web_client(
        settings, store, chat_script=[("text", "hi")], snapshot=complete_snapshot
    )
    chat(client, "hello")
    assert len(client.get("/api/chat/history").json()["entries"]) == 2
    # "restart": a fresh app/process ⇒ empty transcript (FR-016 scope)
    client2, *_ = make_web_client(settings, store, session_id="20260712-190000Z")
    assert client2.get("/api/chat/history").json()["entries"] == []
