# Feature Specification: Evidence-Replay Eval Mode + Barcode Plausibility Gate

**Feature Branch**: `025-eval-replay-barcode-gate`
**Created**: 2026-07-11
**Status**: Draft
**Input**: User description: "Evidence-replay eval mode + barcode plausibility gate (feature 025, collection-agent only). Two items motivated by the 2026-07-11 post-024 eval run (20260711-222805Z-discogs: strict 52.1%, top-1 37.2%, practical 56.4%, 0 errors, vs pre-024 baseline 56.4% strict) where per-image diffing showed 20 of 94 images flipped outcome purely from vision nondeterminism (8 miss→hit, 12 hit→miss) — all of 024's target catno-drowning cases converted with zero re-rank regressions, but ±10-image vision noise swamps the +4 aggregate gain, so single-run strict-rate comparisons cannot resolve search-ladder changes. (1) Evidence-replay eval mode: a new eval-run option (e.g. --replay <run_id>) that re-runs ONLY the search ladder over the evidence values recorded in a prior run's results.jsonl. Deterministic, zero vision calls/cost — the correct instrument for A/B-ing ladder changes. (2) Barcode plausibility gate: the run caught vision emitting a 4-digit \"barcode\" (3070, image 17859_secondary1.jpeg, Cybotron) that hijacked the highest-precision barcode rung and killed a previously-hit catno (D-216). Real UPC/EAN are 8–13 digits; add a deterministic minimum-digit plausibility rule mirroring 022's FR-019 precedent. Also owed: an honest inconclusive-reading note in 024's quickstart."

## Context & Motivation

The 2026-07-11 eval run (`20260711-222805Z-discogs`, 94 images, after the
024 merge and a master backfill of 42 releases / 8 masterless) measured
strict 52.1%, top-1 37.2%, practical 56.4%, 0 errors — against the pre-024
baseline of strict 56.4% (`20260707-231623Z-discogs`). A per-image diff of
the two runs showed:

- **20 of 94 images flipped outcome between runs from vision
  nondeterminism alone** (8 miss→hit, 12 hit→miss) — the same photo,
  the same pipeline rung logic, different extracted evidence per run.
- **Every one of 024's target catno-drowning cases converted** (SUB 15 →
  catno hit at rank 2, FING 1 at rank 4, Angelfish at rank 3, EUHO 021-6,
  DIG 019) with zero regressions attributable to the exact-catno re-rank.

Conclusion: the ±10-image vision noise swamps the ~4-image aggregate gain,
so **single-run strict-rate comparisons cannot resolve search-ladder
changes**. The eval harness measures the whole pipeline (vision + ladder)
but provides no instrument for measuring the ladder alone. Item 1 adds
that instrument. Separately, the run surfaced a concrete ladder-input
defect (item 2): vision emitted a 4-digit "barcode" (`3070`, image
`17859_secondary1.jpeg`, Cybotron) that occupied the highest-precision
barcode rung, returned wrong candidates, and thereby prevented the catno
rung from firing on the correctly-extracted `D-216` — an image the
baseline run had identified. Real UPC/EAN barcodes are 8–13 digits; a
4-digit digit-run can never be one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Replay a prior run's evidence to A/B a ladder change (Priority: P1)

The owner has a completed eval run whose per-image records carry the
extracted evidence values (024's `evidence` field). After changing the
search ladder (or to establish a like-for-like baseline before changing
it), the owner replays that run: every image's *recorded* evidence is fed
through the current search ladder — no photos re-read, no vision calls,
no vision cost — producing a new results/summary pair in the standard
shape. Because the evidence inputs are byte-identical between replays,
any per-image outcome difference between two replays of the same source
run is attributable to the ladder change (or, rarely, Discogs catalog
drift), not to vision nondeterminism.

**Why this priority**: This is the measurement instrument the 024
follow-up analysis proved is missing. Without it, no future ladder change
(including this feature's own barcode gate) can be validated: vision
noise of ±10 images per 94 drowns single-digit true gains. It is also the
prerequisite for honestly evaluating item 2.

**Independent Test**: Replay an existing run twice with unchanged code
and confirm per-image outcomes are identical across the two replays; then
replay the same run after a deliberate ladder change and confirm the diff
contains only images whose evidence the change touches.

**Acceptance Scenarios**:

1. **Given** a completed prior run whose records carry evidence, **When**
   the owner starts a replay of that run, **Then** a new run directory is
   produced with one result per source record and a summary satisfying
   all existing invariants, and zero vision calls are made or billed.
2. **Given** the same source run replayed twice with unchanged search
   logic, **When** the two replays' per-image outcomes are compared,
   **Then** they are identical (the only permitted source of difference
   is Discogs-side catalog drift between the replays, not anything local).
3. **Given** a source record that carries recorded evidence (including a
   record whose original outcome was a search-stage error), **When** the
   replay processes it, **Then** the current production search ladder is
   re-run over exactly the recorded evidence values and the outcome is
   scored afresh against the record's recorded truth.
4. **Given** a source record without recorded evidence (an original
   `no_evidence` record, a pre-search vision-stage error, or an unlabeled
   record), **When** the replay processes it, **Then** it is carried
   through with its original outcome category — never re-photographed,
   never re-vision'd — so both runs' denominators stay comparable.
5. **Given** a replay identifier that does not correspond to a prior run
   (or a prior run whose records carry no evidence at all), **When** the
   owner starts a replay, **Then** the command fails fast with a clear
   configuration-error message and no run directory is left behind as if
   it were a completed run.
6. **Given** a completed replay, **When** the owner inspects its summary
   and records, **Then** the replay is clearly distinguishable from a
   camera-source run and names the source run it replayed.

---

### User Story 2 - Implausible barcodes no longer hijack the barcode rung (Priority: P2)

The owner scans a record (via the phone page or the eval) where vision
emits a short digit-run — e.g. a 4-digit matrix or catalog fragment — in
the barcode field. Because real UPC/EAN barcodes are 8–13 digits, the
system recognizes the value as implausible, clears it from the barcode
evidence, and lets the remaining evidence (catno, artist+title) drive the
search ladder exactly as if no barcode had been read. The Cybotron case
(`17859_secondary1.jpeg`: fake barcode `3070` suppressing a correct catno
`D-216`) identifies again.

**Why this priority**: A measured, reproducible accuracy defect with a
deterministic fix — but its honest validation depends on US1's
instrument, so it is second in sequence. The fix lands in the shared
evidence normalization, so it reaches the phone scan page and the eval
alike; the vision prompt stays frozen.

**Independent Test**: Feed evidence containing a sub-8-digit barcode plus
a valid catno through the pipeline and confirm the barcode rung never
fires, the catno rung does, and journal/eval evidence records reflect the
post-gate values. Then replay the 2026-07-11 run (via US1) and confirm
the Cybotron image converts miss→hit with no regression on any image
whose evidence carries a plausible (8+ digit) barcode.

**Acceptance Scenarios**:

1. **Given** extracted evidence with a barcode of fewer than 8 digits and
   a catalog number, **When** candidates are searched, **Then** the
   barcode rung is not attempted, the catno rung fires, and the recorded
   evidence kinds and rungs-tried reflect that.
2. **Given** extracted evidence whose only field is a sub-8-digit
   barcode, **When** the scan is processed, **Then** it is treated as
   no-evidence (routes to no-match/no_evidence), not as a barcode search.
3. **Given** extracted evidence with a barcode of 8 or more digits,
   **When** the scan is processed, **Then** behavior is byte-identical to
   pre-025 (the gate never touches plausible barcodes).
4. **Given** a catalog-number field containing a 10+-digit separator-
   stripped digit run (022's existing reclassification), **When**
   evidence is normalized, **Then** the reclassified barcode still lands
   in the barcode field and is never gated (it is by construction ≥ 10
   digits) — the two rules compose without conflict.
5. **Given** the phone scan page and the eval harness, **When** each
   processes the same evidence containing an implausible barcode,
   **Then** both exhibit the gate identically (shared pipeline, one
   normalization site).

---

### User Story 3 - 024's quickstart records its inconclusive live reading honestly (Priority: P3)

A future reader of 024's quickstart / owner checklist finds an explicit
note that the SC-002 fresh-eval reading was **inconclusive under vision
variance** — catno-rung hits 17 vs baseline 20, while every one of 024's
target catno-drowning cases confirmed converted — rather than an
unqualified pass or an unexplained open checkbox.

**Why this priority**: Documentation honesty only — no behavior change.
It closes 024's dangling owner-validation item with what was actually
observed, preserving the project's recorded-honesty discipline (023's
upper-bound caveat precedent).

**Independent Test**: Read `specs/024-scan-accuracy-followups/quickstart.md`
and confirm the SC-002 item records the 2026-07-11 numbers, the
inconclusive aggregate reading, the confirmed per-case conversions, and a
pointer to 025's replay mode as the instrument that resolves this class
of comparison.

**Acceptance Scenarios**:

1. **Given** 024's quickstart owner checklist, **When** 025 lands,
   **Then** the SC-002 item is annotated with the 2026-07-11 run's
   outcome: aggregate inconclusive under vision variance, all target-class
   conversions confirmed, zero re-rank-caused regressions.

---

### Edge Cases

- **Replay of a replay**: a replay's own records carry evidence in the
  same shape, so replaying a replay is legal and behaves identically to
  replaying the original (the chain's evidence is byte-identical anyway).
- **Source run predates 024** (records lack the evidence field entirely):
  the replay fails fast with a clear message telling the owner the run is
  too old to replay — it is not silently scored as all-no-evidence.
- **Torn trailing line** in the source run's records (interrupted run):
  tolerated — the torn line is skipped, matching the established
  manifest-reader tolerance; every complete record is replayed.
- **Original record was a search-stage error** (evidence present, search
  failed): replayed normally — the evidence exists, so the ladder re-runs
  and may now succeed; the replay's own search failures are recorded as
  that replay's errors, per the existing taxonomy.
- **Original record was a vision-stage error** (no evidence recorded):
  carried through as an error of the same kind with zero search work —
  "cannot replay what was never extracted" — keeping denominators
  aligned with the source run.
- **Truth master unknown at replay time**: miss near-miss buckets are
  computed by the same rules as a camera run, resolving truth master ids
  from local dataset metadata when available; when unavailable, the
  bucket is `unknown` — never guessed, never fetched live.
- **Replay combined with a camera source**: a replay names its input run;
  asking for both a replay and an image source in one invocation is a
  configuration error, not a silent precedence rule.
- **Limit on a replay**: an explicit limit truncates the replayed records
  the same way it truncates an image source, and the summary flags it.
- **Barcode with exactly 8 digits**: plausible (UPC-E/EAN-8 exist);
  processed exactly as today.
- **Digit-run with separators in the barcode field** (e.g. `3 070`):
  the existing digits-only barcode normalization already strips
  non-digits before the gate sees the value; the gate judges digit count
  only.
- **Gated barcode alongside no other evidence**: the scan becomes
  no-evidence and routes to the existing no-match path — it must not
  crash or fabricate a rung.

## Requirements *(mandatory)*

### Functional Requirements

**Evidence-replay eval mode (US1)**

- **FR-001**: The eval command MUST offer a replay mode that takes the
  identifier of a prior run and re-evaluates that run's per-image records
  using only locally recorded data: the recorded evidence values and the
  recorded ground-truth release per image. It MUST NOT read image files
  and MUST NOT make any vision/LLM call — replay is billed zero vision
  calls, and every replay record reports zero vision calls.
- **FR-002**: For every source record carrying recorded evidence
  (including records whose original outcome was a search-stage error),
  the replay MUST re-run the unmodified production search ladder — the
  same code path the phone page and camera-source eval use (023 FR-011
  discipline) — over exactly the recorded evidence values, and score the
  fresh outcome against the record's recorded truth.
- **FR-003**: Source records without recorded evidence MUST be carried
  through honestly, never re-extracted: original `no_evidence` records
  remain `no_evidence`; original vision-stage errors remain errors of
  that kind with no search performed; `unlabeled` records remain
  `unlabeled` and are never evaluated. The replay's totals MUST cover
  every source record exactly once so the two runs' denominators are
  directly comparable.
- **FR-004**: A replay MUST produce a standard run directory — per-image
  records appended incrementally and a summary — in the existing
  contracted shapes with all existing invariants holding, plus explicit
  replay provenance: the output MUST be distinguishable as a replay and
  MUST name the source run it replayed. Existing readers of 023/024-shape
  results MUST remain able to read replay output.
- **FR-005**: Replay MUST be structurally read-only to the same standard
  as the rest of the eval surface (no writes to Discogs, no journal or
  session writes, covered by the existing structural guard) and MUST
  never modify the source run's files. Live Discogs *search reads* are
  performed under the existing rate governor, exactly like a camera run.
- **FR-006**: Replay MUST fail fast with a configuration error (existing
  exit-code conventions) when the named source run does not exist, has no
  readable records, or contains no replayable records (e.g. a pre-024 run
  with no evidence fields). A torn trailing record line MUST be tolerated
  (skipped), matching established reader behavior. Naming both a replay
  source and an image source in one invocation is a configuration error.
- **FR-007**: Replay MUST compute miss near-miss (master-relation)
  buckets by the same rules as a camera run, resolving truth master ids
  from local dataset metadata when available and reporting `unknown` when
  not — never guessing and never making metadata lookups beyond the
  search ladder's own requests.
- **FR-008**: An explicit record limit MUST apply to replay the same way
  it applies to image sources, flagged in the summary.

**Barcode plausibility gate (US2)**

- **FR-009**: Evidence normalization MUST treat a barcode value whose
  digit count is below the plausibility minimum (8 digits — the shortest
  real UPC-E/EAN-8 forms; upper bounds are out of scope) as *not a
  barcode*: the value is cleared from the barcode field before any
  search-ladder or evidence-kind decision. Plausible barcodes (8+ digits)
  MUST be processed byte-identically to pre-025.
- **FR-010**: The gate MUST live at the single shared evidence-
  normalization site (the 022 FR-019 precedent) so the phone scan page
  and the eval harness — camera and replay alike — inherit it
  identically, with no per-surface divergence. The vision prompt MUST NOT
  change.
- **FR-011**: The gate MUST compose with 022's existing long-digit-run
  catno→barcode reclassification: a reclassified value (by construction
  10+ digits) is never gated, and the gate MUST NOT move a cleared
  barcode into the catalog-number field (a short digit run is not
  reliably a catalog number; injecting it could hijack the catno rung the
  same way the fake barcode hijacked the barcode rung).
- **FR-012**: All downstream evidence representations — evidence kinds,
  rungs tried, journal lines, eval records — MUST reflect the post-gate
  values, consistent with how post-normalization evidence is recorded
  today (no "ghost" barcode rung in any record).

**024 documentation debt (US3)**

- **FR-013**: 024's quickstart owner checklist MUST be updated to record
  the SC-002 reading honestly: the 2026-07-11 fresh-eval aggregate was
  inconclusive under vision variance (catno-rung hits 17 vs baseline 20)
  while all target catno-drowning cases confirmed converted with zero
  re-rank-caused regressions, and single-run comparisons cannot resolve
  ladder changes — with a pointer to 025's replay mode as the instrument.

### Key Entities

- **Source run record**: one prior per-image result — its recorded
  evidence values (present iff extraction produced values), recorded
  truth release, original outcome category, and image name. The replay's
  unit of input; never modified.
- **Replay run**: a standard eval run whose inputs are source run records
  instead of images; carries provenance (which run it replayed) and
  produces the standard per-image records and summary with zero vision
  cost.
- **Replayable record**: a source record carrying recorded evidence —
  re-run through the search ladder. Non-replayable records (no evidence)
  are carried through by category.
- **Plausible barcode**: a digits-only barcode value of at least 8 digits
  (UPC-E/EAN-8 through EAN-13-and-beyond). Anything shorter is cleared
  from evidence by the plausibility gate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Two back-to-back replays of the same source run with
  unchanged search logic produce identical per-image outcomes (100% of
  records; the only tolerated difference source is remote catalog drift
  between the two replays, which back-to-back execution minimizes).
- **SC-002**: A replay of the 2026-07-11 run (`20260711-222805Z-discogs`)
  under the barcode gate converts the Cybotron image
  (`17859_secondary1.jpeg`) from miss to hit via the catalog-number rung,
  and no image whose evidence carries a plausible (8+ digit) barcode
  changes outcome relative to a pre-gate replay of the same run.
- **SC-003**: Replays make zero vision calls (summary reports 0) and a
  ~94-record replay completes in under 5 minutes under the standard rate
  governor — an A/B iteration that previously cost a full vision run
  becomes free of vision cost and latency.
- **SC-004**: A replay's evaluated/total counts equal its source run's
  (denominator parity), so strict/top-1/practical rates are directly
  comparable between the source run and any of its replays.
- **SC-005**: Every existing test remains green with the gate on by
  construction (no flag): evidence with plausible barcodes and all
  non-barcode evidence flows are byte-identical to pre-025.
- **SC-006**: 024's quickstart SC-002 item reads as an honest,
  self-contained record of the inconclusive live validation (numbers,
  confirmed conversions, and the instrument that supersedes the
  comparison method).

## Assumptions

- **Replay determinism claim scope**: replay eliminates *local*
  nondeterminism (vision). The search ladder still performs live Discogs
  search reads, so the remote catalog can drift between runs; this is
  accepted and documented rather than mocked away, because the instrument
  exists to compare ladder logic against the live service it actually
  queries.
- **Ground truth source**: the replayed run's own records are the ground
  truth (truth release per image travels with the record). The dataset
  manifest is consulted only to resolve truth *master* ids for the
  near-miss buckets, and only if locally available; images are never
  needed.
- **Plausibility minimum = 8 digits**: UPC-E and EAN-8 are the shortest
  real retail barcode forms. No upper-bound gate is added (022's existing
  10+-digit catno reclassification already handles the long direction,
  and EAN add-on codes legitimately exceed 13 digits).
- **Cleared means dropped, not reclassified**: unlike 022's FR-019 (a
  10+-digit run is *definitively* a barcode), a short digit run is not
  definitively a catalog number — moving it into the catno field could
  hijack that rung with junk. The gate clears the barcode field and lets
  genuinely-extracted evidence drive the ladder.
- **No configuration knob for the threshold**: mirrors 022's
  `BARCODE_MIN_DIGITS` precedent (a domain constant, not a tunable) —
  barcode formats don't vary by deployment.
- **Component scope**: `collection-agent` only; no new dependencies
  anticipated. Vision prompt changes, image preprocessing, CI eval
  integration, and master-level scoring changes remain out of scope
  (unchanged from 023/024 boundaries).
