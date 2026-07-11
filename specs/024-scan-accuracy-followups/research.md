# Research: Scan Accuracy Follow-ups (024)

Grounded in the merged 023 code and the 2026-07-07 spot-check evidence
(spec Context). All decisions offline-verifiable except R2's Discogs-field
claim, which was verified live during the spot-check itself.

## R1 — Re-rank raw results, not built Candidates

**Decision**: In `scan/search.py::_run_search`, the catno rung fetches
`per_page = max(scan_candidates_max, scan_catno_search_depth)` and
stable-partitions the RAW result dicts (exact-catno matches first, source
order preserved within each group) BEFORE deduplication, Candidate
construction, and the existing cap. Other rungs pass through unchanged
(`per_page = scan_candidates_max`, no partition).

**Rationale**: Partitioning raw dicts means the duplicate checker and
Candidate construction run only for the ≤cap survivors (same work as today),
and the verbatim rule is trivially preserved — ordering is the only thing
that changes. Python's `sorted(key=...)` is stable, giving FR-002's
group-internal order for free.

**Alternatives considered**: building all ~50 Candidates then re-ranking —
rejected (needless duplicate-checker work, larger blast radius); asking
Discogs for exact matching — no such API parameter exists.

## R2 — `master_id` comes free in both places

**Decision**: Truth master ids come from the release payload the builder
ALREADY fetches (`GET /releases/{id}` → `master_id`); candidate master ids
come from the search results (`/database/search` items carry `master_id`) —
verified live during the 2026-07-07 spot-check (e.g. truth 1948 →
master 5309; its candidate carried the same). Zero additional requests in
either path. A `master_id` of `0`/absent is treated as "no master".

**Rationale**: The whole metric costs nothing at build/eval time; the only
gap is datasets built before 024 — closed by R4's backfill.

## R3 — Catno normalization mirrors 022's FR-019 precedent

**Decision**: `normalize_catno(s)` = remove spaces, hyphens, dots, slashes,
underscores; casefold. Exactness: any of the candidate's catno values
(the search payload's `catno` string, additionally split on commas — Discogs
comma-joins multi-catno results) normalizes equal to the normalized searched
catno (which comes from the evidence value the rung searched with).

**Rationale**: Same character-class discipline that fixed the barcode-in-
catno confusion in 022; covers every observed case (`SUB 15`≡`SUB15`≡
`sub-15`, while `SUB 150` stays distinct because the digit tail differs).
Leading-zero/label-alias equivalences deliberately excluded (spec
Assumptions) — no observed case needs them and they risk false exactness.

## R4 — Backfill appends superseding lines; readers take newest-per-release

**Decision**: `eval-dataset --backfill-masters` iterates done manifest
releases lacking `master_id`, calls `get_release` (governor-paced, no image
downloads), and appends a COPY of the release's newest manifest line with
`master_id` set (images list carried over verbatim). Fetch failures are
counted and skipped (old line stays authoritative). Manifest reading gains
one rule used by both `dataset.py` (resume) and `sources.py` (items):
**newest line per release_id wins**. Append-only property of the manifest is
preserved — nothing is rewritten in place.

**Rationale**: In-place manifest rewriting would break the append-only/
torn-line guarantees 023 established. Newest-line-wins also cleans up the
pre-existing duplicate-line semantics from failed→retried releases (023
iterated all lines; harmless then, but now formalized). `done_release_ids`
semantics are unchanged in effect: a release's newest line is `downloaded`/
`no_images` exactly when 023's any-line rule said done.

## R5 — Evidence passthrough reuses `compact_dump()` byte-for-byte

**Decision**: `EvalResult.evidence: dict | None`, populated in
`harness.evaluate_item` with `evidence.compact_dump()` right after
extraction — the same method the scan journal uses (022 FR-021), so the
results file and the journal speak one evidence dialect. `no_evidence`
records carry the empty dump result (omitted via exclude_none/empty rules);
`unlabeled` and pre-vision `error` records carry none.

**Rationale**: One evidence shape across journal and results means the same
debugging skills/tools apply to both; zero new serialization logic.

## R6 — Miss classification lives in scoring (pure), truth master travels on EvalItem

**Decision**: `EvalItem` gains `truth_master_id: int | None` (from the
manifest via `sources.py`; always `None` for the retained source).
`scoring.score_search_outcome` gains the candidates' master ids and returns
`miss_master_relation` for misses: `same_master` (truth master known ∧ any
candidate master equals it), `different` (truth master known ∧ candidates
carried ≥1 master id ∧ none equal), `unknown` (truth master unknown ∨ no
candidate master ids to compare — includes the zero-candidate case).
Summary adds `misses_same_master`, `misses_different`, `misses_master_unknown`
and `practical_rate = (hits + misses_same_master) / strict denominator`.
New normative invariants: (8) the three miss buckets sum to `misses`;
(9) `practical_rate ≥ identification_rate` when both non-null, equal iff
`misses_same_master == 0`; (10) `evidence` present on every record where a
vision call was made.

**Rationale**: Keeps all classification in the pure, unit-testable module;
the harness only threads data. The `unknown` bucket honors the spec's
never-guess rule for old manifests and the retained source.

## R7 — Test strategy

**Decision**: `discogs_payloads.search_result` gains a `master_id` kwarg
(absent by default — exercising verbatim-absent). Re-rank tests replay the
measured drowning case: exact `SUB 15` at source position ~20 among
`SUB 15x` neighbors, asserting position 1 post-rank, cap respected,
`more_matches` from true totals, and byte-identical behavior when no exact
match exists / on other rungs. Dataset tests cover master recording,
backfill supersession (newest-line-wins), and backfill-404 honesty. Harness
integration asserts evidence dumps in records and the practical rate
end-to-end. Existing tests change ONLY where they assert catno-rung
internals (per_page value), per spec SC-006.

**Rationale**: The eval that found the bugs becomes the regression suite
that pins the fixes (SC-001/SC-002's offline half).
