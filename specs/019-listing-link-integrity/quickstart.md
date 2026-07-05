# Quickstart: Listing Link Integrity

**Feature**: 019-listing-link-integrity

## Prerequisites

- `cd collection-agent && uv sync` (or the venv you already use for 017/018)
- A synced snapshot at `collection-agent/data/snapshot.json` (for the live
  replay only; tests never touch the network)

## Run the tests (no live API calls)

```bash
cd collection-agent
pytest                                  # full suite — all pre-existing tests must stay green
pytest tests/unit/test_filters.py    -k release_url   # matches + fallback_matches carry the link
pytest tests/unit/test_analytics.py  -k release_url   # top_n entries carry the link
pytest tests/unit/test_media.py      -k release_url   # per_record carries it; links[]/none unchanged
```

The id-space test is the load-bearing one: its fixture record has
`instance_id != release_id` and asserts every emitted URL embeds
`release_id` and never `instance_id`.

## Verify the prompt surface

```bash
cd collection-agent
grep -n "release_url" src/collection_agent/prompts/system.md
```

Expected: ground rule 1 names `release_url` as the only source for a
record's Discogs page link and forbids constructing URLs from any
identifier.

## Replay the incident (live snapshot, chat)

```bash
cd collection-agent
python -m collection_agent chat
```

Ask, in order (the 018 replay prompts that produced invented URLs, plus the
direct link asks):

1. `can you locate Guido Schneider - Focus On 2xLP?` then
   `give me the Discogs link for it`
   → the answer's URL must be the tool-provided `release_url`
   (`https://www.discogs.com/release/<release_id>`), not an
   `instance_id`-shaped guess.
2. `my house records from the 90s` then `links for those`
   → any Discogs URL shown must appear verbatim in the tool output of this
   session; `media_links` URIs stay verbatim; records with no media get the
   explicit "no linked media" statement, with the release page offered only
   as the record's page.
3. `top 5 rated` then `and the link for the second one?`
   → ordinal follow-up resolves via the last listing and returns that
   record's `release_url`.
4. `do I have Autobahn by Kraftwerk?` (assuming absent)
   → absence reported per the 018 locate ladder, with **no** link
   fabricated for the absent record.

Success = zero `discogs.com` URLs in assistant answers that are absent from
the session's tool results (SC-001).

## Manual live spot check (SC-002)

Open one returned `release_url` in a browser and confirm it resolves to the
release page for that record (artist/title match). One-off manual check —
never automated (offline test suite norm).
