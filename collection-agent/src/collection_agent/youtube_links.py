"""Play-link mechanics for the YouTube playlist feature (020).

Pure functions — no network, no snapshot, no LLM. `video_id_from_uri` is
the deterministic parser that keeps video ids out of the LLM's hands
(ground rule 1; 013→014/019 precedent: enforcement over prompt steering),
and `build_watch_videos_url` is the ONLY place the play-link URL shape
exists (contracts/youtube-playlists.md §1, mirroring 019's
`release_page_url` single-source discipline). The `watch_videos` endpoint
is undocumented YouTube behavior — verified live 2026-07-06; its
retirement is an accepted risk recorded in the spec.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

# YouTube video ids are 11 chars of [A-Za-z0-9_-]
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")

_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/")


def video_id_from_uri(uri: str) -> str | None:
    """Extract the video id from a stored MediaLink URI, or None.

    None ⇒ the record is skipped with reason `unresolvable_uri` — never
    guessed at (FR-002/003). Empirically every stored link parses
    (2,798/2,798 snapshot links are standard watch?v= URLs; Discogs only
    accepts YouTube release videos), so this is a defensive guard.
    """
    try:
        parsed = urlparse(uri.strip())
    except (ValueError, AttributeError):
        return None
    host = parsed.netloc.lower().split(":")[0]

    candidate: str | None = None
    if host in _YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [None])[0]
        else:
            for prefix in _PATH_PREFIXES:
                if parsed.path.startswith(prefix):
                    candidate = parsed.path[len(prefix):].split("/")[0]
                    break
    elif host in _SHORT_HOSTS:
        candidate = parsed.path.lstrip("/").split("/")[0]

    if candidate and _VIDEO_ID.fullmatch(candidate):
        return candidate
    return None


def chunk_record_videos(
    per_record_ids: list[tuple[object, list[str]]], cap: int
) -> list[dict]:
    """Split ordered (record, ids) pairs into play-link chunks of ≤ cap videos.

    Record-aligned (FR-005): a chunk boundary never splits a record's videos
    unless that single record alone exceeds the cap — then it splits and the
    record lands in `split` so the caller can note it. Pairs with no ids
    (records whose every video was deduped into an earlier record) ride
    along in the current chunk without consuming capacity. Order is
    preserved throughout; chunks are disjoint and jointly complete.

    Returns dicts: {"entries": [(record, ids_in_this_chunk)],
    "video_count": int, "split": [record, ...]}.
    """
    if cap < 1:
        raise ValueError("cap must be >= 1")
    chunks: list[dict] = []
    current: dict = {"entries": [], "video_count": 0, "split": []}

    def flush() -> None:
        nonlocal current
        if current["video_count"]:
            chunks.append(current)
            current = {"entries": [], "video_count": 0, "split": []}

    for record, ids in per_record_ids:
        if not ids:
            current["entries"].append((record, []))
            continue
        if len(ids) > cap:
            flush()
            for start in range(0, len(ids), cap):
                piece = ids[start : start + cap]
                current["entries"].append((record, piece))
                current["video_count"] += len(piece)
                current["split"].append(record)
                if current["video_count"] == cap:
                    flush()
            continue
        if current["video_count"] + len(ids) > cap:
            flush()
        current["entries"].append((record, ids))
        current["video_count"] += len(ids)

    if current["video_count"]:
        chunks.append(current)
    elif current["entries"] and chunks:
        # trailing all-deduped records ride with the last real chunk
        chunks[-1]["entries"].extend(current["entries"])
    return chunks


def build_watch_videos_url(video_ids: list[str], base_url: str) -> str:
    """The anonymous play link: opens as a temporary, saveable playlist.

    `base_url` comes from settings (VII(a)); ids come exclusively from
    `video_id_from_uri` — callers must never pass LLM-supplied ids.
    """
    if not video_ids:
        raise ValueError("cannot build a play link with no video ids")
    return f"{base_url.rstrip('/')}/watch_videos?video_ids={','.join(video_ids)}"
