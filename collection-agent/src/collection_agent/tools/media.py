"""US3 media-links tool (FR-014/015/016; contracts/agent-tools.md §1).

Returns the music/video links stored in each record's Discogs metadata —
URIs verbatim (signed URLs are never edited; snapshot-schema invariant 6),
grouped per record, with an explicit `none` flag when a record has no
linked media. Records resolve by instance id, by a name mention
("alex smoke simple things"), or from the session's last listing
("those" / "esos") — so it works standalone or chained after
filter_records.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from collection_agent.agent import AgentSession, ToolDef
from collection_agent.models import CollectionRecord
from collection_agent.registry import fold
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.tools.common import load_for_serving, with_warnings


class MediaLinksArgs(BaseModel):
    record_refs: list[str] = Field(
        default_factory=list,
        description="Records to look up: instance ids (as strings) and/or "
        'name mentions like "Alex Smoke - Simple Things". Leave empty with '
        "use_last_listing=true to use the previous listing.",
    )
    use_last_listing: bool = Field(
        default=False,
        description="Use the records from the session's last filter_records "
        'result (the user said "those records", "esos", …).',
    )


def _resolve(
    refs: list[str],
    use_last: bool,
    session: AgentSession,
    records: list[CollectionRecord],
) -> tuple[list[CollectionRecord], list[str]]:
    by_instance = {r.instance_id: r for r in records}
    resolved: list[CollectionRecord] = []
    not_found: list[str] = []
    seen: set[int] = set()

    def add(rec: CollectionRecord) -> None:
        if rec.instance_id not in seen:
            seen.add(rec.instance_id)
            resolved.append(rec)

    if use_last:
        if not session.last_listing_instance_ids:
            not_found.append("(no previous listing in this session)")
        for iid in session.last_listing_instance_ids:
            if iid in by_instance:
                add(by_instance[iid])

    for ref in refs:
        ref = ref.strip()
        if ref.isdigit() and int(ref) in by_instance:
            add(by_instance[int(ref)])
            continue
        needle = fold(ref)
        hits = [
            r for r in records
            if needle and needle in fold(" ".join([*r.artists, r.title]))
        ]
        if hits:
            for r in hits:
                add(r)
        else:
            not_found.append(ref)

    return resolved, not_found


def make_media_tools(settings: Settings, store: SnapshotStore) -> list[ToolDef]:
    def media_links(session: AgentSession, args: MediaLinksArgs) -> dict[str, Any]:
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

        per_record = []
        for rec in resolved:
            per_record.append({
                "instance_id": rec.instance_id,
                "artist": ", ".join(rec.artists) or "?",
                "title": rec.title,
                "year": rec.year,
                "links": [
                    {"uri": v.uri, "title": v.title, "duration_s": v.duration_s}
                    for v in rec.videos
                ],
                "none": not rec.videos,  # FR-016: explicit, per record
            })

        payload: dict[str, Any] = {
            "per_record": per_record,
            "records_with_links": sum(1 for p in per_record if not p["none"]),
            "records_without_links": sum(1 for p in per_record if p["none"]),
            "note": "URIs are verbatim from Discogs metadata — do not modify "
            "them. For records marked none=true, state that Discogs has no "
            "linked media for them.",
        }
        if not_found:
            payload["not_found"] = not_found
        return with_warnings(ctx, payload)

    return [
        ToolDef(
            name="media_links",
            description="The music/video links stored in Discogs metadata for one "
            "or more records — grouped per record, with an explicit flag when a "
            "record has none. Accepts instance ids, name mentions, or the last "
            "listing.",
            params_model=MediaLinksArgs,
            fn=media_links,
        )
    ]
