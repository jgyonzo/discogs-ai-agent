# Amendment (020): Agent Tool Surface — YouTube Play Links

Amends `specs/017-discogs-collection-agent/contracts/agent-tools.md`.
Third amendment to that contract (018 → deltas 1–5 against §3; 019 →
deltas 6–8 against §1/§5). This amendment: **deltas 9–11** against §1
and §5 (delta 11 added 2026-07-06 from replay finding 6). The
play-link surface itself is specified in this feature's
`contracts/youtube-playlists.md`.

Re-scope note (2026-07-06): an earlier draft of this amendment
(deltas 9–12) covered an OAuth account-write path — superseded by the
owner's re-scope to anonymous play links; the write path §4 is now
**untouched** by this feature.

## Delta 9 — §1 read tools: `playlist_links` added (FR-001/005/007)

The read-tool table gains one row:

| Tool | Args | Returns |
|---|---|---|
| `playlist_links` | `record_refs`, `use_last_listing`, `videos_per_record ("all"\|"first")`, `suggested_name` | click-to-play YouTube link(s) over the resolved records' stored videos: per-link labels (records covered, video count), chunked at the configured cap (default 50 ids/link, record-aligned, no silent truncation), in-payload dedup notes, `skipped_records` with reasons (`no_videos`/`unresolvable_uri`), `suggested_name` + `save_hint` (saving/naming happens on the YouTube site), standard warnings envelope |

Normative: video ids come only from deterministic parsing of stored
`MediaLink.uri` values; the URL shape exists only in
`youtube_links.py::build_watch_videos_url` with a settings-sourced
base. Resolution semantics identical to `media_links` (§1) — refs,
name mentions, last listing. The tool is read-only: it performs no
network calls and no writes, and it does **not** participate in the §4
write path (no plan, no confirmation prompt).

## Delta 10 — §5 system prompt obligations: play links, honest saving (FR-008/010)

- The 019 link-sourcing rule (ground rule 1 family) extends: a play
  link is presented **only** from the `playlist_links` payload. The
  LLM never assembles a YouTube URL from video ids, playlist ids, or
  any other identifier. Per-video links continue to come only from
  `media_links` output (unchanged).
- Ground rule 6's unsupported-capability list is rephrased: playlist
  *requests* are now supported via play links, while **saving/naming/
  editing playlists in the owner's account** and **YouTube
  search/discovery** are named as unsupported. When asked to save or
  name a playlist, the agent MUST relay the save-on-site guidance
  (payload `save_hint` + `suggested_name`) and MUST NOT claim a
  playlist was created, saved, or named in any account.
- Records without usable stored videos are reported as skipped; the
  agent never offers to find a substitute video (v2 search stays
  deferred).

## Delta 11 — §1 read tools: lean `filter_records` listing entries (replay finding 6)

Added 2026-07-06 after the third live replay: prompt-level column
guidance lost to the payload shape (`gpt-4o-mini` rendered whatever
fields the entries carried), so the entry shape itself changes — the
013→014 enforcement-over-steering precedent applied to listings.

- Default listing entry (matches **and** `fallback_matches`):
  `instance_id`, `artist`, `title`, `year`, `country`, `release_url` —
  nothing else. `format` and `folder` are no longer default fields
  (supersedes the entry shape shown in 019's delta 6; `release_url`
  semantics unchanged).
- New `include` arg on `filter_records`: extra registry attributes
  (aliases accepted) added per entry when the user asks to see them.
  Unknown names land in `unsupported_criteria` with reason "unknown
  attribute (include)" — never silently dropped (FR-013a family).
  `folder` renders as the folder *name*, never the raw id.
- Auto-include: a criterion whose op is not `eq`/`missing` adds its
  attribute to the entries (values vary → informative); `eq` criteria
  do not (a column repeating one value is noise).
- `title` is display-capped at `settings.listing_title_max_chars`
  (default 70, env `LISTING_TITLE_MAX_CHARS`) with a trailing ellipsis
  — matching/locating is unaffected (it runs on snapshot data, not the
  displayed string).

## Explicitly not amended

- §4 write path — unchanged (this feature adds no writes).
- §6 CLI surface — unchanged (no new commands or gates).
- §3 attribute registry — unchanged (no new attributes).

## Verification

- Unit: tool-surface test asserts `playlist_links` is registered as a
  read tool and that no `execute_*`/plan machinery exists for it;
  prompt tests assert the ground-rule 1/6 clauses (with
  `{attribute_block}` still the only schema prose — VII(b) analog).
- Live (quickstart): SC-001/SC-002 replays from
  `youtube-playlists.md` §4.
