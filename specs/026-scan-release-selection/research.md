# Research: Scan Release & Master Selection (026)

All Technical Context unknowns resolved. Each decision below records what
was chosen, why, and what was rejected.

## R1 — Fetching a master's other pressings

**Decision**: New read-only `DiscogsClient.get_master_versions(master_id,
per_page)` → `GET /masters/{master_id}/versions?page=1&per_page=N`, through
the existing governed `_get_json`/`_request` path (rate-limit headers
honored like every other call). Exactly one page, one request per tap.
Documented as the FOURTH amendment to 017's discogs-consumption contract
(`amendment-017-discogs-consumption-4.md`) — a new READ, zero new writes.

**Rationale**: The endpoint is already documented in
`docs/discogs_api_reference.md` §7.6 with the exact per-item field list.
One capped page keeps the tap within the 60 req/min budget and bounded in
memory; pagination beyond page 1 is not needed for the feature's purpose
(pick the right pressing, honestly say when more exist).

**Alternatives considered**: paginating all versions (rejected: popular
masters have 100+ versions ⇒ several requests per tap for marginal pick
value); reusing `/database/search?master_id=...` (rejected: not a
documented search filter for this purpose and returns search-shaped noise;
the versions endpoint is the purpose-built, richer source).

## R2 — Master identity without extra requests

**Decision**: The default results view displays the master as a labeled
element on the selected release — the work's identity is conveyed by the
candidate's own verbatim `title` (Discogs search titles are
"Artist - Title", which names the work) plus an explicit master page link
built from `master_id`. **No `GET /masters/{id}` call is made, ever, in
this feature.**

**Rationale**: SC-006 and the Technical Context require the default view to
add zero Discogs requests. Search results carry `master_id` (024) but not a
separate master title; the candidate's title already names the work, and
the master *page* (one tap away) is the authoritative rendering. Fetching
master metadata would add a request + latency to every multi-candidate scan
for a label the owner can see anyway.

**Alternatives considered**: auto `get_master` on scan (rejected: violates
the zero-extra-request constraint, burns rate budget on every scan);
fetching master title lazily when rendering (rejected: same request for
strictly less value than the link itself provides).

## R3 — Discogs page links: server-built wire fields (019 discipline)

**Decision**: `Candidate` gains two additive fields, built server-side from
the EXISTING `DISCOGS_WEB_BASE_URL` settings field and genuine ids:
`release_page_url` (= `{base}/release/{release_id}`; always populated —
`release_id` is required) and `master_page_url` (= `{base}/master/{master_id}`
iff `master_id` is present, else `None`). The URL shapes live in exactly one
code site per id space: `tools/common.py` — the existing
`release_page_url` helper is refactored to an id-based core (its
record-based signature preserved for 019 callers) and a new
`master_page_url(settings, master_id)` sits beside it. `scan/search.py`
enriches candidates at build time (settings are already in scope in
`_run_search`). The static page renders ONLY these server-built URLs — it
never constructs a URL from any identifier.

**Rationale**: This is exactly 019's listing-link-integrity discipline
(tool-built links from the right id space, `DISCOGS_WEB_BASE_URL`
settings-sourced per VII(a)) and 020's single-URL-shape-site grep
enforcement. Building at candidate-construction time (not per-endpoint)
means the scan page, manual search, and the new versions endpoint inherit
identical links from one site. The fields are additive with `None`/derived
defaults, so eval and all existing readers are unaffected (eval persists
evidence, not candidates).

**Alternatives considered**: hardcoding `https://www.discogs.com` in the
page JS (rejected: VII(a) violation, breaks the settings override, and
splits the URL shape across languages); client-side construction from
`release_id`/`master_id` shipped as numbers (rejected: re-introduces the
fabricated-link risk class 019 closed — the page should render links, not
mint them); a per-response links map (rejected: more shape for no gain).

## R4 — Master-versions item → Candidate mapping (verbatim)

**Decision**: Each `versions[]` item maps to the existing `Candidate` model
with the same verbatim discipline as `_candidate_from_result`:
`release_id=id`, `title=title` (verbatim — versions titles typically omit
the artist; never re-composed), `year=str(released)` if present,
`country=country`, `formats=[format]` (the payload's single descriptive
string carried whole as a one-element list — joined for display exactly as
today, never parsed), `labels=[label]` if present, `catno=catno`,
`thumb_url=thumb`, `discogs_uri=None` (not in the payload; the page link is
`release_page_url`), `master_id=` the requested master id (known genuine
context), `duplicate=` the same fresh `snapshot_duplicate_checker` overlay
as scan results. Versions already displayed in the cycle (by `release_id`,
including the selected release itself — the versions list contains it) are
dropped before display.

**Rationale**: 019/022's verbatim rule: every display field comes from the
payload; the only transformations are the same tolerated ones search
already uses (`str()` on a numeric year, list-wrapping). Splitting the
`format` string would be parsing/invention; wrapping it whole renders
byte-identically in the UI (cards join formats with ", "). Deduping against
the cycle's own candidates is what makes the list honestly "**other**
pressings" (FR-012's "no additional versions" case falls out naturally).

**Alternatives considered**: mapping `major_formats[]` into `formats`
(rejected: loses the descriptive detail — "LP, Album, Reissue" vs "Vinyl");
a new `VersionCandidate` model (rejected: the whole point is that versions
flow through the SAME candidate pipeline — duplicate overlay, allowlist,
add gate, rendering — a second model would fork all four).

## R5 — Endpoint, gate, and session-allowlist integration

**Decision**: `GET /api/master-versions?scan_id=...&master_id=...`
(sync-def handler → threadpool, like every other scan handler). Server-side
gates, in order:

1. `scan_id` must be an open, known cycle (not closed, not superseded);
   otherwise 409 `superseded` — the page's results are stale.
2. `master_id` must be the `master_id` of a candidate REGISTERED in that
   cycle (`_CycleContext` gains the set of its candidates' master ids);
   otherwise 403 `unknown_master` — a master the server never displayed can
   never drive a fetch (same shape as 022's `unknown_candidate` add gate:
   client input can only select among server-offered values).
3. The generation is captured at entry and re-checked after the fetch —
   a newer scan supersedes the in-flight fetch (409, no state effects) —
   but the fetch itself does NOT bump the generation: it extends the
   current cycle rather than starting a new one, so it must not auto-close
   the cycle it belongs to.

On success: fetched versions are mapped (R4), deduped, then registered into
the SAME session allowlist and cycle title map as scan candidates —
`/api/add` and the journal work on them with ZERO changes (FR-004/011: same
write gate, same duplicate confirmation, same `added` journal line with the
cycle's source). Discogs failure → 502 `discogs_unavailable`; the page
keeps its current results (FR-012).

**Rationale**: Reuses 022's proven gate architecture instead of inventing a
parallel one. Not bumping the generation is the key subtlety: `_begin_cycle`
exists to supersede PREVIOUS work; a versions fetch is a continuation of
the CURRENT cycle. Registering into the existing allowlist is what makes
"same confirmation flow" literally true rather than re-implemented.

**Alternatives considered**: POST instead of GET (rejected: read-only fetch
with two query params; GET matches `/api/search`); accepting any master_id
(rejected: violates the offered-values-only discipline and would let a
mistyped id fetch arbitrary lists); bumping the generation (rejected: would
auto-close the very cycle the user is refining, journaling a spurious
`skipped`); a separate versions allowlist (rejected: forks the write gate).

## R6 — Cap and truncation honesty

**Decision**: ONE new `Settings` field: `scan_versions_max`
(`COLLECTION_AGENT_SCAN_VERSIONS_MAX`, default **25**) — the `per_page` of
the single versions request and thus the display cap. The response carries
`total_versions` verbatim from `pagination.items`; the page states
"showing N of T versions" whenever T exceeds what's displayed (FR-013 —
never silent truncation, same honesty rule as 022's `more_matches` and
020's no-silent-truncation chunking).

**Rationale**: VII(a) — the cap is runtime configuration, so it is a
settings field, not a literal. 25 is a browsable phone-screen list that
covers the long tail of real masters in one request; `scan_candidates_max`
(8) is deliberately NOT reused — that cap tunes identification precision,
this one tunes a browse list; coupling them would make one knob fight two
jobs.

**Alternatives considered**: reusing `scan_candidates_max` (rejected
above); no cap / fetch-all pagination (rejected in R1); a "load more"
pagination UI (rejected: out of scope for v1 — the honest count plus the
master page link covers the >25 case).

## R7 — Journal impact: none

**Decision**: NO journal schema change and no new outcome kinds. The
versions fetch itself is not journaled — the journal records cycle
OUTCOMES (added/skipped/no_match/failed), and a fetch is a read, exactly
like the initial Discogs search which is also not separately journaled.
Adds that pick a versions-sourced candidate journal a standard `added`
line: the cycle's own `source` (photo/manual_search), `evidence_kinds` as
tried, `release_id`/`release_title` from the registered title map.

**Rationale**: `contracts/scan-journal-schema.md` stays untouched — the
audit trail's meaning ("what was decided about this scan cycle") is
unchanged by where in the list the picked candidate came from; the
release_id/title recorded are the truth either way. Avoids a contract
amendment with no audit value.

**Alternatives considered**: a new `versions_fetched` journal line
(rejected: journal is an outcome audit, not a request log; 021's LangSmith
tracing and the server log already cover diagnostics); a new `source` enum
value for versions-adds (rejected: the scan's source honestly remains the
photo/manual search that started the cycle; the enum is contracted).

## R8 — Page interaction design (selected / alternatives / links / on-demand)

**Decision**: The static page (vanilla JS, still fully self-contained)
renders, per non-empty result:

- **Selected match**: `candidates[0]` — the ladder/re-rank already puts the
  best match first (022 ladder order, 024 exact-catno partition), so
  "selected" is a pure presentation designation with NO ranking change. Its
  card is visually prominent and carries: a "View release on Discogs ↗"
  anchor (`release_page_url`), a master row shown only when
  `master_page_url` exists — "Master page ↗" anchor + a
  "Show other pressings" button — and the usual add button.
- **Alternatives**: `candidates[1..]` under an "Other possibilities"
  heading, same cards as today plus their own Discogs anchor each.
- **Links vs actions (FR-009)**: outbound links are real `<a>` elements
  with `target="_blank"` and `rel="noopener noreferrer"`, visually distinct
  (link styling + ↗) and structurally separate from the add `<button>`s;
  no card-level click handler adds anything. New-tab navigation leaves the
  page's in-memory state untouched, and all cycle state lives server-side
  (session/cycles), so backgrounding the page on the phone loses nothing
  (FR-008/SC-003).
- **On-demand pressings**: the button disables while fetching, then
  appends an "Other pressings of this master" section rendered by the SAME
  card renderer (dup badges, links, add buttons identical); empty result →
  honest inline "No other pressings found on Discogs."; 502 → honest
  failure line, existing results untouched; 409 → the standard superseded
  handling. A new scan/search resets the section with everything else
  (existing `renderCandidates` reset + FR-022/023 supersede semantics,
  unchanged).
- Zero-candidate and manual-search flows keep their existing behavior;
  manual-search results get the identical selected/alternatives rendering
  (FR-014 — same renderer, same response shape).

**Rationale**: `candidates[0]`-as-selected keeps the eval-measured pipeline
byte-identical while giving the owner the designation the spec asks for.
Anchors (not JS `window.open`) are the platform-native "new tab" that
mobile browsers handle correctly. Reusing one card renderer is what makes
FR-011 ("same detail, same rules") structurally true.

**Alternatives considered**: a server-side `selected` field on
`ScanResponse` (rejected: it would duplicate what position 0 already means;
the contract instead DOCUMENTS position-0 semantics — see the scan-api
amendment); JS-opened windows (rejected: popup-blocker-prone, worse than
anchors); collapsing alternatives behind a toggle (rejected: hides the
comparison the feature exists to enable).

## R9 — Eval comparability (023/024/025) preserved by construction

**Decision**: No changes to `scan/vision.py`, the ladder walk, evidence
normalization, or anything under `eval/`. The only shared-code changes the
eval pipeline can even see are the two additive link fields on `Candidate`
(defaults; not persisted — eval results store evidence and outcome fields,
not candidate dumps) and the settings pass-through into
`_candidate_from_result`. Candidate ordering, rung semantics, caps, and
per_page depths are byte-identical for every existing call path.

**Rationale**: 025 established that ladder changes must be measured by
evidence replay; this feature deliberately makes none, so no eval run is
required to merge and prior baselines stay comparable. The 023 AST
read-only guard is untouched (no `eval/` edits). A defensive unit test pins
that `find_candidates`' returned ordering and fields (minus the new link
fields) are unchanged for a fixed fake payload.

**Alternatives considered**: threading the new fields into eval results for
diagnostics (rejected: links are derivable from ids already recorded;
results.jsonl stays 024/025-shaped).
