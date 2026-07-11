# Tasks: Evidence-Replay Eval Mode + Barcode Plausibility Gate

**Input**: Design documents from `/specs/025-eval-replay-barcode-gate/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: included — this repo's constitution (IV, quality gates) and the
023/024 precedent make the new invariants unit-tested in the same change
set; the suite stays offline (FakeDiscogsClient, no live API calls).

**Organization**: grouped by user story. US1 (replay instrument) is the
MVP; US2 (barcode gate) is independent code-wise but its *validation*
uses US1; US3 is a documentation edit.

All `collection-agent` paths below are relative to `collection-agent/`
(run tests with `cd collection-agent && uv run pytest`).

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Confirm clean baseline: `cd collection-agent && uv run pytest`
      → 450 passed, no network; note the count for the PR description.

*(No other setup: zero new dependencies, zero new Settings fields, no
scaffolding — the eval package and test files already exist.)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the additive record/summary fields both replay tasks and the
summary printing depend on.

- [ ] T002 Add `EvalResult.replayed: bool | None = None` and
      `EvalSummary.replay_of: str | None = None` in
      `src/collection_agent/eval/scoring.py` (docstrings citing
      `amendment-023-eval-results-2.md` deltas 3–4; no logic change to
      `score_search_outcome`/`summarize` beyond passing `replay_of`
      through `summarize(...)` as an optional arg defaulting to None).
- [ ] T003 Unit tests in `tests/unit/test_eval_scoring.py`: (a) a
      camera-run `EvalResult`/`EvalSummary` serializes byte-identically
      to pre-025 (`exclude_none` omits the new fields — invariant 12's
      "never appears in a camera run"); (b) `summarize(...,
      replay_of="X")` lands the field; (c) a 024-format summary/record
      dict (without the new fields) still validates (backward read).

**Checkpoint**: camera-eval behavior provably unchanged; replay fields exist.

---

## Phase 3: User Story 1 — Replay a prior run's evidence to A/B a ladder change (Priority: P1) 🎯 MVP

**Goal**: `eval-run --replay <run_id>` re-runs ONLY the production search
ladder over a prior run's recorded evidence — zero vision calls, no
OpenAI key — producing a standard, provenance-carrying run
(contracts/amendment-023-eval-results-2.md).

**Independent Test**: build a fixture source run (results.jsonl with
hit/miss/no_evidence/vision_error/discogs_error/unlabeled records), run
the replay against a scripted `FakeDiscogsClient`, and verify: per-record
carry-through vs replayed partition, fresh scoring, provenance fields,
invariants 11–14, and that two identical replays produce identical
outcomes.

### Tests for User Story 1 (write first, watch them fail)

- [ ] T004 [P] [US1] Unit tests (new file)
      `tests/unit/test_eval_replay.py` — source-run reader: parses a
      well-formed results.jsonl; skips blank lines; tolerates a torn
      trailing line (partial JSON) while keeping all complete records;
      ignores unknown fields; `SourceError` on missing run dir, missing
      results.jsonl, empty file, and zero evidence-carrying records
      (pre-024 run) — message names the run id (FR-006).
- [ ] T005 [P] [US1] Unit tests in `tests/unit/test_eval_replay.py` —
      replayability partition (R3 table): evidence-carrying hit / miss /
      post-vision discogs_error records become replay items; `unlabeled`,
      `no_evidence`, evidence-less `error` (kind preserved), and the
      defensive evidence-less hit/miss become carry-throughs with the
      correct category + detail; every source record yields exactly one
      item (FR-003).
- [ ] T006 [P] [US1] Unit tests in `tests/unit/test_eval_replay.py` —
      truth-master re-resolution (R5): manifest present → discogs-source
      items get `truth_master_id` via newest-line-wins; manifest absent →
      None; retained-source records always None; no network anywhere.
- [ ] T007 [P] [US1] Integration test in
      `tests/integration/test_eval_harness.py` — end-to-end `run_replay`
      over a tmp-dir fixture source run + scripted `FakeDiscogsClient`:
      (a) run dir named `*-replay`, results.jsonl + summary.json written;
      (b) summary `replay_of` = source run id, `vision_calls == 0`,
      every record carries `replayed` and `vision_calls == 0`
      (invariants 11–12); (c) denominator parity: one output record per
      source record, same `image` names, unlimited (invariant 13);
      (d) hits/misses only from `replayed == true` records
      (invariant 14); (e) an original discogs_error record with evidence
      is re-scored (can flip to hit); (f) a fresh scripted search failure
      records that replay's own discogs_error; (g) two back-to-back
      replays over the same scripted client produce identical per-image
      outcomes (SC-001); (h) `--limit`-equivalent arg truncates and sets
      `limited`; (i) the source run's files are byte-identical after the
      replay (read-only input).

### Implementation for User Story 1

- [ ] T008 [US1] New module `src/collection_agent/eval/replay.py`:
      `ReplayItem` model (data-model §2, evidence/carry_outcome mutual
      exclusion), `load_source_run(settings, run_id) -> list[ReplayItem]`
      implementing the reader (torn-line tolerance), the R3 partition,
      and R5 truth-master re-resolution (reuse `dataset.load_manifest` +
      `newest_release_lines`; manifest optional). Raise
      `sources.SourceError` for all fail-fast cases BEFORE any run dir is
      created. Module docstring cites the amendment; no journal/session
      imports (AST guard covers this automatically).
- [ ] T009 [US1] `run_replay(discogs_client, settings, replay_of, limit,
      notify)` in `src/collection_agent/eval/harness.py`: replay items →
      per-item evaluation (`replay_item` fn: carry-through short-circuit,
      else `ScanEvidence(**evidence)` re-materialization →
      `find_candidates` → `score_search_outcome`, `vision_calls=0`,
      `replayed` set on every record) — reusing the existing incremental
      fsync'd write loop and `summarize` (pass `replay_of`,
      `dataset_snapshot_completeness=None`); run id `_run_id("replay")`.
      Factor the shared run-dir/write/summary plumbing out of `run_eval`
      rather than duplicating it.
- [ ] T010 [US1] CLI in `src/collection_agent/cli.py`: `--replay RUN_ID`
      on the `eval-run` subparser (help: "re-run the search ladder over a
      prior run's recorded evidence (025; zero vision calls)");
      `--source` default becomes `None`, resolved to `"discogs"` iff
      `--replay` absent; both explicit → console error + `EXIT_CONFIG`;
      replay path skips the `OPENAI_API_KEY` gate and never calls
      `_build_llm_client`; `_print_eval_summary` gains a
      `replay of <run_id>` row when `replay_of` is set.
- [ ] T011 [US1] CLI-level integration tests (same style as existing CLI
      tests) in `tests/integration/test_eval_harness.py`: `--replay` +
      `--source` → exit 2; `--replay` with unset `OPENAI_API_KEY` runs
      (monkeypatched `run_replay`); unknown run id → exit 2 with the
      SourceError message.
- [ ] T012 [US1] Verify guards untouched-but-covering: run
      `uv run pytest tests/unit/test_eval_readonly_guard.py
      tests/unit/test_eval_gitignore_guard.py` — the new `eval/replay.py`
      must pass the AST sweep with zero guard-file edits.

**Checkpoint**: replay works end-to-end offline; SC-001/003/004
mechanically verifiable. MVP deliverable.

---

## Phase 4: User Story 2 — Implausible barcodes no longer hijack the barcode rung (Priority: P2)

**Goal**: sub-8-digit barcode evidence is cleared at the shared
normalization site (`ScanEvidence`), so the barcode rung can't fire on it
anywhere (phone page, camera eval, replay); plausible barcodes are
byte-identical to 024 (contracts/amendment-022-scan-api-2.md).

**Independent Test**: construct `ScanEvidence` with implausible/plausible
barcodes and assert the gate + composition with FR-019; drive the ladder
with gated evidence and assert the catno rung fires first.

### Tests for User Story 2 (write first, watch them fail)

- [ ] T013 [P] [US2] Unit tests in `tests/unit/test_scan_models.py` —
      the gate (FR-009/011/012): 7-digit and 4-digit barcodes (incl. the
      live `"3070"`) cleared → not in `evidence_kinds`, absent from
      `compact_dump()`; exactly 8 digits kept; 13 digits kept; separators
      stripped first (`"3 0-70"` → 4 digits → cleared; existing
      normalization); cleared value NEVER moves to `catno` (catno stays
      exactly as extracted, both when present and when absent);
      barcode-only implausible evidence → `is_empty` True; FR-019
      composition: an 11-digit `catno` still reclassifies to `barcode`
      and survives the gate.
- [ ] T014 [P] [US2] Ladder test in `tests/unit/test_scan_search.py` —
      Cybotron-shaped evidence (`barcode="3070"` pre-gate, catno
      `"D-216"`, artist/label): after construction the ladder's first
      rung tried is `catno` (scripted `FakeDiscogsClient` asserts no
      `barcode=` search parameter is ever sent), and `rungs_tried`
      reflects post-gate reality (no ghost rung).

### Implementation for User Story 2

- [ ] T015 [US2] `src/collection_agent/scan/models.py`: add
      `BARCODE_PLAUSIBLE_MIN_DIGITS = 8` beside `BARCODE_MIN_DIGITS` and
      a `_gate_implausible_barcode` model validator defined AFTER
      `_reclassify_barcode_in_catno` (pydantic v2 definition order —
      data-model §5): clear `barcode` when `0 < len(barcode) <
      BARCODE_PLAUSIBLE_MIN_DIGITS`; comment cites the live case (3070 /
      D-216) and the drop-don't-reclassify rationale (R7).
- [ ] T016 [US2] Regression sweep: `uv run pytest tests/unit/
      test_scan_models.py tests/unit/test_scan_search.py tests/unit/
      test_scan_vision.py tests/integration/test_scan_server.py` — all
      pre-existing scan tests pass unmodified (SC-005: no test asserted a
      sub-8-digit barcode surviving; if one did, STOP — that's a spec
      conflict to surface, not a test to edit).

**Checkpoint**: gate live everywhere `ScanEvidence` is constructed;
US1+US2 together make SC-002 (Cybotron flip) measurable by the owner.

---

## Phase 5: User Story 3 — 024 quickstart records its inconclusive live reading (Priority: P3)

**Goal**: FR-013 — close 024's dangling SC-002 checklist item honestly.

**Independent Test**: read the edited file; the item is self-contained
(numbers + reading + pointer), not an unexplained open checkbox.

### Implementation for User Story 3

- [ ] T017 [P] [US3] Edit `specs/024-scan-accuracy-followups/quickstart.md`
      SC-002 checklist item: annotate with the 2026-07-11 run
      (`20260711-222805Z-discogs`, after `--backfill-masters` of 42
      releases / 8 masterless): strict 52.1% / top-1 37.2% / practical
      56.4% vs 56.4% baseline; catno-rung hits 17 vs 20; per-image diff:
      20/94 outcomes flipped on vision nondeterminism (8 miss→hit, 12
      hit→miss); ALL target drowning cases converted (SUB 15 rank 2,
      FING 1 rank 4, Angelfish rank 3, EUHO 021-6, DIG 019) with zero
      re-rank-caused regressions → **aggregate reading inconclusive under
      vision variance; conversions confirmed**; single-run strict-rate
      comparison cannot resolve ladder changes — superseded by 025's
      `eval-run --replay` (link `specs/025-eval-replay-barcode-gate/`).
      Match the file's existing checklist voice; mark the item resolved
      the way 023's validation notes do.

**Checkpoint**: all three stories complete.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T018 [P] Update `collection-agent/README.md` eval section: replay
      mode (command, zero-vision/no-OpenAI-key property, what it holds
      constant vs re-runs live — one honest paragraph mirroring
      quickstart's), and the barcode plausibility gate one-liner in the
      scan section.
- [ ] T019 Full offline gate: `cd collection-agent && uv run pytest` —
      all tests green (expect ~450 + new); confirm zero live API/network
      use in the suite (existing conftest guards).
- [ ] T020 Quickstart self-check (offline parts): run the T019 command
      exactly as quickstart states it; verify the jq diff recipe against
      two fixture results files in the scratchpad (not committed).
- [ ] T021 CLAUDE.md merged-state block: rewrite the 025 in-flight
      pointer into the post-merge summary block (single-PR flow, owner
      decision 2026-07-07 — lands in THIS feature branch/PR), demoting
      024 to "Prior feature" and recording: what shipped, run/live
      numbers that motivated it, invariants 11–14, contracts amended,
      tests count, out-of-scope kept, owner-only live checklist
      (quickstart SC-001..SC-006) still open.

---

## Owner-only live validation (post-merge, not executable by the agent)

Tracked in `quickstart.md`'s checklist, requires the owner's Discogs
token / dataset / phone:

- [ ] T022 [OWNER] quickstart SC-001 (replay determinism, live),
      SC-002 (Cybotron flip + gate-population audit), SC-003 (cost/
      latency), SC-004 (denominator parity vs source run), SC-005 (one
      physical plausible-barcode scan), SC-006 (read the 024 note).

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2**: T001 first (baseline). T002 blocks T003 and all
  of US1 (replay code sets/reads the new fields).
- **US1 (Phase 3)**: T004–T007 (tests, parallel) before T008–T010
  (implementation); T008 → T009 → T010 (module → harness → CLI);
  T011–T012 after T010.
- **US2 (Phase 4)**: independent of US1 code — only Phase 2 blocks it
  (and nothing in Phase 2 touches scan models, so US2 can start any time
  after T001; sequenced after US1 here because its *measurement* story
  uses the replay instrument). T013–T014 before T015; T016 after T015.
- **US3 (Phase 5)**: T017 has no code dependency; kept near the end so
  the note can reference 025's replay mode as an existing fact.
- **Polish**: T018 parallel with anything post-US2; T019–T021 last, in
  order.

### Parallel opportunities

- T004, T005, T006, T007 (four different test concerns; T004–T006 same
  new file — write in one pass if a single agent, parallel if split by
  file only), T013+T014, T017, T018.
- US2 (T013–T016) can proceed fully in parallel with US1 (T004–T012):
  disjoint files (`scan/models.py`+scan tests vs `eval/`+eval tests).

## Implementation Strategy

MVP = Phases 1–3 (the instrument alone is shippable and immediately
useful). Then US2 (the gate — small, and now measurable), US3 (one doc
edit), polish. Commit after each phase or logical group (split by
concern); everything lands in the single 025 PR with the CLAUDE.md
merged-state block per the single-PR flow.
