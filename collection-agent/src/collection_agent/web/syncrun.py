"""Single-occupancy background sync (028 FR-009, research R5).

A thin occupancy + observability shell over the UNCHANGED
`snapshot.sync.run_sync`: one daemon thread, its own DiscogsClient
(closed in `finally`), progress mirrored from the existing
`on_progress(phase, done, total)` callback into a lock-guarded status
snapshot, `notify` messages collected as warnings.

The web sync is ALWAYS the standard sync (`full=False` — 028
clarification 2026-07-12): resume if interrupted, refresh otherwise.

Daemon thread is deliberate (research R5): killing the server mid-run
equals the already-designed-for interrupted sync — the enrichment
journal (flushed every 10 releases) survives and the next run resumes.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from collection_agent.models import Completeness
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore, utcnow_iso
from collection_agent.web.models import SyncStatusView


def _default_client_factory(settings: Settings) -> Callable[[], Any]:
    def factory():
        from collection_agent.discogs.client import DiscogsClient

        return DiscogsClient(settings)

    return factory


def _default_run_sync(*args, **kwargs):
    from collection_agent.snapshot.sync import run_sync

    return run_sync(*args, **kwargs)


class SyncRunner:
    """At most one run at a time; `start()` is check-and-start atomic."""

    def __init__(
        self,
        settings: Settings,
        store: SnapshotStore,
        client_factory: Callable[[], Any] | None = None,
        run_sync_fn: Callable[..., Any] | None = None,
    ):
        self._settings = settings
        self._store = store
        self._client_factory = client_factory or _default_client_factory(settings)
        self._run_sync = run_sync_fn or _default_run_sync
        self._mutex = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = "idle"
        self._phase: str | None = None
        self._done: int | None = None
        self._total: int | None = None
        self._warnings: list[str] = []
        self._error: str | None = None
        self._finished_at: str | None = None

    # -- public surface --------------------------------------------------------

    def start(self) -> bool:
        """Begin a background run; False (and no effect) if one is active."""
        with self._mutex:
            if self._state == "running":
                return False
            self._state = "running"
            self._phase = None
            self._done = None
            self._total = None
            self._warnings = []
            self._error = None
            self._finished_at = None
            self._thread = threading.Thread(
                target=self._run, name="collection-sync", daemon=True
            )
            self._thread.start()
            return True

    def status(self) -> SyncStatusView:
        with self._mutex:
            return SyncStatusView(
                state=self._state,
                phase=self._phase,
                done=self._done,
                total=self._total,
                warnings=list(self._warnings),
                error=self._error,
                finished_at=self._finished_at,
            )

    def join(self, timeout: float | None = None) -> None:
        """Wait for the current run's thread (tests; never used by routes)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    # -- worker -----------------------------------------------------------------

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        with self._mutex:
            self._phase = phase
            self._done = done
            self._total = total

    def _notify(self, message: str) -> None:
        with self._mutex:
            self._warnings.append(message)

    def _run(self) -> None:
        client = None
        try:
            client = self._client_factory()
            meta = self._run_sync(
                client,
                self._store,
                self._settings,
                full=False,
                on_progress=self._on_progress,
                notify=self._notify,
            )
            with self._mutex:
                self._state = (
                    "complete"
                    if meta.completeness == Completeness.COMPLETE
                    else "partial"
                )
                self._finished_at = utcnow_iso()
        except Exception as exc:  # typed data for the page, never a crash
            with self._mutex:
                self._state = "failed"
                self._error = str(exc)
                self._finished_at = utcnow_iso()
        finally:
            close = getattr(client, "close", None)
            if close:
                close()
