"""Evidence -> candidate pipeline (022 T017, FR-004/005/006).

Precision ladder: barcode -> catno(+label) -> artist+title; a lower rung
runs only when higher-precision evidence is absent or returned zero
results. Manual search is the same pipeline entered at the free-text
rung. Every Candidate field is copied VERBATIM from the search result —
absent keys stay absent, nothing is constructed or backfilled from
evidence (019 discipline).

Duplicate status arrives through an injectable checker so US1 works
before the snapshot overlay (US2) lands; the placeholder is an explicit
`unknown`, never a fabricated `not_in_collection` (FR-010).
"""

from __future__ import annotations

from collections.abc import Callable

from collection_agent.scan.models import Candidate, DuplicateStatus, ScanEvidence
from collection_agent.settings import Settings

DuplicateChecker = Callable[[int], DuplicateStatus]


def pending_duplicate_checker(_release_id: int) -> DuplicateStatus:
    return DuplicateStatus(state="unknown", reason="duplicate check pending")


def snapshot_duplicate_checker(store, session) -> DuplicateChecker:
    """Duplicate overlay (US2 T023, FR-009/010): snapshot instance counts +
    this session's adds. Build one per request — it loads the snapshot once.

    Degradation rules (data-model.md): missing/unreadable snapshot ->
    unknown("no snapshot"); presence in ANY snapshot shows its count (plus
    session adds); absence is `not_in_collection` ONLY from a complete
    snapshot — a partial/stale snapshot's absence degrades to unknown,
    never to a false "not in your collection". A release added this
    session is always `in_collection` regardless of snapshot state.
    """
    from collection_agent.models import Completeness

    snapshot = None
    try:
        snapshot = store.load()
    except Exception:  # unreadable/corrupt file — degrade, never guess
        snapshot = None

    counts: dict[int, int] = {}
    completeness = None
    if snapshot is not None:
        completeness = snapshot.meta.completeness
        for record in snapshot.records:
            counts[record.release_id] = counts.get(record.release_id, 0) + 1

    def check(release_id: int) -> DuplicateStatus:
        session_copies = session.added_release_ids.get(release_id, 0)
        snap_copies = counts.get(release_id, 0)
        if session_copies:
            return DuplicateStatus(
                state="in_collection",
                copies=snap_copies + session_copies,
                added_this_session=True,
            )
        if snapshot is None:
            return DuplicateStatus(state="unknown", reason="no snapshot")
        if snap_copies:
            reason = (
                None
                if completeness == Completeness.COMPLETE
                else f"count as of last sync (snapshot {completeness.value})"
            )
            return DuplicateStatus(
                state="in_collection", copies=snap_copies, reason=reason
            )
        if completeness == Completeness.COMPLETE:
            return DuplicateStatus(state="not_in_collection")
        return DuplicateStatus(
            state="unknown", reason=f"snapshot {completeness.value}"
        )

    return check


def evidence_rungs(evidence: ScanEvidence) -> list[tuple[str, dict]]:
    """Search params per available evidence, strongest first (FR-004)."""
    rungs: list[tuple[str, dict]] = []
    if evidence.barcode:
        rungs.append(("barcode", {"barcode": evidence.barcode}))
    if evidence.catno:
        params = {"catno": evidence.catno}
        if evidence.label:
            params["label"] = evidence.label
        rungs.append(("catno", params))
    if evidence.artist and evidence.title:
        rungs.append(
            ("artist_title", {"artist": evidence.artist, "release_title": evidence.title})
        )
    return rungs


def _candidate_from_result(
    result: dict, duplicate_checker: DuplicateChecker
) -> Candidate:
    """Verbatim mapping; the only transformation is str() on a numeric year
    (Discogs sends search years as strings; be tolerant, never invent)."""
    year = result.get("year")
    thumb = result.get("thumb") or result.get("cover_image") or None
    return Candidate(
        release_id=int(result["id"]),
        title=result["title"],
        year=str(year) if year is not None else None,
        country=result.get("country"),
        formats=list(result.get("format") or []),
        labels=list(result.get("label") or []),
        catno=result.get("catno"),
        thumb_url=thumb,
        discogs_uri=result.get("uri"),
        duplicate=duplicate_checker(int(result["id"])),
    )


def _run_search(
    client,
    settings: Settings,
    params: dict,
    duplicate_checker: DuplicateChecker,
) -> tuple[list[Candidate], bool]:
    payload = client.search_releases(
        {**params, "per_page": settings.scan_candidates_max, "page": 1}
    )
    results = payload.get("results") or []
    candidates: list[Candidate] = []
    seen: set[int] = set()
    for result in results:
        rid = int(result["id"])
        if rid in seen:
            continue
        seen.add(rid)
        candidates.append(_candidate_from_result(result, duplicate_checker))
        if len(candidates) >= settings.scan_candidates_max:
            break
    total = int(payload.get("pagination", {}).get("items", len(results)))
    more_matches = total > len(candidates)
    return candidates, more_matches


def find_candidates(
    client,
    settings: Settings,
    evidence: ScanEvidence,
    duplicate_checker: DuplicateChecker = pending_duplicate_checker,
) -> tuple[list[Candidate], bool, list[str]]:
    """Walk the ladder; returns (candidates, more_matches, rungs_tried)."""
    tried: list[str] = []
    for rung, params in evidence_rungs(evidence):
        tried.append(rung)
        candidates, more = _run_search(client, settings, params, duplicate_checker)
        if candidates:
            return candidates, more, tried
    return [], False, tried


def find_candidates_text(
    client,
    settings: Settings,
    query: str,
    duplicate_checker: DuplicateChecker = pending_duplicate_checker,
) -> tuple[list[Candidate], bool]:
    """Free-text rung (manual search, FR-012)."""
    return _run_search(client, settings, {"q": query}, duplicate_checker)
