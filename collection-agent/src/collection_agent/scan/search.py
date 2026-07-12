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
from collection_agent.tools.common import master_page_url, release_page_url_for_id

DuplicateChecker = Callable[[int], DuplicateStatus]

# 024 (amendment-022-scan-api §2): separator characters ignored when
# comparing catalog numbers — same character-class discipline as 022's
# barcode-in-catno normalization (FR-019 there)
_CATNO_SEPARATORS = str.maketrans("", "", " -./_")


def normalize_catno(value: str) -> str:
    """Separator-stripped, casefolded catno for exact-match comparison:
    'SUB 15' ≡ 'sub-15' ≡ 'SUB15', while 'SUB 150' stays distinct."""
    return value.translate(_CATNO_SEPARATORS).casefold()


def _is_exact_catno(result: dict, searched_normalized: str) -> bool:
    """True when ANY of the result's (comma-joined) catnos normalizes equal
    to the searched catno; a result with no catno is never exact."""
    raw = result.get("catno")
    if not raw:
        return False
    return any(
        normalize_catno(part) == searched_normalized
        for part in str(raw).split(",")
        if part.strip()
    )


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
    """Search params per available evidence, strongest first (FR-004).
    The composed free-text fallback (FR-020) is appended last: it fires
    only when every structured rung is absent or returned zero results."""
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
    query = compose_query(evidence)
    if query:
        rungs.append(("text", {"q": query}))
    return rungs


def compose_query(evidence: ScanEvidence) -> str | None:
    """FR-020 (addendum 1, live finding F2): one free-text query from the
    partial evidence — artist, title (or the lead track: on 12" singles
    the lead track IS the release title), label. Barcode/catno are left
    out: their structured rungs already ran, and digit runs pollute q=."""
    parts = [
        evidence.artist,
        evidence.title or (evidence.tracks[0] if evidence.tracks else None),
        evidence.label,
    ]
    query = " ".join(p for p in parts if p)
    return query or None


def _candidate_from_result(
    result: dict, settings: Settings, duplicate_checker: DuplicateChecker
) -> Candidate:
    """Verbatim mapping; the only transformation is str() on a numeric year
    (Discogs sends search years as strings; be tolerant, never invent).
    026: plus the two server-built page links (never from the payload —
    tools/common owns the URL shapes; master link iff master_id)."""
    year = result.get("year")
    thumb = result.get("thumb") or result.get("cover_image") or None
    release_id = int(result["id"])
    master_id = int(result["master_id"]) if result.get("master_id") else None
    return Candidate(
        release_id=release_id,
        title=result["title"],
        year=str(year) if year is not None else None,
        country=result.get("country"),
        formats=list(result.get("format") or []),
        labels=list(result.get("label") or []),
        catno=result.get("catno"),
        thumb_url=thumb,
        discogs_uri=result.get("uri"),
        # 024: master_id verbatim; Discogs uses 0/absent for "no master"
        master_id=master_id,
        release_page_url=release_page_url_for_id(settings, release_id),
        master_page_url=(
            master_page_url(settings, master_id) if master_id else None
        ),
        duplicate=duplicate_checker(release_id),
    )


def _run_search(
    client,
    settings: Settings,
    params: dict,
    duplicate_checker: DuplicateChecker,
    per_page: int | None = None,
    exact_catno: str | None = None,
) -> tuple[list[Candidate], bool]:
    payload = client.search_releases(
        {**params, "per_page": per_page or settings.scan_candidates_max, "page": 1}
    )
    results = payload.get("results") or []
    if exact_catno is not None:
        # 024 FR-002: stable partition on the RAW results — exact normalized
        # catno matches first, source order preserved within each group;
        # dedup/cap/verbatim Candidate build below are unchanged. When no
        # exact match exists this is a no-op (byte-identical order).
        searched = normalize_catno(exact_catno)
        results = sorted(
            results, key=lambda r: 0 if _is_exact_catno(r, searched) else 1
        )
    candidates: list[Candidate] = []
    seen: set[int] = set()
    for result in results:
        rid = int(result["id"])
        if rid in seen:
            continue
        seen.add(rid)
        candidates.append(_candidate_from_result(result, settings, duplicate_checker))
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
        # 024 FR-001: the catno rung fetches a deeper single page so the
        # exact-catno re-rank can surface matches Discogs' substring search
        # buried; every other rung is byte-identical to pre-024 behavior
        depth = (
            max(settings.scan_catno_search_depth, settings.scan_candidates_max)
            if rung == "catno"
            else None
        )
        candidates, more = _run_search(
            client, settings, params, duplicate_checker,
            per_page=depth,
            exact_catno=params.get("catno") if rung == "catno" else None,
        )
        if candidates:
            return candidates, more, tried
    return [], False, tried


def candidates_from_versions(
    payload: dict,
    master_id: int,
    settings: Settings,
    duplicate_checker: DuplicateChecker,
    exclude_ids: set[int],
) -> tuple[list[Candidate], int]:
    """Map a GET /masters/{id}/versions payload to candidates (026,
    data-model §2). Verbatim discipline: the only transformations are the
    same ones search tolerates — str() on the year and list-wrapping the
    payload's single format/label strings (never split/parsed). Items whose
    release_id is already registered in the requesting cycle (incl. the
    selected release itself — the list contains it) are dropped, so the
    result is honestly OTHER pressings. Returns (candidates, total) where
    total is pagination.items verbatim (FR-013 honesty)."""
    versions = payload.get("versions") or []
    total = int(payload.get("pagination", {}).get("items", len(versions)))
    candidates: list[Candidate] = []
    seen: set[int] = set(exclude_ids)
    for item in versions:
        release_id = int(item["id"])
        if release_id in seen:
            continue
        seen.add(release_id)
        released = item.get("released")
        fmt = item.get("format")
        label = item.get("label")
        candidates.append(
            Candidate(
                release_id=release_id,
                title=item["title"],
                year=str(released) if released else None,
                country=item.get("country"),
                formats=[fmt] if fmt else [],
                labels=[label] if label else [],
                catno=item.get("catno"),
                thumb_url=item.get("thumb") or None,
                discogs_uri=None,
                # the requested master, validated server-side against the
                # cycle's own candidates — genuine by construction
                master_id=master_id,
                release_page_url=release_page_url_for_id(settings, release_id),
                master_page_url=master_page_url(settings, master_id),
                duplicate=duplicate_checker(release_id),
            )
        )
    return candidates, total


def find_candidates_text(
    client,
    settings: Settings,
    query: str,
    duplicate_checker: DuplicateChecker = pending_duplicate_checker,
) -> tuple[list[Candidate], bool]:
    """Free-text rung (manual search, FR-012)."""
    return _run_search(client, settings, {"q": query}, duplicate_checker)
