"""Scan HTTP server (022 T019, contracts/scan-api.md).

App factory with every collaborator injected (settings, LLM client,
Discogs client, snapshot store, session) so tests drive it fully stubbed
via TestClient — no sockets, no live calls.

Write gate (research R9): the ONLY writing route is POST /api/add; it
requires a release_id the server itself served as a candidate this
session (allowlist) and, for duplicate-marked releases, an explicit
confirm_duplicate=true. The vision step has no path to a write.

Secrets: nothing in any response — the page, candidate payloads, and
error bodies carry no token and no API key (FR-017).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from collection_agent.discogs.client import DiscogsError
from collection_agent.scan.journal import JournalWriteError
from collection_agent.scan.models import (
    AddRequest,
    AddResponse,
    EvidenceSummary,
    ScanResponse,
    SessionResponse,
    SkipRequest,
)
from collection_agent.scan.search import (
    find_candidates,
    find_candidates_text,
    snapshot_duplicate_checker,
)
from collection_agent.scan.session import ScanSession
from collection_agent.scan.vision import VisionExtractionError, extract_evidence
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore

_STATIC_DIR = Path(__file__).resolve().parent / "static"

NO_MATCH_MESSAGE = (
    "Couldn't identify this record from the photo — nothing legible enough "
    "to search with. Try another angle, or use manual search below."
)
NO_RESULTS_MESSAGE = (
    "No Discogs release matched what the photo shows. Try manual search "
    "with anything you can read on the record."
)


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


class _CycleContext:
    """Per-scan_id context the outcome journal needs later (source,
    evidence kinds/values, candidate titles served)."""

    def __init__(
        self,
        source: str,
        evidence_kinds: list[str],
        evidence_fields: dict | None = None,
    ):
        self.source = source
        self.evidence_kinds = evidence_kinds
        # FR-021: extracted values (photo) / query (manual) for the journal
        self.evidence_fields = evidence_fields or {}
        self.titles: dict[int, str] = {}
        self.has_candidates = False


def create_app(
    settings: Settings,
    llm_client: Any,
    discogs_client: Any,
    store: SnapshotStore,
    session: ScanSession,
    username: str,
) -> FastAPI:
    app = FastAPI(title="collection-agent scan", docs_url=None, redoc_url=None)
    cycles: dict[str, _CycleContext] = {}
    # 023 FR-007: photo retention exists ONLY behind the opt-in flag — with
    # it off, no retention code runs and behavior is byte-identical to 022
    retainer = None
    if settings.scan_retain_photos:
        from collection_agent.scan.retention import PhotoRetainer

        retainer = PhotoRetainer(settings.scan_retention_dir, session.session_id)
    # FR-023: handlers are sync `def`s (threadpool) so a slow vision call
    # never blocks other requests; this lock guards session/cycle state
    state_lock = threading.Lock()
    generation = {"current": 0}

    def _duplicate_checker():
        # fresh per request: reads the snapshot as it is NOW (it may have
        # been marked stale by a previous add this session) + session adds
        return snapshot_duplicate_checker(store, session)

    def _snapshot_state() -> str:
        snap = store.load()
        return snap.meta.completeness.value if snap else "missing"

    def _register(scan_id: str, ctx: _CycleContext, candidates) -> None:
        ctx.has_candidates = bool(candidates)
        for c in candidates:
            ctx.titles[c.release_id] = c.title
        cycles[scan_id] = ctx
        session.register_candidates([c.release_id for c in candidates])

    def _begin_cycle() -> int:
        """FR-022/023 (addendum 2): a new scan/search supersedes everything
        before it — bump the generation (in-flight identifications discard
        their results when they resume) and auto-close every still-open
        cycle. Open cycles by construction had candidates (no-match/failed
        cycles close at their own time), so the outcome is `skipped`.
        Raises JournalWriteError (caller maps to 500)."""
        with state_lock:
            generation["current"] += 1
            for scan_id, ctx in list(cycles.items()):
                if not session.is_closed(scan_id):
                    session.record_outcome(
                        scan_id,
                        "skipped",
                        ctx.source,
                        evidence_kinds=ctx.evidence_kinds,
                        evidence=ctx.evidence_fields,
                        detail="auto-closed: superseded by a new scan",
                    )
            return generation["current"]

    def _superseded(gen: int) -> bool:
        with state_lock:
            return gen != generation["current"]

    def _superseded_response() -> JSONResponse:
        return _error(
            409,
            "superseded",
            "A newer scan started — this one was discarded.",
        )

    # -- page + health --------------------------------------------------------

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "session_id": session.session_id,
            "snapshot": _snapshot_state(),
        }

    # -- identify --------------------------------------------------------------

    @app.post("/api/scan")
    def scan(photo: UploadFile = File(...)):
        if photo.content_type is None or not photo.content_type.startswith("image/"):
            return _error(
                415,
                "unsupported_media_type",
                "The upload wasn't an image. Send a photo (JPEG/PNG/WebP/HEIC).",
            )
        image_bytes = photo.file.read()
        if len(image_bytes) > settings.scan_max_image_bytes:
            cap_mib = settings.scan_max_image_bytes / (1024 * 1024)
            return _error(
                413,
                "image_too_large",
                f"Photo is larger than the {cap_mib:.0f} MiB upload cap — "
                "retake at lower resolution.",
            )

        # 023 FR-008: retain the original bytes BEFORE any identification
        # outcome exists; failure is loud in the log but never in the flow
        retained = (
            retainer.save_pending(image_bytes, photo.content_type)
            if retainer is not None
            else None
        )

        try:
            gen = _begin_cycle()
        except JournalWriteError as exc:
            return _error(500, "journal_error", str(exc))

        try:
            evidence = extract_evidence(
                llm_client, settings, image_bytes, photo.content_type
            )
        except VisionExtractionError as exc:
            if _superseded(gen):
                return _superseded_response()
            return _error(
                502,
                "vision_unavailable",
                f"Could not read the photo right now: {exc}",
            )
        if _superseded(gen):
            # FR-023: a newer scan started while vision ran — discard
            return _superseded_response()

        summary = EvidenceSummary(
            kinds=list(evidence.evidence_kinds),
            fields=evidence.model_dump(exclude={"notes"}),
        )
        ctx = _CycleContext(
            "photo", list(evidence.evidence_kinds), evidence.compact_dump()
        )

        if evidence.is_empty:
            with state_lock:
                if gen != generation["current"]:
                    return _superseded_response()
                scan_id = session.next_scan_id()
                if retainer is not None:
                    retainer.assign(retained, scan_id)
                try:
                    session.record_outcome(
                        scan_id, "no_match", "photo", evidence_kinds=[],
                        evidence=ctx.evidence_fields,
                    )
                except JournalWriteError as exc:
                    return _error(500, "journal_error", str(exc))
                cycles[scan_id] = ctx
            return ScanResponse(
                scan_id=scan_id,
                source="photo",
                evidence_summary=summary,
                candidates=[],
                more_matches=False,
                message=NO_MATCH_MESSAGE,
            )

        try:
            candidates, more_matches, tried = find_candidates(
                discogs_client, settings, evidence, _duplicate_checker()
            )
        except DiscogsError as exc:
            if _superseded(gen):
                return _superseded_response()
            return _error(
                502, "discogs_unavailable", f"Discogs search failed: {exc}"
            )

        # journal truth: the rungs actually attempted (incl. the FR-020
        # free-text fallback), not just what was extracted
        ctx.evidence_kinds = tried
        with state_lock:
            if gen != generation["current"]:
                return _superseded_response()
            scan_id = session.next_scan_id()
            if retainer is not None:
                retainer.assign(retained, scan_id)
            _register(scan_id, ctx, candidates)
            message = None
            if not candidates:
                try:
                    session.record_outcome(
                        scan_id,
                        "no_match",
                        "photo",
                        evidence_kinds=ctx.evidence_kinds,
                        evidence=ctx.evidence_fields,
                    )
                except JournalWriteError as exc:
                    return _error(500, "journal_error", str(exc))
                message = NO_RESULTS_MESSAGE
        return ScanResponse(
            scan_id=scan_id,
            source="photo",
            evidence_summary=summary,
            candidates=candidates,
            more_matches=more_matches,
            message=message,
        )

    @app.get("/api/search")
    def manual_search(q: str = ""):
        query = q.strip()
        if not query:
            return _error(400, "empty_query", "Type something to search for.")
        try:
            gen = _begin_cycle()
        except JournalWriteError as exc:
            return _error(500, "journal_error", str(exc))
        try:
            candidates, more_matches = find_candidates_text(
                discogs_client, settings, query, _duplicate_checker()
            )
        except DiscogsError as exc:
            if _superseded(gen):
                return _superseded_response()
            return _error(
                502, "discogs_unavailable", f"Discogs search failed: {exc}"
            )
        with state_lock:
            if gen != generation["current"]:
                return _superseded_response()
            scan_id = session.next_scan_id()
            _register(
                scan_id,
                _CycleContext("manual_search", ["text"], {"q": query}),
                candidates,
            )
        return ScanResponse(
            scan_id=scan_id,
            source="manual_search",
            evidence_summary=EvidenceSummary(kinds=["text"], fields={"q": query}),
            candidates=candidates,
            more_matches=more_matches,
            message=None if candidates else NO_RESULTS_MESSAGE,
        )

    # -- write gate --------------------------------------------------------------

    @app.post("/api/add")
    def add(req: AddRequest):
        if not session.is_known_candidate(req.release_id):
            return _error(
                403,
                "unknown_candidate",
                "That release was not offered as a candidate in this "
                "session — nothing was added.",
            )
        ctx = cycles.get(req.scan_id) or _CycleContext("photo", [])
        title = ctx.titles.get(req.release_id)

        duplicate = _duplicate_checker()(req.release_id)
        is_duplicate = (
            duplicate.state == "in_collection" or duplicate.added_this_session
        )
        if is_duplicate and not req.confirm_duplicate:
            return AddResponse(
                status="needs_duplicate_confirmation",
                release_id=req.release_id,
                duplicate=duplicate,
                detail=(
                    f"Already in your collection ({duplicate.copies} "
                    f"cop{'y' if duplicate.copies == 1 else 'ies'}) — confirm "
                    "again to add another copy."
                ),
            )

        try:
            result = discogs_client.add_to_collection(
                username, settings.scan_target_folder_id, req.release_id
            )
        except DiscogsError as exc:
            try:
                with state_lock:
                    session.record_outcome(
                        req.scan_id,
                        "failed",
                        ctx.source,
                        evidence_kinds=ctx.evidence_kinds,
                        release_id=req.release_id,
                        release_title=title,
                        detail=f"add failed: {exc}",
                        evidence=ctx.evidence_fields,
                    )
            except JournalWriteError as journal_exc:
                return _error(500, "journal_error", str(journal_exc))
            return AddResponse(
                status="failed",
                release_id=req.release_id,
                detail=f"Discogs rejected the add: {exc}",
            )

        instance_id = result.get("instance_id")
        try:
            with state_lock:
                session.record_outcome(
                    req.scan_id,
                    "added",
                    ctx.source,
                    evidence_kinds=ctx.evidence_kinds,
                    release_id=req.release_id,
                    release_title=title,
                    instance_id=instance_id,
                    duplicate_add=is_duplicate,
                    evidence=ctx.evidence_fields,
                )
                session.record_add(req.release_id)
        except JournalWriteError as exc:
            # the live add DID happen — be honest about both facts
            return _error(
                500,
                "journal_error",
                f"The release was added on Discogs but the session journal "
                f"could not be written: {exc}",
            )
        store.mark_stale()
        return AddResponse(
            status="added",
            release_id=req.release_id,
            instance_id=instance_id,
            duplicate=duplicate,
            detail="Added to your Discogs collection.",
        )

    # -- cycle close + log ---------------------------------------------------------

    @app.post("/api/skip")
    def skip(req: SkipRequest):
        with state_lock:
            if session.is_closed(req.scan_id):
                return {"status": "skipped"}
            ctx = cycles.get(req.scan_id) or _CycleContext("photo", [])
            outcome = (
                "skipped" if (ctx.has_candidates or req.release_id) else "no_match"
            )
            try:
                session.record_outcome(
                    req.scan_id,
                    outcome,
                    ctx.source,
                    evidence_kinds=ctx.evidence_kinds,
                    release_id=req.release_id,
                    release_title=ctx.titles.get(req.release_id)
                    if req.release_id
                    else None,
                    evidence=ctx.evidence_fields,
                )
            except JournalWriteError as exc:
                return _error(500, "journal_error", str(exc))
        return {"status": "skipped"}

    @app.get("/api/session")
    def session_log() -> SessionResponse:
        with state_lock:
            entries = list(reversed(session.log))
        return SessionResponse(
            session_id=session.session_id,
            entries=entries,
        )

    return app
