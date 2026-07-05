# Research: Listing Link Integrity (019)

No NEEDS CLARIFICATION markers existed in the Technical Context. The
decisions below resolve the design choices the spec left open ("carry a real
URL and/or make the id non-linkable-looking").

## R1 — Real tool-provided URL, not id obfuscation

**Decision**: Add a genuine `release_url` field to every per-record listing
entry. Keep `instance_id` in the payload exactly as it is today (bare int,
same key).

**Rationale**: The 018 postmortem's core lesson (013→014 precedent) is that
prompt-level prohibition fails at the decision point when the deterministic
layer doesn't offer the needed artifact. The LLM invented URLs because the
user asked for a link and the only id-shaped material in reach was
`instance_id`. Supplying the real URL removes the motive; the extended
ground rule (R4) removes the license. Obfuscating or renaming the id
(e.g. `"inst-12345"`, `ref` key) would:
- break `media_links` ref resolution (`ref.isdigit()` path in
  `tools/media.py::_resolve`) and every LLM habit of passing ids back;
- churn the organize/propose_moves reference surface for zero user value —
  spec FR-003/SC-004 require that surface unchanged;
- still not give the LLM a link to answer with, leaving the original
  pressure intact.
FR-003's "does not read as URL material" is satisfied by the combination of
an adjacent explicit `release_url` field plus the ground-rule prohibition:
the id is never the best-looking link material again. The replay gate
(FR-006/SC-001) is the acceptance check for this judgment.

**Alternatives considered**: string-prefixing instance ids (breaks
resolution, above); dropping `instance_id` from display payloads entirely
(breaks ordinal/move follow-ups); a separate `get_release_url` tool (an
extra round-trip and a new decision point at exactly the moment the LLM is
tempted to improvise — the field must be *already present* in the listing).

## R2 — URL shape and configuration source

**Decision**: `{discogs_web_base_url}/release/{release_id}` with a new
settings field `discogs_web_base_url: str`, alias `DISCOGS_WEB_BASE_URL`,
default `"https://www.discogs.com"`.

**Rationale**: `CollectionRecord.release_id` is captured in the sync
**instance pass** (models.py — not enrichment), so the URL is derivable for
every record in every snapshot state, including snapshots synced before this
feature — no schema migration, no re-sync, no extra API calls (spec FR-002).
The canonical release-page path `/release/{release_id}` is already used by
the offline matcher (`collection_matcher/export_batch.py`), which is the
in-repo precedent for the shape. The web base differs from the existing API
base (`DISCOGS_BASE_URL` → `https://api.discogs.com`), and Constitution
VII(a) forbids hardcoding path/URL literals in tool code — hence a distinct
settings field.

**Alternatives considered**: reusing Discogs' `resource_url`/`uri` API
fields (not persisted in the snapshot; would require re-sync and a
snapshot-schema change — violates FR-002); hardcoding the base in
`tools/common.py` (VII(a) violation); importing the matcher's helper
(cross-package import forbidden by Constitution VI — the two packages stay
import-free of each other; the matcher keeps its own line).

## R3 — One shared helper, per-tool field addition

**Decision**: Add `release_page_url(settings, record) -> str` to
`tools/common.py`. Each listing producer adds `"release_url"` to its own
display dict: `browse._display` (covers `matches` AND `fallback_matches` —
both call `_display`), `analytics._display` (all `top_n` bases), and
`media.py`'s `per_record` entries.

**Rationale**: `tools/common.py` is already the shared serving layer
(`load_for_serving`, `with_warnings`) every read tool imports. One helper
keeps the URL shape in a single place; the display dicts stay tool-local
because their shapes legitimately differ (browse has `folder`/`format`;
analytics doesn't; media has `links`). Merging the `_display` functions was
rejected as unrelated churn.

**Alternatives considered**: computing the URL on `CollectionRecord` as a
property (models.py has no settings access — VII(a) would be violated by a
baked-in base, and threading settings into the model is disproportionate);
post-processing payloads in the agent loop (hides the field from the tools'
own docstrings/contract and misses tool-specific notes).

## R4 — Prompt change: extend ground rule 1, note in media tool

**Decision**: Extend ground rule 1 in `prompts/system.md` with explicit
link-sourcing sentences: a record's Discogs page link comes **only** from
the listing payload's `release_url`; music/video links come **only** from
`media_links`; constructing a URL from `instance_id` or any other
identifier is forbidden. Update `media_links`' payload `note` so the
release page is not presented as playable media (spec FR-005/US3).

**Rationale**: The invented-URL behavior is a link-sourcing failure, i.e.
exactly ground rule 1's territory — strengthening the existing rule keeps
one authoritative statement instead of a competing section (the 018 FR-009
lesson: the note the LLM reads at the decision point must agree with the
standing rule). This is procedural prose, not attribute/schema prose, so
the VII(b) analog holds; the registry-rendered `{attribute_block}` is
untouched.

**Alternatives considered**: a new "Links" prompt section (splits authority
with ground rule 1); relying on the payload field alone with no prompt
change (the model would still occasionally "helpfully" construct URLs for
records it hasn't listed — the rule covers the not-in-collection edge
case).

## R5 — Verification strategy: id-space tests + 018 replay

**Decision**: Three layers, no live network in CI:
1. **Unit**: fixture records with `instance_id != release_id`; assert each
   listing entry's `release_url` embeds `release_id` and NOT `instance_id`
   (browse matches, browse fallback_matches, top_n, media per_record); the
   URL equals the settings-derived shape.
2. **Integration**: prompt-render test asserts the ground-rule sentences;
   loop-level test asserts every listing-producing tool result carries
   `release_url` on each entry.
3. **Replay (quickstart, manual)**: re-run the 018 incident prompts that
   produced invented URLs and grep the transcript for `discogs.com` URLs
   absent from tool output (SC-001); one manual click-through of a returned
   link on the live site (SC-002 spot check — assumptions note in spec).

**Rationale**: The wrong-id-space bug is deterministic and unit-testable;
the behavioral claim ("the LLM stops inventing") is only observable in
replay, matching how 018 validated each ladder rung. Live-resolution checks
stay manual to keep the suite offline (017 norm: no live API calls in
tests).

**Alternatives considered**: automated LLM-in-the-loop link assertions in
CI (nondeterministic, needs API key — rejected per 017/018 test norms).
