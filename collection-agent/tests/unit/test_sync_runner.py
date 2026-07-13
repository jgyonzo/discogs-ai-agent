"""028 T004: SyncRunner state machine + single occupancy (research R5).

`run_sync` is stubbed; a threading.Event lets tests hold the "sync" open
to assert the running state and the occupancy refusal deterministically.
"""

from __future__ import annotations

import threading

import pytest

from collection_agent.models import Completeness
from collection_agent.web.syncrun import SyncRunner
from tests.conftest import make_record, make_snapshot


class RecordingClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def make_runner(settings, store, run_sync_fn, client=None):
    client = client or RecordingClient()
    runner = SyncRunner(
        settings, store, client_factory=lambda: client, run_sync_fn=run_sync_fn
    )
    return runner, client


def completed_meta(completeness=Completeness.COMPLETE):
    return make_snapshot([make_record(1)], completeness=completeness).meta


def test_idle_before_any_start(settings, store):
    runner, _ = make_runner(settings, store, lambda *a, **k: completed_meta())
    status = runner.status()
    assert status.state == "idle"
    assert status.phase is None and status.done is None and status.total is None


def test_complete_run_reports_progress_and_closes_client(settings, store):
    def fake_sync(client, st, se, full, on_progress, notify):
        assert full is False  # web sync is ALWAYS the standard sync
        on_progress("collection pages", 1, 3)
        on_progress("enriching releases", 2, 2)
        notify("rate limit low — pacing requests")
        return completed_meta()

    runner, client = make_runner(settings, store, fake_sync)
    assert runner.start() is True
    runner.join(timeout=5)
    status = runner.status()
    assert status.state == "complete"
    assert status.phase == "enriching releases"
    assert (status.done, status.total) == (2, 2)
    assert status.warnings == ["rate limit low — pacing requests"]
    assert status.error is None
    assert status.finished_at is not None
    assert client.closed is True


def test_partial_meta_reports_partial_state(settings, store):
    runner, _ = make_runner(
        settings, store, lambda *a, **k: completed_meta(Completeness.PARTIAL)
    )
    runner.start()
    runner.join(timeout=5)
    assert runner.status().state == "partial"


def test_exception_reports_failed_with_message_and_closes_client(settings, store):
    def boom(*a, **k):
        raise RuntimeError("Discogs 5xx after retries")

    runner, client = make_runner(settings, store, boom)
    runner.start()
    runner.join(timeout=5)
    status = runner.status()
    assert status.state == "failed"
    assert "Discogs 5xx after retries" in status.error
    assert status.finished_at is not None
    assert client.closed is True


def test_single_occupancy_second_start_refused_while_running(settings, store):
    release = threading.Event()
    entered = threading.Event()

    def slow_sync(*a, **k):
        entered.set()
        assert release.wait(timeout=5)
        return completed_meta()

    runner, _ = make_runner(settings, store, slow_sync)
    assert runner.start() is True
    assert entered.wait(timeout=5)
    assert runner.status().state == "running"
    assert runner.start() is False  # refused, no second thread
    release.set()
    runner.join(timeout=5)
    assert runner.status().state == "complete"


def test_restart_after_failure_and_after_partial_is_allowed(settings, store):
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("network")
        return completed_meta()

    runner, _ = make_runner(settings, store, flaky)
    runner.start()
    runner.join(timeout=5)
    assert runner.status().state == "failed"
    assert runner.start() is True  # re-trigger resumes (journal semantics)
    runner.join(timeout=5)
    status = runner.status()
    assert status.state == "complete"
    assert status.error is None  # stale failure never leaks into a new run


def test_client_factory_error_is_a_failed_run(settings, store):
    def bad_factory():
        raise RuntimeError("no client")

    runner = SyncRunner(
        settings, store, client_factory=bad_factory,
        run_sync_fn=lambda *a, **k: pytest.fail("must not run without a client"),
    )
    runner.start()
    runner.join(timeout=5)
    assert runner.status().state == "failed"
    assert "no client" in runner.status().error
