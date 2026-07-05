"""Two-phase collection sync (research R6; contracts/discogs-consumption.md §2).

Phase 1 — instance pass: folders, collection value, and every instance from
collection folder 0 (= All) with `basic_information`. Cheap (~10 requests
for 1k instances at per_page=100).

Phase 2 — enrichment pass: `GET /releases/{id}` once per *unique* release —
country, videos, community stats, market signals. Results are journaled
incrementally (atomic), so an interrupted sync resumes without re-fetching;
`full=True` ignores the journal and re-enriches everything.

The final snapshot is written once, atomically, at the end. Completeness:
- complete: every unique release enriched or 404-warned
- partial:  some enrichments failed (server errors) or the sync was
            interrupted before finishing (journal survives for resume)

Progress reporting is callback-based (`on_progress(phase, done, total)`) so
the CLI can render rich bars and tests can stay silent.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from collection_agent.discogs.client import DiscogsClient, DiscogsServerError
from collection_agent.models import (
    CollectionRecord,
    CollectionValue,
    Completeness,
    Folder,
    LabelRef,
    MediaLink,
    Snapshot,
    SnapshotMeta,
    SyncStats,
)
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore, utcnow_iso

ProgressFn = Callable[[str, int, int], None]
_JOURNAL_FLUSH_EVERY = 10


class SyncInterrupted(Exception):
    """Raised internally to surface a clean partial result on Ctrl-C."""


def run_sync(
    client: DiscogsClient,
    store: SnapshotStore,
    settings: Settings,
    full: bool = False,
    on_progress: ProgressFn | None = None,
    notify: Callable[[str], None] | None = None,
) -> SnapshotMeta:
    """Run/resume a sync. Returns the final SnapshotMeta (also persisted)."""
    progress = on_progress or (lambda _p, _d, _t: None)
    say = notify or (lambda _m: None)
    warnings: list[str] = []
    started = time.monotonic()
    requests_before = 0  # governor doesn't count; we count coarse steps

    # --- phase 1: identity, folders, value, instances -----------------------
    identity = client.get_identity()
    username = identity.get("username") or settings.discogs_username
    if not username:
        raise RuntimeError("could not resolve username from /oauth/identity")
    if settings.discogs_username and settings.discogs_username != username:
        say(
            f"DISCOGS_USERNAME={settings.discogs_username!r} does not match the "
            f"token identity {username!r}; using the token identity."
        )

    folders = [
        Folder(
            folder_id=int(f["id"]), name=str(f["name"]), count=int(f.get("count", 0))
        )
        for f in client.get_folders(username)
    ]

    value = CollectionValue()
    try:
        raw_value = client.get_collection_value(username)
        value = CollectionValue(
            minimum=raw_value.get("minimum"),
            median=raw_value.get("median"),
            maximum=raw_value.get("maximum"),
        )
    except DiscogsServerError as exc:
        warnings.append(f"collection value unavailable: {exc}")

    records: list[CollectionRecord] = []
    total_pages = 1
    page_no = 0
    for page in client.iter_collection_pages(username):
        page_no += 1
        total_pages = int(page.get("pagination", {}).get("pages", page_no))
        for item in page.get("releases", []):
            records.append(_record_from_instance(item))
        progress("instances", page_no, total_pages)
        requests_before += 1

    unique_ids = sorted({r.release_id for r in records})

    # --- phase 2: per-release enrichment (journaled, resumable) -------------
    journal: dict[int, dict[str, Any]] = {} if full else store.load_journal()
    pending = [rid for rid in unique_ids if rid not in journal]
    done = len(unique_ids) - len(pending)
    progress("enrichment", done, len(unique_ids))

    interrupted = False
    failed: list[int] = []
    try:
        for i, rid in enumerate(pending, start=1):
            try:
                detail = client.get_release(rid)
            except DiscogsServerError as exc:
                failed.append(rid)
                warnings.append(f"release {rid} enrichment failed: {exc}")
                continue
            if detail is None:
                journal[rid] = {"_404": True}
                warnings.append(f"release {rid} returned 404; kept without enrichment")
            else:
                journal[rid] = _enrichment_from_release(detail)
            if i % _JOURNAL_FLUSH_EVERY == 0:
                store.save_journal(journal)
            progress("enrichment", done + i, len(unique_ids))
    except KeyboardInterrupt:
        interrupted = True
        say("sync interrupted — progress journaled; re-run `sync` to resume.")
    finally:
        store.save_journal(journal)

    # --- merge + persist ------------------------------------------------------
    enriched_at = utcnow_iso()
    for rec in records:
        enr = journal.get(rec.release_id)
        if enr and not enr.get("_404"):
            _apply_enrichment(rec, enr, enriched_at)

    enriched_count = sum(
        1 for rid in unique_ids if rid in journal  # includes 404-warned
    )
    completeness = (
        Completeness.COMPLETE
        if not interrupted and not failed and enriched_count == len(unique_ids)
        else Completeness.PARTIAL
    )

    meta = SnapshotMeta(
        username=username,
        synced_at=enriched_at,
        completeness=completeness,
        instance_count=len(records),
        unique_release_count=len(unique_ids),
        enriched_count=enriched_count,
        collection_value=value,
        sync_stats=SyncStats(
            requests=requests_before + len(pending) + 3,
            duration_s=round(time.monotonic() - started, 1),
            warnings=warnings,
        ),
    )
    store.save(Snapshot(meta=meta, folders=folders, records=records))
    if completeness == Completeness.COMPLETE:
        store.clear_journal()  # everything is in the snapshot now
    return meta


# --- payload mapping ---------------------------------------------------------


def _record_from_instance(item: dict[str, Any]) -> CollectionRecord:
    basic = item.get("basic_information", {})
    return CollectionRecord(
        instance_id=int(item["instance_id"]),
        release_id=int(basic.get("id") or item.get("id")),
        folder_id=int(item.get("folder_id", 1)),
        date_added=item.get("date_added"),
        my_rating=item.get("rating"),
        title=str(basic.get("title", "")),
        artists=[a.get("name", "") for a in basic.get("artists", []) if a.get("name")],
        year=basic.get("year"),
        labels=[
            LabelRef(name=l.get("name", ""), catno=l.get("catno") or None)
            for l in basic.get("labels", [])
            if l.get("name")
        ],
        formats=_flatten_formats(basic.get("formats", [])),
        genres=list(basic.get("genres", []) or []),
        styles=list(basic.get("styles", []) or []),
    )


def _flatten_formats(formats: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for f in formats:
        if f.get("name"):
            out.append(str(f["name"]))
        out.extend(str(d) for d in f.get("descriptions", []) or [])
    # dedupe, keep order
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _enrichment_from_release(detail: dict[str, Any]) -> dict[str, Any]:
    community = detail.get("community", {}) or {}
    rating = community.get("rating", {}) or {}
    return {
        "country": detail.get("country"),
        "genres": list(detail.get("genres", []) or []),
        "styles": list(detail.get("styles", []) or []),
        "community_have": community.get("have"),
        "community_want": community.get("want"),
        "community_rating_avg": rating.get("average"),
        "community_rating_count": rating.get("count"),
        "num_for_sale": detail.get("num_for_sale"),
        "lowest_price": detail.get("lowest_price"),
        "videos": [
            {
                "uri": v.get("uri"),
                "title": v.get("title"),
                "duration_s": v.get("duration"),
            }
            for v in detail.get("videos", []) or []
            if v.get("uri")
        ],
    }


def _apply_enrichment(
    rec: CollectionRecord, enr: dict[str, Any], enriched_at: str
) -> None:
    rec.country = enr.get("country")
    if enr.get("genres"):
        rec.genres = enr["genres"]  # release detail is authoritative
    if enr.get("styles"):
        rec.styles = enr["styles"]
    rec.community_have = enr.get("community_have")
    rec.community_want = enr.get("community_want")
    rec.community_rating_avg = enr.get("community_rating_avg")
    rec.community_rating_count = enr.get("community_rating_count")
    rec.num_for_sale = enr.get("num_for_sale")
    rec.lowest_price = enr.get("lowest_price")
    rec.videos = [MediaLink(**v) for v in enr.get("videos", [])]
    rec.enriched_at = enriched_at
