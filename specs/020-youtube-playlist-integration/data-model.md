# Data Model: YouTube Playlist Integration (020)

Re-scoped 2026-07-06: the feature is a **read tool**. No persisted
state, no session state, no pydantic write-plan models. The snapshot
schema is **unchanged** — the tool reads `CollectionRecord.videos`
(`MediaLink.uri`, verbatim) and `instance_id`/`release_id`/`title`/
`artists` for display. Payloads below follow the repo pattern for read
tools (plain dicts, like `media_links`).

## 1. `playlist_links` tool payload

```jsonc
{
  "links": [
    {
      "url": "https://www.youtube.com/watch_videos?video_ids=aaa,bbb,…",
      "index": 1,                  // 1-based, listing order
      "video_count": 50,
      "records": [                 // records covered by THIS link, in order
        {"instance_id": 123, "display": "Artist – Title", "video_count": 7}
      ],
      "label": "link 1 — records 1–7 (50 videos)"
    }
  ],
  "link_count": 2,
  "total_videos": 98,
  "covered_record_count": 13,
  "skipped_records": [
    {"instance_id": 456, "display": "Artist – Title",
     "reason": "no_videos"}       // or "unresolvable_uri"
  ],
  "duplicate_notes": ["video X appears under records A and B — included once (record A)"],
  "videos_per_record": "all",      // echo of the effective mode
  "suggested_name": "discogs-minimal",   // user's requested name, echoed
  "save_hint": "Playing the link opens a temporary playlist; use YouTube's 'Save playlist' to keep it in the library and name it.",
  "detail": "Links are click-to-play; nothing was created or saved in any account."
  // + standard with_warnings() envelope (stale/partial snapshot etc.)
}
```

Invariants (unit-tested):

- **Completeness partition (FR-007/SC-003)**: every resolved record
  appears in exactly one of `links[].records` ∪ `skipped_records`.
- **Chunk discipline (FR-005)**: `video_count ≤
  settings.youtube_playlist_max_ids` per link; links are disjoint and
  jointly cover every usable video; chunk boundaries are
  record-aligned (a record's videos split across links only if that
  record alone exceeds the cap, with a `duplicate_notes`-style note).
- **Dedup (FR-004)**: a `video_id` appears at most once across all
  links of one payload; first (listing-order) occurrence wins.
- **Link integrity (FR-002/010, SC-002)**: every id in every `url`
  came from `video_id_from_uri()` over a stored `MediaLink.uri` of a
  resolved record; `url` is built only from
  `settings.youtube_web_base_url` + the fixed `watch_videos` path.
- **Empty result (spec edge case)**: all records skipped ⇒ `links: []`,
  `link_count: 0`, and an explanatory `detail` — never a link with
  zero ids.

Error payloads (repo pattern): `no_records_resolved` (with
`not_found`), plus the standard blocked-snapshot envelope from
`load_for_serving`.

## 2. `video_id_from_uri` (pure function)

`src/collection_agent/youtube_links.py`

| Input shape | Result |
|---|---|
| `…youtube.com/watch?v=<id>[&…]` | `<id>` |
| `…youtu.be/<id>[?…]` | `<id>` |
| `…youtube.com/shorts/<id>` · `…/embed/<id>` | `<id>` |
| anything else / no 11-char id | `None` → skip reason `unresolvable_uri` |

Also here: `build_watch_videos_url(video_ids, base_url) -> str` — the
single place the play-link URL shape exists (mirrors 019's
`release_page_url` helper discipline).

## 3. Settings (amended — Constitution VII(a))

| Field | Env alias | Default |
|---|---|---|
| `youtube_web_base_url` | `YOUTUBE_WEB_BASE_URL` | `https://www.youtube.com` |
| `youtube_playlist_max_ids` | `YOUTUBE_PLAYLIST_MAX_IDS` | `50` |

No credentials, no token paths, no quota fields (re-scope removed
them). No `.gitignore` changes needed — nothing new is written to disk.

## 4. Explicitly unchanged

- `AgentSession` — no new fields; `playlist_links` consumes
  `last_listing_instance_ids` via the existing `_resolve` semantics and
  does not modify it.
- `models.py` — no new entities; `WritePlan`/`PlanState` untouched.
- CLI — no new commands, no new confirmation gate (read-only tool).
- Snapshot schema & sync — untouched; every existing snapshot works.
