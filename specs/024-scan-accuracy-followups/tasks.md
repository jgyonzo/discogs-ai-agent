# Tasks: Scan Accuracy Follow-ups (Eval-Driven)

**Input**: Design documents from `/specs/024-scan-accuracy-followups/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R7), data-model.md, contracts/ (4 amendments), quickstart.md

**Tests**: Included — spec FR-016 mandates offline coverage of every new
rule; the suite stays 100% offline (022/023 discipline).

**Organization**: By user story. US1 = exact-catno re-rank (P1), US2 =
evidence in eval results (P2), US3 = same-master metric (P3). Paths repo-relative.

## Phase 1: Setup

- [X] T001 Add `scan_catno_search_depth: int` (default 50, alias `COLLECTION_AGENT_SCAN_CATNO_SEARCH_DEPTH`, VII(a) comment) in `collection-agent/src/collection_agent/settings.py`
- [X] T002 [P] Add `master_id: int | None = None` kwarg to `search_result(...)` in `collection-agent/tests/fixtures/discogs_payloads.py` (absent by default so verbatim-absent stays exercised)

---

## Phase 2: Foundational

- [X] T003 Add `master_id: int | None = None` to `Candidate` (verbatim optional; 019 comment) in `collection-agent/src/collection_agent/scan/models.py` and carry it in `_candidate_from_result` in `collection-agent/src/collection_agent/scan/search.py` (`result.get("master_id") or None` — 0/absent ⇒ None per data-model)
- [X] T004 [P] Unit tests for Candidate `master_id` verbatim/absent/zero handling in `collection-agent/tests/unit/test_scan_models.py`

**Checkpoint**: candidate payload ready — all three stories can proceed.

---

## Phase 3: User Story 1 — Exact-catno re-rank (P1) 🎯 MVP

**Goal**: exact normalized catno matches surface first on the catno rung; deeper single-page fetch; everything else byte-identical (spec FR-001..006).

**Independent Test**: scripted search page with the exact match at source position ~20 among longer prefix-neighbors → served list has it first, capped, `more_matches` honest; no-exact-match and non-catno rungs unchanged.

- [X] T005 [US1] Add `normalize_catno(s) -> str` (strip spaces/hyphens/dots/slashes/underscores + casefold) and `_is_exact_catno(result, searched) -> bool` (any comma-joined part of `result["catno"]` normalizes equal; no catno ⇒ False) in `collection-agent/src/collection_agent/scan/search.py`
- [X] T006 [US1] Catno-rung depth + stable partition in `collection-agent/src/collection_agent/scan/search.py`: `_run_search` gains per-rung awareness — catno rung fetches `per_page = max(settings.scan_catno_search_depth, settings.scan_candidates_max)`, stable-partitions RAW results (exact first, source order within groups) before the existing dedup/cap/verbatim build (research R1); all other rungs and `find_candidates_text` byte-identical; `more_matches` still from `pagination.items` vs served count
- [X] T007 [P] [US1] Re-rank unit tests in `collection-agent/tests/unit/test_scan_search.py`: SUB 15 replay (exact at source pos ~20 of 40 `SUB 15x` neighbors → served pos 1, cap respected) · multiple exacts keep source order ahead of non-exacts · separator/case-insensitive equality (`SUB 15`≡`sub-15`≡`SUB15`, `SUB 150`≢`SUB 15`) · multi-catno comma-joined any-match · no-catno never exact · no-exact-match page byte-identical to pre-024 order · non-catno rungs and manual search still fetch `per_page = scan_candidates_max` · `more_matches` true-total honesty at depth
- [X] T008 [US1] Update any existing tests asserting catno-rung `per_page` internals (only where SC-006 allows) in `collection-agent/tests/unit/test_scan_search.py` / `collection-agent/tests/integration/test_scan_server.py`

**Checkpoint**: live scan page + eval both re-rank; US1 shippable alone.

---

## Phase 4: User Story 2 — Evidence in eval results (P2)

**Goal**: every evaluated result record carries the journal-shaped compact evidence dump (spec FR-007/008).

**Independent Test**: harness run with stubbed vision → record's `evidence` equals `compact_dump()`; empty extraction ⇒ omitted; unlabeled ⇒ absent; 023-format files still parse.

- [X] T009 [US2] Add `evidence: dict | None = None` to `EvalResult` in `collection-agent/src/collection_agent/eval/scoring.py`; populate it in `evaluate_item` (`collection-agent/src/collection_agent/eval/harness.py`) with `evidence.compact_dump() or None` right after extraction — carried on hit/miss/no_evidence AND post-vision `discogs_error` records; absent on unlabeled and pre-vision errors (research R5)
- [X] T010 [P] [US2] Tests: unit (`collection-agent/tests/unit/test_eval_scoring.py`) — 023-format record without `evidence` validates (FR-008); integration (`collection-agent/tests/integration/test_eval_harness.py`) — record `evidence` matches the stubbed extraction's compact dump · `no_evidence` record omits it · unlabeled record omits it · invariant 10 (every `vision_calls ≥ 1` non-empty-extraction record carries evidence)

**Checkpoint**: zero-candidate misses diagnosable from results.jsonl alone.

---

## Phase 5: User Story 3 — Same-master near-miss metric (P3)

**Goal**: manifest master ids (+ backfill), miss classification, practical rate with invariants 8–9 (spec FR-009..014).

**Independent Test**: manifest with truth master + scripted same-master candidate → miss classified `same_master`, summary practical rate correct; unknown-master paths never guess; backfill supersedes via newest-line-wins.

- [X] T011 [US3] `ManifestRelease.master_id: int | None = None` (0/absent ⇒ None) + record it in `_process_release` from the fetched payload; add `newest_release_lines(entries) -> dict[int, ManifestRelease]` and rebase `done_release_ids` on it (newest-line-wins, amendment-023-eval-dataset delta 2) in `collection-agent/src/collection_agent/eval/dataset.py`
- [X] T012 [US3] `backfill_masters(client, settings, limit=None, on_progress=None) -> dict` in `collection-agent/src/collection_agent/eval/dataset.py`: done releases whose newest line lacks `master_id` → `get_release` (metadata only, NO downloads) → append newest-line copy with `master_id` + refreshed `fetched_at`; failures/404 counted + skipped, nothing appended; appends its own `run_header`; stats `backfilled`/`backfill_failed`/`already_have_master`
- [X] T013 [US3] Wire `--backfill-masters` flag on the `eval-dataset` subcommand (mutually usable with `--limit`; distinct summary table) in `collection-agent/src/collection_agent/cli.py`
- [X] T014 [US3] Sources: consume `newest_release_lines` (dedup) and thread `truth_master_id` onto `EvalItem` (discogs source; retained source always `None`) in `collection-agent/src/collection_agent/eval/sources.py`; add `truth_master_id: int | None = None` to `EvalItem` in `collection-agent/src/collection_agent/eval/scoring.py`
- [X] T015 [US3] Classification + summary in `collection-agent/src/collection_agent/eval/scoring.py`: `score_search_outcome` gains `truth_master_id` + candidate master ids → `miss_master_relation` (`same_master`/`different`/`unknown` per research R6) on `EvalResult`; `EvalSummary` gains `misses_same_master`/`misses_different`/`misses_master_unknown`/`practical_rate`; `summarize` computes them (invariants 8–9); harness (`collection-agent/src/collection_agent/eval/harness.py`) threads candidate master ids through
- [X] T016 [US3] Show practical rate + miss split in `_print_eval_summary` in `collection-agent/src/collection_agent/cli.py` (strict rate stays the headline row)
- [X] T017 [P] [US3] Dataset unit tests in `collection-agent/tests/unit/test_eval_dataset.py`: build records `master_id` (and omits it when payload lacks one/is 0) · `newest_release_lines` picks the last line (failed→downloaded, downloaded→backfilled) · backfill appends superseding line with images verbatim + refreshed `fetched_at` · backfill 404 counted, old line intact · backfill skips releases already carrying masters · `done_release_ids` equivalence on newest-line rule
- [X] T018 [P] [US3] Sources/scoring unit tests in `collection-agent/tests/unit/test_eval_sources.py` + `collection-agent/tests/unit/test_eval_scoring.py`: duplicate release lines yield each image once (newest line) · `truth_master_id` threaded (discogs) / always None (retained) · classification matrix: same_master, different, unknown (truth master None; candidates without master ids; zero candidates) · invariants 8–9 incl. equality-iff-zero-near-misses and null-denominator cases
- [X] T019 [US3] Integration in `collection-agent/tests/integration/test_eval_harness.py`: end-to-end run over a manifest with masters + a scripted same-master miss → record `miss_master_relation == "same_master"`, summary practical > strict by exactly that share; 023-format manifest (no masters) run classifies misses `unknown` and practical == strict... plus `unknown` bucket populated

**Checkpoint**: strict + practical rates reported; all invariants pinned.

---

## Phase 6: Polish & Cross-Cutting

- [X] T020 [P] Update `collection-agent/README.md`: catno re-rank note in the scan section, `COLLECTION_AGENT_SCAN_CATNO_SEARCH_DEPTH` env row, `--backfill-masters` + practical-rate notes in the eval section
- [X] T021 [P] Cross-check spec/plan/contracts/data-model/quickstart naming + invariant numbering; fix drift in `specs/024-scan-accuracy-followups/`
- [X] T022 Full offline gate: `cd collection-agent && pytest` green (410 + new), zero live calls, secrets audit still exactly 3 sites, eval AST read-only guard still passes over the grown `eval/`

---

## Dependencies & Execution Order

- Setup (T001–T002) → Foundational (T003–T004) → stories.
- **US1 (T005–T008)**: needs T001 (+T002 for tests). Internally T005 → T006 → T007/T008.
- **US2 (T009–T010)**: independent of US1/US3 (needs nothing beyond Phase 1); safe anytime after setup.
- **US3 (T011–T019)**: needs T002/T003 (candidate master ids). T011 → T012 → T013; T014 → T015 → T016; tests after their modules. Shares `scoring.py`/`harness.py` with US2 → schedule after US2 to avoid file contention.
- Polish last; T020/T021 parallel; T022 final gate.

## Parallel Opportunities

- T002 ∥ T001 · T004 ∥ (US1 start) · T007 test-writing ∥ T008 · T010 ∥ US3 start (different files? shares scoring.py — sequence) · T017 ∥ T018 · T020 ∥ T021

## Implementation Strategy

MVP = US1 (the pipeline fix — converts measured misses for every future scan).
US2 is a two-line observability win; US3 completes the honesty metric. Each
checkpoint is independently shippable; T022 gates the PR.
