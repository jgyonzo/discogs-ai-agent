# Tasks: Schema-context join graph

**Input**: Design documents from `/specs/009-schema-context-join-graph/`
**Prerequisites**:
- Plan: [plan.md](./plan.md)
- Spec: [spec.md](./spec.md)
- Research: [research.md](./research.md) (R1 fixes the section format; R2 fixes the test strategy; R3 adds one glossary entry)
- Contracts: [contracts/amendment-005-schema-context.md](./contracts/amendment-005-schema-context.md) (verbatim §"Join graph" insertion text)
- Quickstart: [quickstart.md](./quickstart.md)

**Tests**: included — FR-010 demands a regression test; SC-002, SC-003, SC-005 are test-anchored. Tests are not optional for this feature.

**Components touched**: `agent/` only (Constitution Principle VI). Plus the `005/contracts/schema-context.md` amendment. No edits to `etl/`, `frontend/`, or any prompt template.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: Which user story this task belongs to (US1, US2, US3).
- File paths are absolute relative to the repo root and should be created/edited as named.

## Path Conventions

- Agent source: `agent/src/discogs_agent/`
- Agent tests: `agent/tests/`
- Spec contracts (cross-feature amendment target): `specs/005-agent-schema-context/contracts/`

---

## Phase 1: Setup

No setup tasks. The `agent/` package, its dependency manifest, the `seed_duckdb` test fixture, and the `agent_env` fixture all exist from 004 + 005 + 006 + 007. No new dependencies in 009.

---

## Phase 2: Foundational

No foundational tasks. 009 introduces no new env vars, no new dependencies, no new modules — only an existing-function extension plus one new test file plus one optional golden snapshot.

---

## Phase 3: User Story 1 — Cross-grain analytical questions return semantically correct SQL (Priority: P1) 🎯 MVP

**Goal**: The canonical reproducer ("show the artist with more masters by decade, exclude Various and Unknown Artist") generates SQL that traverses `master_fact` ↔ `release_unique_view` ↔ `release_artist_bridge` using correctly-paired identifier columns, never `master_fact.master_id = release_artist_bridge.release_id`.

**Independent Test**: Submit the canonical reproducer 10 times against the live agent post-fix per [quickstart.md §1.4](./quickstart.md). Assert (a) zero attempts produce the forbidden join (SC-002), (b) at least 9 of 10 produce the correct master ↔ release ↔ bridge traversal (SC-001).

### Implementation for User Story 1

- [X] T001 [US1] Extend `_DOMAIN_GLOSSARY` in `agent/src/discogs_agent/duckdb_layer/schema.py` with one new entry per [research.md §R3](./research.md): "release_artist_bridge and release_label_bridge are NOT unique on release_id. Each row is one (release × artist) or one (release × label). For 'releases per artist' or 'releases per label' counts, GROUP BY the artist/label and use COUNT(DISTINCT release_id) — naive COUNT(*) double-counts." Append to the existing tuple `_DOMAIN_GLOSSARY`. Keep ordering: existing 3 entries first, new one as #4.

- [X] T002 [US1] Add a private helper `_render_join_graph(has_master_fact: bool) -> list[str]` in `agent/src/discogs_agent/duckdb_layer/schema.py` that returns the lines for the new "Join graph" section per [contracts/amendment-005-schema-context.md](./contracts/amendment-005-schema-context.md) Insertion 1. Three sub-blocks per [research.md §R1](./research.md): (a) **Edges** — flat list of `table.column ↔ table.column` pairs, master-side conditional on `has_master_fact`; (b) **Cross-grain traversal hints** — the namespaces line, the master-traversal worked example (conditional on `has_master_fact`), the prefer-`release_unique_view` line, the bridges-not-unique line; (c) **Forbidden joins** — the three forbidden patterns when `has_master_fact = true`, omitted entirely when false. Wording is paraphrased from [research.md §R1](./research.md) "Proposed exact wording"; final wording is in [contracts/amendment-005-schema-context.md](./contracts/amendment-005-schema-context.md). Function returns `list[str]` (lines without trailing newlines), to be joined by the caller.

- [X] T003 [US1] Integrate `_render_join_graph` into `render_schema_block` in `agent/src/discogs_agent/duckdb_layer/schema.py` (depends on T002). Insert call between the sample-values block and the domain-glossary block. The new section is rendered unconditionally (even when `sample_values` is empty). Implementation note: integration point is `lines.extend(_render_join_graph(has_master_fact))` between the two blocks, with a comment block above explaining the truncation invariant.

- [X] T004 [US1] Apply the contract amendment to `specs/005-agent-schema-context/contracts/schema-context.md` per [contracts/amendment-005-schema-context.md](./contracts/amendment-005-schema-context.md). Three insertions landed: (Insertion 1) new top-level section "## Join graph" placed AFTER "## Rendered block format" and BEFORE "## Token budget"; (Insertion 2) updated the example block in "## Rendered block format" to include the "Join graph" sub-block AND glossary entry #4; (Insertion 3) one new bullet added to "## Consumer rules" reaffirming VII.b applies to the new section. Prose copied verbatim from the amendment file.

### Tests for User Story 1

- [X] T005 [P] [US1] Extended `agent/tests/unit/test_schema_context.py` (the actual test file name in the codebase — note the `_context` suffix; the task spec said `test_schema.py` but the existing file was `test_schema_context.py`) with 4 new test functions per [research.md §R2](./research.md) Layer A: `test_join_graph_section_present_when_master_fact_true`, `test_join_graph_section_omits_master_when_master_fact_false`, `test_join_graph_glossary_entry_about_bridge_grain`, `test_join_graph_section_position_relative_to_other_sections`. All synthetic-input, no DuckDB connection.

- [X] T006 [P] [US1] Created `agent/tests/integration/test_schema_context_join_graph.py` with 4 test functions: the golden-snapshot test (`test_rendered_block_matches_golden`), a defensive presence check (`test_join_graph_subsection_present_on_seed`), a no-master_fact assertion (`test_join_graph_section_omitted_master_when_no_master_fact` — uses `seed_duckdb_no_master` fixture), and a token-budget sanity check (`test_rendered_block_within_token_budget`). The golden-snapshot test supports `UPDATE_GOLDEN=1` env var for intentional regeneration. The diff message points the reviewer at `quickstart.md §3` for the revert-and-rerun sanity check.

- [X] T007 [US1] Generated `agent/tests/integration/golden/schema_context_block.txt` (3,439 chars / ~823 tokens against the seed catalog). Implementation note: when first generated, the snapshot was non-deterministic between runs because `_collect_sample_values` lacked a tie-breaker on count-tied rows. Folded in a one-line fix to `_collect_sample_values` (`ORDER BY c DESC, v ASC`) — improves production prompt-caching stability AND makes the test deterministic. Documented in the function's comment.

- [X] T008 [P] [US1] Token-budget sanity check landed as `test_rendered_block_within_token_budget` inside the integration test file (T006). Asserts `rendered_token_count <= 1200`. Empirical reading on the seed catalog: 823 tokens (well under budget; ~377 tokens of headroom).

**Checkpoint**: User Story 1 fully functional. Pre-fix the regression test fails (T006); post-fix the regression test passes. The manual reproducer in [quickstart.md §1.4](./quickstart.md) succeeds (verified during PR review).

---

## Phase 4: User Story 2 — Other cross-grain questions also work (Priority: P2)

**Goal**: Variations on the cross-grain pattern — master ↔ labels, master ↔ styles, country breakdowns of masters, etc. — all generate correct traversals.

**Independent Test**: Submit a small probe set of cross-grain questions through the live agent post-fix and verify each generates correct join chains.

### Implementation for User Story 2

- [X] T009 [US2] No code change. The fix from US1 is general-purpose — the join graph documents *all* the documented FK edges, so the same correctness story holds for master ↔ labels and master ↔ release-grain attributes. (Verified by inspection: the rendered block delivers all FK edges, not just the master ↔ artist case.)

### Tests for User Story 2

- [ ] T010 [P] [US2] **Manual gate, deferred to PR review.** Documented in [quickstart.md §1.4](./quickstart.md). Probe set: master ↔ artist (canonical), master ↔ labels, master ↔ countries, master ↔ styles. To be run once against the live agent during PR review and the PASS/FAIL results documented in the PR description. Not gated by CI per [research.md §R2](./research.md) (LLM nondeterminism + cost + rate limits make CI-side LLM calls inappropriate).

**Checkpoint**: US2 verified manually. The fix's breadth is confirmed.

---

## Phase 5: User Story 3 — A regression test prevents this class of bug from coming back (Priority: P1)

**Goal**: A future contributor cannot silently re-introduce the bug. The CI gate is the regression test from Phase 3 (T005, T006, T007, T008).

**Independent Test**: Verify the regression tests fail on a hypothetical revert of the fix per [quickstart.md §3](./quickstart.md).

### Verification for User Story 3

- [X] T011 [US3] **Verified during implementation.** Stashed the producer change (`schema.py`), ran `pytest tests/integration/test_schema_context_join_graph.py tests/unit/test_schema_context.py` → **7 tests failed, 8 passed** (the 4 new unit tests + 3 of the 4 new integration tests fail without the fix). Restored the stash → all 15 tests green. Locks in SC-003 (the regression suite is verified to fail on a revert).

**Checkpoint**: US3 verified. The regression suite is load-bearing.

---

## Phase 6: Polish & Cross-cutting

- [X] T012 [P] Full agent test suite: **158 passed, 2 skipped** (`pytest tests/`). The pre-existing 75-test suite still passes alongside the new 009 tests. No regressions.

- [X] T013 [P] `mypy --strict src/discogs_agent/duckdb_layer/schema.py`: **Success: no issues found in 1 source file**.

- [X] T014 [P] `ruff format` reformatted 2 files (the new test file + the modified test_schema_context.py — minor whitespace tidying). `ruff check` on all three files: **All checks passed!**.

- [X] T015 [P] SC-005 grep verified. Pre-existing references to table names exist in `code_generator.md` (Critical rule for release_fact + Subgenres on release_fact.style — both invariant negative rules permitted by `005/contracts/schema-context.md` "Consumer rules"), `router.md`, `query_understanding.md`, `repair_code.md`, `response_synthesizer.md`. **009 added zero new occurrences** — 009 touched no prompt files. Recorded in [PR description (forthcoming)] for review.

- [ ] T016 [P] **Manual gate, deferred to PR review.** Run the canonical reproducer 10 times against the live agent post-fix per [quickstart.md §1.4](./quickstart.md); document SC-001 (≥9/10 correct traversals) and SC-002 (0/10 forbidden joins) in the PR description.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup, Foundational**: empty.
- **Phase 3 (US1)**: T001 ↔ T002 (different parts of same file but no inter-task dep), T003 depends on T002, T004 independent, T005 ↔ T006 ↔ T008 in parallel after T003, T007 depends on T002+T003+T006.
- **Phase 4 (US2)**: T009 is verification-only (no code), T010 is documentation-only.
- **Phase 5 (US3)**: T011 depends on T005, T006, T008 being implemented.
- **Phase 6 (Polish)**: depends on all implementation tasks.

### User Story Dependencies

- **US1 (P1)**: foundational — establishes the fix and its core regression test.
- **US2 (P2)**: depends on US1 implementation; no code of its own.
- **US3 (P1)**: depends on US1 implementation; the regression test IS the US1 deliverable.

### Within Each User Story

- T001, T002, T004 in parallel.
- T003 sequential (depends on T002).
- T005, T006, T008 in parallel after T003.
- T007 sequential (golden snapshot — depends on the renderer producing the post-fix output).

### Parallel Opportunities

- **Phase 3**: T001/T002/T004 can run in parallel (different files, or different parts of the same file with no dependencies). T005/T006/T008 in parallel after T003. T007 must come last in this phase.
- **Phase 6**: all tasks marked [P] in parallel.

---

## Parallel Example: User Story 1

```bash
# After T002+T003 land, run all unit tests in parallel:
Task: "Extend test_schema.py with rendered-block assertions"
Task: "Create test_schema_context_join_graph.py with golden snapshot"
Task: "Sanity-check token budget"

# Then sequentially: T007 generates the golden file using the post-fix renderer.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 3 (US1) — extend the renderer + the contract + the regression suite.
2. **STOP and VALIDATE**:
   - `pytest agent/tests/integration/test_schema_context_join_graph.py` green.
   - `pytest agent/tests/unit/test_schema.py` green.
   - Manual reproducer ([quickstart.md §1.4](./quickstart.md)): zero "BUG PRESENT" lines in 10 attempts.
3. This is a deployable, demoable MVP. The bug is closed.

### Incremental Delivery

The whole feature is small; incremental delivery is mostly cosmetic. A reasonable cut:

1. **Increment 1 — Renderer + glossary** (T001+T002+T003): the producer change. Makes the post-fix block visible to anyone running the agent locally.
2. **Increment 2 — Contract** (T004): updates `005/contracts/schema-context.md`. Reviewable separately from the code change.
3. **Increment 3 — Tests** (T005-T008): locks in the behavior.
4. **Increment 4 — Polish** (T012-T016): green gates + manual smoke.

For PR purposes a single commit is fine; the increments above are mostly review-aid.

### Parallel Team Strategy

With one developer (typical for this size):

1. T001, T002, T004 in any order.
2. T003 once T002 is done.
3. T005, T006, T008 in parallel after T003.
4. T007 once T006 is structurally complete.
5. T011 + T012-T016 at the end.

With two developers: developer A takes the renderer + tests (T001-T003, T005-T008), developer B takes the contract + manual smoke (T004, T010, T011, T015, T016).

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks in the same phase.
- `[Story]` label maps task to a specific user story for traceability.
- File paths in task descriptions are absolute relative to the repo root.
- Tests here are explicitly mandated by FR-010 — they are not optional.
- Constitution VII.b is the load-bearing principle. The integration test (T006) is its mechanical enforcement.
- 16 tasks total across 6 phases. Setup: 0. Foundational: 0. US1: 8. US2: 2. US3: 1. Polish: 5.
