# Feature Specification: Scan Accuracy Follow-ups (Eval-Driven)

**Feature Branch**: `024-scan-accuracy-followups`
**Created**: 2026-07-07
**Status**: Draft
**Input**: User description: "Scan accuracy follow-ups from 023's first measured eval (94-image run: 56.4% identification, and a 14-miss catno spot-check on 2026-07-07). Three items: (1) exact-catno re-rank on the catno rung (deeper fetch + deterministic exact-match-first ordering, candidate cap and field verbatim-ness unchanged); (2) eval result records carry the compact extracted-evidence values so zero-candidate misses are diagnosable from the results file alone; (3) same-master near-miss metric — builder records truth master ids (backfillable), candidates carry their verbatim master id, harness reports a practical rate alongside the unchanged strict rate; unknown masters degrade honestly. Out of scope: vision prompt changes, depth changes on non-catno rungs, replacing strict scoring as primary, retained-source master resolution via live lookups."

## Context

023 delivered the measurement loop and its first numbers: 56.4% per-image
identification / 76% per-release over a 94-image run. A live spot-check of the
14 catno-involved misses (2026-07-07, ~30 read-only lookups) produced three
evidence-backed findings, each mapping to one item here:

1. **Catalog-number drowning** (2–3 misses): Discogs' catno search
   substring-matches, so short catalog numbers lose to longer neighbors —
   truth `SUB 15` was pushed out of the top-8 by `SUB 150`/`SUB 152`; `FD 006`
   drowned under `SFDB 006`/`FDS-B006`. The exact match existed but never
   reached the owner. This is the only *pipeline* defect the eval surfaced.
2. **Undiagnosable zero-candidate misses** (4 misses): the eval results record
   evidence *kinds* but not the extracted *values*, so "catno search returned
   nothing" cannot be classified as vision-misread vs. absent-from-Discogs
   without replaying. 022's replay addendum 1 (FR-021) already taught this
   lesson for the scan journal; the harness must learn it too.
3. **Wrong-pressing near-misses** (≥4 of 14 spot-checked; e.g. a candidate
   with the *identical* catalog number, same album, different pressing):
   strict release-id scoring counts "right album on screen, wrong row" as a
   full miss, so the practical accuracy of the scan flow is understated. The
   strict rate stays the primary metric; a same-master "practical" rate must
   be reported beside it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Exact catalog-number matches surface first (Priority: P1)

As the owner scanning a record whose catalog number is a prefix of many other
catalog numbers (e.g. `SUB 15` among `SUB 150`–`SUB 159`), I want the release
whose catalog number matches *exactly* what was read to appear at the top of
the candidate list, so the correct pressing is on screen instead of being
pushed out by longer look-alikes.

**Why this priority**: The only real pipeline fix; converts measured misses
into hits for both the live scan page and the eval, and every catno-rung scan
benefits.

**Independent Test**: With a scripted search backend returning an exact-catno
match ranked below the candidate cap among longer substring matches, the
pipeline's candidate list shows the exact match first and still respects the
cap; a record with no exact match behaves exactly as today.

**Acceptance Scenarios**:

1. **Given** a catno search where the exact match ranks below the candidate
   cap (e.g. position 20 of 40), **When** the catno rung runs, **Then** the
   exact match appears first in the served candidates and the list is still
   capped at the configured maximum.
2. **Given** several candidates whose catalog numbers all exactly equal the
   searched value (same catno reused across pressings), **When** re-ranked,
   **Then** all exact matches precede all non-exact ones, each group keeping
   Discogs' relative order.
3. **Given** exact-match comparison, **When** catalog numbers differ only in
   separators or case (`SUB 15` vs `sub-15` vs `SUB15`), **Then** they compare
   as equal; `SUB 150` never compares equal to `SUB 15`.
4. **Given** a catno search with no exact match anywhere in the fetched
   results, **When** the rung completes, **Then** the candidate list is
   exactly what today's behavior produces (Discogs order, capped).
5. **Given** any rung other than catno (barcode, artist+title, free-text),
   **When** it runs, **Then** its fetch depth and ordering are byte-identical
   to 023-merged behavior.
6. **Given** the re-ranked list, **When** candidates are displayed or
   journaled, **Then** every candidate field is still verbatim from the
   search payload — only order and fetch depth changed (019 discipline).

---

### User Story 2 - Diagnose any eval miss from the results file alone (Priority: P2)

As the owner reading an eval run's results, I want each record to carry the
actual evidence values the vision step extracted (artist, title, label,
catno, barcode, tracks — the same compact shape the scan journal already
uses), so a zero-candidate miss tells me *what was searched* without
re-running anything or consulting external traces.

**Why this priority**: 4 of 14 spot-checked misses were unclassifiable
without this; it is pure observability with no behavior change.

**Independent Test**: Run the harness over a labeled image with a stubbed
vision reply; the result record contains the extracted values exactly as the
journal's compact form would, and an empty extraction yields an
empty/absent evidence field, never a fabricated one.

**Acceptance Scenarios**:

1. **Given** an evaluated image whose vision step extracted values, **When**
   its result record is written, **Then** the record carries the compact
   extracted-evidence values (no empty/None entries).
2. **Given** a vision step that returned empty evidence, **When** the record
   is written as `no_evidence`, **Then** the evidence field is absent or
   empty — never invented.
3. **Given** an unlabeled retained photo (skipped, zero billable calls),
   **When** its record is written, **Then** it carries no evidence field (no
   vision ran).
4. **Given** a results file from before this change, **When** it is read by
   any 024 tooling, **Then** the absent evidence field is tolerated.

---

### User Story 3 - Honest practical-accuracy metric (same-master near-misses) (Priority: P3)

As the owner interpreting eval numbers, I want each miss classified as
"same-album near-miss" (a candidate was another pressing of the true
release's master) versus "true miss", and the summary to report a practical
rate (hits + near-misses) alongside the unchanged strict rate — so I know how
often the scan flow actually put the right album on screen.

**Why this priority**: Scoring honesty (the spot-check suggests the practical
rate is meaningfully higher), but it changes no behavior and depends on
ground-truth master data existing.

**Independent Test**: With a dataset manifest carrying truth master ids and a
scripted search returning a same-master candidate, a miss is classified as a
near-miss and the summary reports both rates; with master unknown, the miss
is classified as "master unknown" and excluded from near-miss math — never
guessed.

**Acceptance Scenarios**:

1. **Given** a dataset build, **When** each release is fetched, **Then** its
   master id (when Discogs has one) is recorded in the manifest as part of
   ground truth — with zero additional network requests.
2. **Given** an already-built dataset without master ids, **When** the owner
   runs the builder's backfill mode, **Then** master ids are added for
   already-done releases (re-fetching only the release metadata, not images),
   and manifest readers treat the newest entry per release as authoritative.
3. **Given** a miss where a candidate's master equals the truth's master,
   **When** scored, **Then** the result records "same-master near-miss";
   summary reports strict rate (unchanged definition) AND practical rate
   (hits + near-misses over the same denominator).
4. **Given** a truth release with no master id (Discogs has none, old
   manifest line, or a retained-source photo), **When** a miss is scored,
   **Then** its master relation is "unknown" and it is counted in a distinct
   bucket, excluded from near-miss classification — never guessed.
5. **Given** candidates served by the pipeline, **When** their source search
   results include a master id, **Then** it is carried verbatim (absent stays
   absent) — like every other candidate field.

---

### Edge Cases

- A release whose catalog number is empty/absent on candidates: such
  candidates are simply never "exact matches"; ordering among them is
  unchanged.
- Multi-catno candidates (Discogs lists several): if any of the candidate's
  catalog numbers normalizes equal to the searched value, it is an exact
  match.
- The deeper catno fetch still returns fewer results than the cap: behavior
  identical to today apart from ordering.
- `more_matches` reporting must reflect the true total found by Discogs, not
  the deeper fetch size.
- A same-master candidate at rank 1 on a *hit* is irrelevant — near-miss
  classification applies only to misses.
- Truth master id of 0 or missing from Discogs: treated as "no master"
  (unknown relation), never matched against candidates' masters.
- Backfill mode on a manifest whose release was deleted from Discogs (404):
  the release keeps its old entry; backfill records the failure honestly and
  continues.
- Old eval runs (023 format) remain readable; new fields are additive.

## Requirements *(mandatory)*

### Functional Requirements

**Exact-catno re-rank (US1)**

- **FR-001**: On the catno rung only, the pipeline MUST fetch a deeper result
  page than the candidate cap, with the depth sourced from configuration
  (default deeper than any observed drowning case, e.g. 50). All other rungs
  keep their existing fetch depth.
- **FR-002**: Candidates whose catalog number — after separator/whitespace
  removal and case folding — exactly equals the normalized searched catalog
  number MUST be ordered before all non-exact candidates; within each group
  the source order is preserved (stable re-rank). The list is then truncated
  to the existing candidate cap.
- **FR-003**: A candidate with multiple catalog numbers is exact if ANY of
  them normalizes equal; candidates with no catalog number are never exact.
- **FR-004**: When no exact match exists in the fetched page, the served
  candidate list MUST be identical to pre-024 behavior (source order, capped).
- **FR-005**: Candidate fields remain verbatim from the search payload;
  re-ranking changes order only. `more_matches` MUST still reflect the true
  total reported by the search, relative to the number of candidates served.
- **FR-006**: The re-rank applies wherever the catno rung runs — live scan
  page and eval harness — because they share the pipeline; no eval-only fork.

**Evidence in eval results (US2)**

- **FR-007**: Every evaluated result record MUST carry the compact
  extracted-evidence values (the scan journal's existing compact shape:
  extracted values only, empties omitted). Empty extraction ⇒ empty/absent
  field; unlabeled records (no vision call) carry none.
- **FR-008**: The addition is backward-compatible: 023-format results files
  remain valid, and new files differ only by the added field.

**Same-master metric (US3)**

- **FR-009**: The dataset builder MUST record the truth release's master id
  in the manifest when Discogs provides one, using data already fetched (zero
  extra requests during a normal build).
- **FR-010**: A builder backfill mode MUST add master ids to already-done
  manifest releases by re-fetching release metadata only (no image
  downloads); its manifest entries supersede older ones for the same release
  (newest-entry-wins rule for readers), and image ground truth already
  recorded is preserved. Fetch failures during backfill are recorded honestly
  and skipped, never guessed.
- **FR-011**: Pipeline candidates MUST carry the search result's master id
  verbatim when present (absent stays absent), like every other candidate
  field.
- **FR-012**: The harness MUST classify every miss as: `same_master`
  (some candidate's master id equals the truth's known master id),
  `different` (truth master known, no candidate master matches), or
  `unknown` (truth master unknown, or no candidates carried master ids to
  compare). Classification never involves additional network requests.
- **FR-013**: The summary MUST report, alongside the unchanged strict
  identification rate (still primary): the near-miss count by class and a
  practical rate = (hits + same-master near-misses) over the strict rate's
  denominator. Sum invariants extend accordingly and remain normative.
- **FR-014**: Retained-source photos have no master ground truth in v1; their
  misses are always `unknown` (no live lookups — out of scope).

**Shared discipline**

- **FR-015**: All new tunables (catno fetch depth) MUST be sourced from
  configuration, never hardcoded (VII(a)).
- **FR-016**: The offline test suite MUST cover the re-rank ordering rules,
  evidence passthrough, classification rules, backfill supersession, and the
  extended sum invariants — with zero live calls, as before.

### Key Entities

- **Exact-catno match**: a candidate any of whose catalog numbers, normalized
  (separators/whitespace stripped, case folded), equals the normalized
  searched catalog number.
- **Truth master id**: the master identifier of a dataset image's
  ground-truth release, recorded in the manifest at build/backfill time;
  optional (Discogs has master-less releases).
- **Miss master-relation**: per-miss classification — `same_master` /
  `different` / `unknown`.
- **Practical rate**: (hits + same-master near-misses) / strict denominator;
  reported beside, never instead of, the strict rate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Replaying the two measured drowning cases (`SUB 15`,
  `FD 006`-class: exact match present in the deeper fetch but outside the old
  top-8) as offline scripted tests puts the exact-catno candidate at
  position 1 of the served list.
- **SC-002**: A fresh eval run over the same 023 dataset shows the catno
  rung's hit count no lower than the baseline (20 of 42 tried), with the
  drowned-exact-match class converted; no other rung's behavior changes.
- **SC-003**: Every zero-candidate miss in a new results file is diagnosable
  from the file alone: the record shows exactly which values were extracted
  and which rungs ran.
- **SC-004**: After a backfilled dataset, the summary reports strict AND
  practical rates whose difference equals the same-master near-miss share;
  all extended sum invariants hold (misses = same_master + different +
  unknown).
- **SC-005**: The strict identification rate's definition and all 023
  contracts' invariants remain intact (additive change only); 023-format
  results and manifests stay readable.
- **SC-006**: The full offline suite passes with zero live calls; the live
  scan page's non-catno behavior is unchanged (existing tests unmodified
  except where they assert catno-rung internals).

## Assumptions

- Discogs search results expose a master id for most catalogued releases;
  where absent, the unknown bucket absorbs the case (never guessed).
- Catno normalization = remove separators/whitespace (spaces, hyphens, dots,
  slashes) + case fold. This mirrors 022's barcode/catno normalization
  precedent (FR-019 there) and matched every observed drowning case; smarter
  equivalences (leading zeros, label-prefix aliases) are deliberately not
  attempted in v1.
- Default catno fetch depth of 50 covers the observed cases (`SUB 15x`
  family ≈ a dozen entries) with ample headroom while staying one request.
- The deeper fetch is still a single search request per catno rung, so rate
  budget and one-cycle cost are unchanged in request count.
- Backfill is owner-run and rate-governed like a normal build; at 300–1k
  releases it completes in one sitting.
- The practical rate is an *upper* bracket and the strict rate a *lower*
  bracket of real-world accuracy; both appear together wherever one appears.

## Out of Scope

- Vision prompt changes (022's prompt stays frozen; measured separately).
- Fetch-depth or ordering changes on any rung other than catno.
- Replacing strict release-id scoring as the primary metric.
- Resolving masters for retained-source photos via live lookups at eval time.
- Master-level (fuzzy) matching in the live scan page's duplicate detection
  or anywhere outside eval scoring.
- UI changes to the scan page (candidate ordering flows through untouched).
