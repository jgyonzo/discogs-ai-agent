"""US1 playlist_links: click-to-play YouTube links over stored videos.

Read-only tool (020, agent-tools amendment delta 9): it performs no
network calls and no writes — it assembles play links from the
snapshot's stored `MediaLink` URIs via the deterministic parser in
`youtube_links.py`. Opening a link is the user's action in their
browser; saving/naming the resulting temporary playlist happens on the
YouTube site (payload `save_hint`). Deliberately NOT gated: the §4
write gate exists for account mutations, and this tool has none.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from collection_agent.agent import AgentSession, ToolDef
from collection_agent.models import CollectionRecord
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.tools.common import load_for_serving, with_warnings
from collection_agent.tools.media import _resolve
from collection_agent.youtube_links import (
    build_watch_videos_url,
    chunk_record_videos,
    video_id_from_uri,
)

SAVE_HINT = (
    "Opening a link plays it as a temporary playlist; to keep it, the user "
    "clicks YouTube's 'Save playlist' in the playlist panel and names it "
    "there. The agent cannot save or name playlists in any account."
)


class PlaylistLinksArgs(BaseModel):
    record_refs: list[str] = Field(
        default_factory=list,
        description="Records to include: instance ids (as strings) and/or "
        'name mentions like "Alex Smoke - Simple Things". Leave empty with '
        "use_last_listing=true to use the previous listing.",
    )
    use_last_listing: bool = Field(
        default=False,
        description="Use the records from the session's last listing (the "
        'user said "those records", "the links", "esos"…).',
    )
    suggested_name: str | None = Field(
        default=None,
        description="Playlist name the user asked for — echoed back for the "
        "save-on-site step; the tool cannot name or save playlists.",
    )
    videos_per_record: Literal["all", "first"] = Field(
        default="all",
        description='"first" = one video per record (its first stored one) — '
        'use when the user asks for one track per record / a sampler. '
        'Default "all" includes every stored video.',
    )


def _display(rec: CollectionRecord) -> str:
    return f"{', '.join(rec.artists) or '?'} – {rec.title}"


def make_playlist_tools(settings: Settings, store: SnapshotStore) -> list[ToolDef]:
    def playlist_links(session: AgentSession, args: PlaylistLinksArgs) -> dict[str, Any]:
        ctx = load_for_serving(store)
        if ctx.blocked:
            return ctx.blocked

        resolved, not_found = _resolve(
            args.record_refs, args.use_last_listing, session, ctx.snapshot.records
        )
        if not resolved and not not_found:
            return with_warnings(ctx, {
                "error": "no_records_specified",
                "detail": "Provide record_refs (ids or artist/title mentions) "
                "or set use_last_listing=true after a listing.",
            })
        if not resolved:
            return with_warnings(ctx, {
                "error": "no_records_resolved",
                "not_found": not_found,
                "detail": "None of the referenced records could be resolved in "
                "the collection — ask the user which records to use.",
            })

        # per record: parse ids deterministically, dedup across the request
        seen: dict[str, str] = {}  # video_id -> display of the record that owns it
        covered: list[dict[str, Any]] = []  # {"record": rec, "ids": [...]}
        skipped_records: list[dict[str, Any]] = []
        duplicate_notes: list[str] = []
        for rec in resolved:
            display = _display(rec)
            if not rec.videos:
                skipped_records.append({
                    "instance_id": rec.instance_id,
                    "display": display,
                    "reason": "no_videos",
                })
                continue
            # US3 selection happens before dedup/chunking: "first" takes the
            # record's first STORED video (spec US3), not the first parseable
            selected = (
                rec.videos if args.videos_per_record == "all" else rec.videos[:1]
            )
            parseable = 0
            own_ids: list[str] = []
            for link in selected:
                vid = video_id_from_uri(link.uri)
                if vid is None:
                    continue
                parseable += 1
                if vid in seen:
                    duplicate_notes.append(
                        f"one video appears under both {seen[vid]} and {display} "
                        f"— included once ({seen[vid]})"
                    )
                    continue
                seen[vid] = display
                own_ids.append(vid)
            if parseable == 0:
                skipped_records.append({
                    "instance_id": rec.instance_id,
                    "display": display,
                    "reason": "unresolvable_uri",
                })
                continue
            # parseable videos exist ⇒ the record is covered even if every
            # id was already contributed by an earlier record (dedup note)
            covered.append({"record": rec, "ids": own_ids})

        base_payload: dict[str, Any] = {
            "skipped_records": skipped_records,
            "duplicate_notes": duplicate_notes,
            "videos_per_record": args.videos_per_record,
            "suggested_name": args.suggested_name,
            "save_hint": SAVE_HINT,
        }
        if not_found:
            base_payload["not_found"] = not_found

        all_ids = list(seen)  # insertion order = listing order
        if not all_ids:
            return with_warnings(ctx, {
                **base_payload,
                "links": [],
                "link_count": 0,
                "total_videos": 0,
                "covered_record_count": 0,
                "detail": "None of the records have usable stored videos — "
                "no play link to build. Report the skip reasons; never offer "
                "to search for substitute videos.",
            })

        # chunked build (FR-005): record-aligned, ≤ cap ids per link,
        # disjoint and jointly complete — silent truncation is impossible
        cap = settings.youtube_playlist_max_ids
        ordinal = {
            entry["record"].instance_id: i for i, entry in enumerate(covered, 1)
        }
        chunks = chunk_record_videos(
            [(entry["record"], entry["ids"]) for entry in covered], cap
        )
        links: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks, 1):
            ids = [vid for _, piece in chunk["entries"] for vid in piece]
            positions = [ordinal[rec.instance_id] for rec, _ in chunk["entries"]]
            lo, hi = min(positions), max(positions)
            span = f"record {lo}" if lo == hi else f"records {lo}–{hi}"
            links.append({
                "url": build_watch_videos_url(ids, settings.youtube_web_base_url),
                "index": i,
                "video_count": len(ids),
                "records": [
                    {
                        "instance_id": rec.instance_id,
                        "display": _display(rec),
                        "video_count": len(piece),
                    }
                    for rec, piece in chunk["entries"]
                ],
                "label": f"link {i} — {span} ({len(ids)} videos)",
            })
            for rec in chunk["split"]:
                note = (
                    f"{_display(rec)} has more videos than fit one link — "
                    "its videos span several links"
                )
                if note not in duplicate_notes:
                    duplicate_notes.append(note)

        return with_warnings(ctx, {
            **base_payload,
            "links": links,
            "link_count": len(links),
            "total_videos": len(all_ids),
            "covered_record_count": len(covered),
            "detail": "Links are click-to-play; nothing was created or saved "
            "in any account."
            + (
                f" The videos exceed one link's capacity ({cap}), so they are "
                "split across the labeled links in listing order."
                if len(links) > 1
                else ""
            ),
        })

    return [
        ToolDef(
            name="playlist_links",
            description="Build click-to-play YouTube playlist link(s) from "
            "records' stored videos (the user opens the link; it plays as a "
            "temporary playlist they can save ON THE YOUTUBE SITE — this tool "
            "cannot create or save playlists in any account). Accepts instance "
            "ids, name mentions, or the last listing.",
            params_model=PlaylistLinksArgs,
            fn=playlist_links,
        )
    ]
