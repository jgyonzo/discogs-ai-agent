# Tasks: Catalog-aggregation postmortem & spec back-fill

**Input**: Design documents from `/specs/012-catalog-aggregation-postmortem/`
**Prerequisites**:
- Plan: [plan.md](./plan.md)
- Spec: [spec.md](./spec.md)
- Research: [research.md](./research.md)
- Contracts: [contracts/amendment-004-code-generation.md](./contracts/amendment-004-code-generation.md), [contracts/amendment-005-schema-context.md](./contracts/amendment-005-schema-context.md)
- Quickstart: [quickstart.md](./quickstart.md)

**Tests**: not new — the fixes are deployed and verified by manual demo testing + the existing test suite (179 passed). A synthetic-large-catalog regression test is recorded as deferred work in `spec.md` "Out-of-scope".

**Components touched**: `agent/` only (Constitution Principle VI). All implementation tasks below are **already done** as part of the hotfix commits `0ae0662` (2026-05-08) and `4143afd` (2026-05-09). The remaining tasks (T-A, T-B, T-C) are the contract amendments and spec hygiene that this back-fill commit lands.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel.
- **[Story]**: US1 (catalog-wide aggregations succeed) or US2 (failures are legibly classified).

## Path Conventions

- Agent source: `agent/src/discogs_agent/`
- Cross-feature contract amendment targets: `specs/004-agent-v1/contracts/`, `specs/005-agent-schema-context/contracts/`

---

## Phase 1: Setup

No setup tasks. The agent runtime, prompt templates, schema-context renderer, and test fixtures all exist from 004 + 005 + 006 + 007 + 008 + 009 + 010 + 011.

---

## Phase 2: Foundational

No foundational tasks.

---

## Phase 3: User Story 1 — Catalog-wide aggregations succeed without OOM (Priority: P1) 🎯 MVP

**Goal**: Q1 + Q4 + any other catalog-wide aggregation curated demo question succeeds end-to-end against the full April 2026 catalog.

**Independent Test**: Per [quickstart.md §3](./quickstart.md), submit Q1 and Q4 against the live agent. Both must return `status: "succeeded"` with a populated `chart_artifact`.

### Implementation for User Story 1 (already deployed)

- [X] T001 [US1] Add `"memory_limit": "1GB"` to the `duckdb.connect(...)` config in `agent/src/discogs_agent/prompts/code_generator.md`. **Deployed as commit `0ae0662` on 2026-05-08.** Generated code now caps DuckDB working memory at 1 GiB; allocations beyond that spill to `temp_directory` rather than triggering the cgroup OOM-killer.

- [X] T002 [US1] Mirror the `memory_limit` requirement in `agent/src/discogs_agent/prompts/repair_code.md` (the repair prompt's "Critical rules" reminder). **Deployed as commit `0ae0662`.**

- [X] T003 [US1] Update the LLM-stub canned responses in `agent/src/discogs_agent/llm/stub.py` (2 occurrences) and the golden-test helper at `agent/tests/golden/_helpers.py` to include `memory_limit=1GB` so test-stratum runs match what the live LLM emits. **Deployed as commit `0ae0662`.**

- [X] T004 [US1] Bump the agent-api `/tmp/duckdb` tmpfs to `size=6g` in `docker-compose.yml`, with a comment block explaining the why. **Deployed as commit `4143afd` on 2026-05-09.**

- [X] T005 [US1] Rewrite `_DOMAIN_GLOSSARY` entry #3 in `agent/src/discogs_agent/duckdb_layer/schema.py` to steer the LLM toward `COUNT(DISTINCT release_id) FROM release_fact GROUP BY X` and away from `release_unique_view` for catalog-wide aggregations. **Deployed as commit `4143afd`.**

- [X] T006 [US1] Update the "Critical rule" in `agent/src/discogs_agent/prompts/code_generator.md` to mirror the new glossary wording. **Deployed as commit `4143afd`.**

- [X] T007 [US1] Update the matching reminder in `agent/src/discogs_agent/prompts/repair_code.md`. **Deployed as commit `4143afd`.**

- [X] T008 [US1] Regenerate the golden snapshot at `agent/tests/integration/golden/schema_context_block.txt` so `test_rendered_block_matches_golden` matches the post-fix rendered block. **Deployed as commit `4143afd`.**

### Verification for User Story 1

- [X] T009 [US1] **Manual verification**: ran Q1 ("Show releases by decade") and Q4 ("Top countries") against the live agent post-fix. Both returned HTTP 200 with `status: "succeeded"` and a populated `chart_artifact`. Generated SQL queries `release_fact` directly with `COUNT(DISTINCT release_id) GROUP BY ...`, never `release_unique_view`. SC-001 + SC-002 + SC-003 verified.

**Checkpoint**: User Story 1 complete. The demo path is unblocked.

---

## Phase 4: User Story 2 — Failures are legibly classified, not silent (Priority: P2)

**Goal**: When a future query exhausts the sandbox's budget (currently no known repro), the failure surfaces as a catchable `OutOfMemoryException` rather than `exit_code=-9` SIGKILL.

### Verification for User Story 2

- [X] T010 [US2] No code change. The `memory_limit` from T001 transforms cgroup OOM (SIGKILL, no stderr) into DuckDB OOM (Python exception, full traceback in stderr). Verified by inspection of historical runs in the postgres `agent_tool_calls.output_json` field — `exit_code=-9` runs disappeared post-`0ae0662`.

**Checkpoint**: US2 verified by historical inspection. The legibility property holds for the next memory-aggressive query.

---

## Phase 5: Spec back-fill (this commit)

**Goal**: Restore SDD discipline that the demo-emergency hotfixes deliberately bypassed.

- [X] T-A Apply the contract amendment to `specs/004-agent-v1/contracts/code-generation.md` per [contracts/amendment-004-code-generation.md](./contracts/amendment-004-code-generation.md). Insert the verbatim §3.1.2 "Sandbox memory budget" subsection after the existing §3.1.1 "Sandbox file-size budget" (added by 007). Documents the `memory_limit=1GB` requirement, the tmpfs sizing, the disciplinary analog (Constitution VII.c memory-side counterpart), and the verification path.

- [X] T-B Apply the contract amendment to `specs/005-agent-schema-context/contracts/schema-context.md` per [contracts/amendment-005-schema-context.md](./contracts/amendment-005-schema-context.md). Replace glossary entry #3 in the example block under "## Rendered block format" with the post-012 wording (matches the deployed renderer at `agent/src/discogs_agent/duckdb_layer/schema.py` `_DOMAIN_GLOSSARY[2]`).

- [X] T-C Land this 012 spec directory + the two contract amendments in a single back-fill commit. (Implemented in this commit.)

**Checkpoint**: Spec back-fill complete. SDD discipline restored.

---

## Phase 6: Polish & deferred work

- [ ] T-D **DEFERRED**: Add a synthetic-large-catalog regression test that exposes budget pressure without requiring the full 19M-release April 2026 catalog. Out of scope for this back-fill; flagged in `spec.md` "Out-of-scope".

- [ ] T-E **DEFERRED**: ETL-side fix to `release_unique_view`'s definition (use `DISTINCT ON (release_id)` or materialize as a real table). The agent's amendments here are workarounds; the structural fix lives on the ETL side. Out of scope for 012; will be its own future spec under `001-discogs-etl/` or `013-`.

- [ ] T-F **DEFERRED**: Optional `RLIMIT_AS` in `agent/src/discogs_agent/sandbox/restrictions.py` as belt-and-suspenders. Not required after the 012 fix combo; remains a defensible addition for a future spec if a new bug class surfaces it.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 3 (US1)**: implementation tasks T001–T009 all DONE before this back-fill. Spec back-fill cannot precede them (it documents what's deployed).
- **Phase 4 (US2)**: derived from T001 (the `memory_limit` change is what creates the legibility property).
- **Phase 5 (spec back-fill)**: this commit. T-A, T-B, T-C land together.
- **Phase 6 (deferred)**: T-D / T-E / T-F are recorded for future work; not part of this commit.

### User Story Dependencies

- **US1 (P1)**: foundational. Already deployed.
- **US2 (P2)**: derived from US1; verified by inspection.

---

## Notes

- `[X]` on the implementation tasks (T001–T009) reflects already-deployed state across commits `0ae0662` and `4143afd`. This back-fill spec captures the WHY for the historical record.
- `[X]` on T-A/T-B/T-C reflects this commit's contract amendments + spec landing.
- `[ ]` on T-D/T-E/T-F reflects deferred work; not gated by this back-fill's merge.
- The constitution is NOT amended. Principles VII.b (prompt-authoring) and VII.c-analog (write-side runtime mechanics) cover the discipline. Same posture as 007/009/010/011.
- Total: 9 implementation tasks (already done) + 3 back-fill tasks (this commit) + 3 deferred = 15 tasks across 6 phases.
