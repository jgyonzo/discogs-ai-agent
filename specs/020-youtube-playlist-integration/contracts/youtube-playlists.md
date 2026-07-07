# Contract: YouTube Play-Link Surface (020)

Re-scoped 2026-07-06: anonymous play links, not account writes. New
contract for this feature's surface; changes to 017's existing surface
are amended separately — see `amendment-017-agent-tools.md`
(deltas 9–10). Consumers: the collection-agent runtime only
(Constitution VI — no new dependencies, no other component touched).

## 1. External consumption: the `watch_videos` endpoint

- Shape: `{youtube_web_base_url}/watch_videos?video_ids=<id1,id2,…>`
  (base settings-sourced; path and param fixed in
  `youtube_links.py::build_watch_videos_url` — the only place this URL
  shape exists).
- Behavior relied upon: opening the URL yields a temporary playlist
  (`list=TLGG…`) playing the ids in order, saveable to the viewer's
  library via the site's "Save playlist" action. Verified live
  2026-07-06 (HTTP 303 with snapshot video ids).
- **No API key, no OAuth, no quota, no writes.** The agent never
  performs an HTTP request against YouTube at all — it only emits the
  URL; the browser does the rest.
- Normative status: **undocumented endpoint, accepted-risk
  dependency** (spec Assumptions). Its retirement breaks clicked links,
  not the agent; no fallback construction is attempted.
- Capacity: at most `settings.youtube_playlist_max_ids` (default 50)
  ids per URL. Exceeding payloads are chunked (§2), never truncated.

## 2. LLM tool surface (addition): `playlist_links` (read-only)

Args: `record_refs: list[str]` · `use_last_listing: bool` ·
`videos_per_record: "all" | "first" = "all"` ·
`suggested_name: str | None`.

Behavior (normative):

1. Record resolution reuses the `media_links`/`propose_moves`
   semantics exactly (instance ids, name mentions, last listing;
   unresolved refs reported as `not_found`; no listing in session and
   no refs ⇒ `no_records_resolved` error payload).
2. Video ids are parsed **deterministically** from stored
   `MediaLink.uri` values (`video_id_from_uri`). A record with no
   parseable video becomes a `skipped_records` entry (`no_videos` /
   `unresolvable_uri`). The LLM never supplies a video id; the tool
   never searches for one (FR-002/003).
3. Duplicate video ids across the request collapse to the first
   listing-order occurrence + a note (FR-004).
4. Chunking per §1 capacity: listing order preserved, record-aligned
   boundaries, per-link labels (records covered + video count), totals
   in the payload; links disjoint and jointly complete (FR-005).
5. Payload carries `suggested_name`, `save_hint`, and a `detail`
   stating nothing was created or saved (FR-008); standard
   `with_warnings` envelope applies (ground rule 2).
6. Completeness partition: resolved records = covered ∪ skipped
   (FR-007). All-skipped ⇒ `links: []`, explanatory detail, no empty
   URL.

The tool performs **no writes** anywhere — it is registered as a plain
read tool; the §4 write gate of the agent-tools contract does not
apply to it (and MUST NOT be imitated: no confirmation prompt).

## 3. System prompt obligations (delta detail in the amendment)

- Play links presented **only** from the `playlist_links` payload
  (ground rule 1 family — FR-010).
- Relay the save-on-site guidance; never claim a playlist was
  created/saved/named in any account (FR-008).
- Account-side playlist management and YouTube search remain in the
  unsupported list; playlist *requests* are answered with this tool.

## 4. Verification (maps to spec success criteria)

- SC-001: live two-prompt replay; click the link, verify play order
  and site-side save.
- SC-002: audit — every id in every emitted URL parses from a stored
  URI of a resolved record; answers contain no YouTube URLs absent
  from tool payloads.
- SC-003: unit-tested completeness/disjointness invariants
  (data-model §1), including multi-link chunking.
- SC-004: fresh-clone check — no Google/YouTube configuration exists
  to perform.
- All pytest coverage is offline (snapshot fixtures); **no live
  network calls in tests** (repo norm) — the live click-through is an
  owner-run quickstart step.
