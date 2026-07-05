# Amendment (019): Agent Tool Surface — Listing Link Integrity

Amends `specs/017-discogs-collection-agent/contracts/agent-tools.md`
(already amended once by
`specs/018-title-locate-postmortem/contracts/amendment-017-agent-tools.md`,
deltas 1–5). This amendment records deltas 6–8. On conflict, this amendment
prevails for the sections it touches; everything not named here is
unchanged.

Trigger: during the 018 replays the LLM fabricated
`discogs.com/release/<instance_id>` links — `instance_id` is a
collection-instance id, not a release id — violating the §5 "never invent
links" obligation. Documented same-day as the 019 candidate in `CLAUDE.md`.

## Delta 6 — §1 read tools: listing entries carry `release_url` (FR-001/002)

Every per-record entry in a listing-shaped read-tool result MUST include a
`release_url` field: the record's Discogs release-page URL, built by the
tool as `{settings.discogs_web_base_url}/release/{release_id}` (settings
alias `DISCOGS_WEB_BASE_URL`, default `https://www.discogs.com`). This
applies to:

- `filter_records` → `matches[]` **and** `fallback_matches[]` (the 018
  delta-4 fallback listing is a listing);
- `top_n` → ranking entries, all bases;
- `media_links` → `per_record[]` (alongside — never replacing — the
  verbatim `links[]` and the explicit `none` flag, which are unchanged;
  the payload note MUST distinguish the release **page** from playable
  media).

Normative properties:

- The URL embeds `release_id` (sync instance pass — present in every
  snapshot state and every existing snapshot; no re-sync required).
  `instance_id` MUST NOT appear inside any URL a tool emits.
- All copies (instances) of the same release share one `release_url`;
  `instance_id` remains the per-copy opaque reference and is unchanged in
  key, type, and follow-up semantics (moves, "their links", ordinals,
  session last-listing).
- Tool code holds no URL literals: the shape lives in one shared helper
  (`tools/common.py::release_page_url`) fed by settings (Constitution
  VII(a)).

## Delta 7 — §5 system prompt obligations: link sourcing (FR-004)

§5 gains a normative obligation. The system prompt MUST state, as part of
its ground rules:

- a record's Discogs page link comes **only** from a tool result's
  `release_url` field;
- music/video links come **only** from `media_links` output;
- constructing or completing a URL from `instance_id` or any other
  identifier is forbidden — including for records the collection does not
  contain (absence is reported without a fabricated link).

## Delta 8 — §1 `media_links` row: returns note

The §1 table row for `media_links` gains: "Each `per_record` entry also
carries `release_url` (delta 6); the verbatim-URI and explicit-`none`
semantics of FR-014/015/016 are unchanged."

## Verification

- Unit: fixture with `instance_id != release_id` asserts the id space of
  every emitted URL (matches, fallback_matches, rankings, per_record).
- Integration: prompt-render test asserts the delta-7 sentences; loop test
  asserts `release_url` presence on every listing entry.
- Replay (manual, quickstart): the 018 invented-URL prompts re-run; every
  `discogs.com` URL in assistant answers appears verbatim in that run's
  tool results (spec SC-001).
