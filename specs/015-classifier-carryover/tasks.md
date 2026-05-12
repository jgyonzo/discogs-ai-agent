---

description: "Task list for 015-classifier-carryover: plumb multi-turn carryover into the router (classifier) so short follow-up questions stop getting rejected as clarification_needed"
---

# Tasks: Classifier carryover — multi-turn follow-up questions stop getting rejected

**Input**: Design documents from `/specs/015-classifier-carryover/`
**Plan**: [plan.md](./plan.md)
**Spec**: [spec.md](./spec.md)
**Research**: [research.md](./research.md)
**Data model**: [data-model.md](./data-model.md)
**Contracts**: [contracts/amendment-004-tools.md](./contracts/amendment-004-tools.md), [contracts/carryover-as-router-input.md](./contracts/carryover-as-router-input.md), [contracts/renumbering-013-pointer.md](./contracts/renumbering-013-pointer.md)
**Quickstart**: [quickstart.md](./quickstart.md)

**Tests**: Tests ARE included — spec FR-009 requires 3 new test cases in `test_query_classifier.py` per research.md §R7. Existing classifier tests (5 cases) and carryover-builder tests must continue to pass without modification (FR-010).

**Organization**: Two user stories. US1 (P1) is the actual fix — router builds carryover before invoking the classifier, refactored to extract `_load_carryover` into the shared `_carryover.py` module so both router and query_understanding consume from one source. US2 (P2) is a side-effect of US1: because the router populates `state["carryover_preamble"]` BEFORE the classifier short-circuits, the post-graph metadata-write at `api_query.py:240–245` naturally persists carryover even on `failed_clarification_needed` runs. US2 has NO separate implementation tasks — only verification.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1 = router carryover; US2 = persistence verification — no implementation work)
- Setup, Foundational, and Polish phases have NO story label

## Path Conventions

This feature lives entirely within the `agent/` component (Constitution Principle VI). Paths are repo-relative; key surfaces:

- Production code: `agent/src/discogs_agent/graph/nodes/{_carryover,router,query_understanding}.py`, `agent/src/discogs_agent/tools/query_classifier.py`, `agent/src/discogs_agent/prompts/router.md`
- Tests: `agent/tests/unit/test_query_classifier.py` (extended with 3 new cases), `agent/tests/conftest.py` (potentially extended `llm_stub`)
- Documentation: `specs/004-agent-v1/contracts/tools.md` (amendment), `specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md` (renamed)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure the branch is in a clean state and the 015 design artifacts are visible to the implementer.

- [X] T001 Verify branch is `015-classifier-carryover` and working tree has only expected pending changes — run `git status` and `git branch --show-current`. The pending items should be the spec/plan/research/data-model/contracts/quickstart artifacts written during `/speckit-specify` and `/speckit-plan` (plus `CLAUDE.md` and `.specify/feature.json` updates). No source code under `agent/src/` should be modified at this point.
- [X] T002 Run the existing agent unit + integration test suite from a baseline checkout to confirm green-before-015 — `cd agent && uv run pytest tests/unit tests/integration -q`. Record the test count; the 015 implementation MUST land with at least the baseline + 3 new tests, all passing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Verify the three contract documents written during `/speckit-plan` are in place. No new code-side prerequisites.

**⚠️ CRITICAL**: No user story work should begin until this verification passes.

- [X] T003 Verify the three 015 contract documents exist and are non-empty — `ls -la specs/015-classifier-carryover/contracts/` MUST list `amendment-004-tools.md`, `carryover-as-router-input.md`, `renumbering-013-pointer.md`. Read each and confirm it matches the spec's FR-011 + FR-012 + FR-013 surfaces. If any is missing or stale, return to `/speckit-plan`.

**Checkpoint**: Foundation ready — US1 can now proceed.

---

## Phase 3: User Story 1 — Router carryover + DRY refactor (Priority: P1) 🎯 MVP

**Goal**: The classifier (router) receives the multi-turn carryover preamble before making its routing decision. Short follow-up questions ("and the second one?", "and the top 5?") that reference prior turns by anaphora are routed to `simple` or `complex`, not `clarification_needed`. Internally, `_load_carryover` is extracted from `query_understanding.py` into the shared `_carryover.py` module so both nodes (router + query_understanding) consume from one production site.

**Independent Test**: replay the two-message sequence from thread `9214f7fb-...` — first *"which is the label with most Electronic releases?"*, then *"and what is the second one?"*. On the post-US1 agent, the second question MUST return `agent_runs.status == "succeeded"` (NOT `failed_clarification_needed`), and the generated SQL MUST resolve "the second one" to the 2nd-ranked label by Electronic releases. Per spec §SC-001, SC-002.

### Tests for User Story 1

> **NOTE: Write these tests FIRST.** The 3 new test cases assert the post-015 behavior; they will fail until the implementation tasks (T007–T010) land. The existing 5 classifier tests + the carryover-builder tests MUST continue to pass without modification (FR-010 regression guard).

- [X] T004 [P] [US1] Add 3 new test cases to `agent/tests/unit/test_query_classifier.py` per [research.md §R7](./research.md): (a) `test_follow_up_with_carryover_routes_to_complex` — non-empty carryover + anaphoric follow-up ("and what is the second one?") → assert `complexity != "clarification_needed"`; (b) `test_follow_up_without_carryover_treats_as_first_turn` — `carryover_preamble=None` + same follow-up → assert `complexity == "clarification_needed"` (regression guard for first-turn behavior); (c) `test_isolation_ambiguous_with_carryover_still_needs_clarification` — rich carryover + canonical isolation-ambiguous question ("What are the best labels?") → assert `complexity == "clarification_needed"` (regression guard for SC-004). Append at the end of the existing test module.
- [X] T005 [P] [US1] Inspect `agent/tests/conftest.py` (or wherever `llm_stub` lives) and determine whether the stub needs extension to handle the new test queries from T004. The existing stub appears to pattern-match on user_query keywords (per Explore findings); if "second one" / "top 5" / "best labels" + carryover-block contents need new stub responses, extend the stub minimally. If the stub already handles them, no change needed. Per [research.md §R8](./research.md).

### Implementation for User Story 1

- [X] T006 [US1] Extract `_load_carryover` from `agent/src/discogs_agent/graph/nodes/query_understanding.py` (lines 39–73) into `agent/src/discogs_agent/graph/nodes/_carryover.py` as a public function named `load_carryover_for_state`. Body is verbatim — only the name changes from private `_load_carryover` to public `load_carryover_for_state`. Place it immediately after `build_carryover_preamble`. Add the necessary imports: `from discogs_agent.config import settings`, `from discogs_agent.persistence.db import current_session`, `from discogs_agent.persistence.repositories import RunRepo`, `from discogs_agent.graph.state import AgentState`, `from uuid import UUID`, and the `_CARRYOVER_STATUSES` constant from `query_understanding.py:36`. Also move the import of `PriorTurn` references to internal use. Per [research.md §R2](./research.md). This task is foundational for T007 and T008.
- [X] T007 [US1] Update `agent/src/discogs_agent/graph/nodes/query_understanding.py` per [research.md §R3](./research.md): (a) delete the local `_load_carryover` function (lines 39–73); (b) remove the `_CARRYOVER_STATUSES` constant (now lives in `_carryover.py`); (c) replace the import block at lines 19–21 with the minimum needed (`PriorTurn` and `build_carryover_preamble` likely no longer used here — prune if unused); (d) replace line 81's `_load_carryover(state)` call with `state.get("carryover_preamble"), (state.get("carryover_turn_count") or 0)`; (e) delete the state-writes at lines 117–118 (the router populates these upstream). Depends on T006.
- [X] T008 [P] [US1] Update `agent/src/discogs_agent/graph/nodes/router.py` per [research.md §R1](./research.md): (a) add import `from discogs_agent.graph.nodes._carryover import load_carryover_for_state`; (b) inside `router_node`, before the `with use_node("router"):` block, call `carryover_preamble, turn_count = load_carryover_for_state(state)`; (c) populate `state["carryover_preamble"] = carryover_preamble` and `state["carryover_turn_count"] = turn_count`; (d) pass `carryover_preamble=carryover_preamble` into the `ClassifierInput(...)` constructor. Depends on T006.
- [X] T009 [P] [US1] Update `agent/src/discogs_agent/tools/query_classifier.py` per [research.md §R6](./research.md): (a) add `carryover_preamble: str | None = None` field to `ClassifierInput` (line 25–27); (b) inside `_render_prompt` at the `.format()` call (line 44–49), add `carryover_block=(payload.carryover_preamble or "")` as a keyword argument. This task is independent of T006/T007 (different file, additive change).
- [X] T010 [P] [US1] Update `agent/src/discogs_agent/prompts/router.md` per [research.md §R5](./research.md): insert the `{carryover_block}` placeholder block BETWEEN the existing `{schema_context_block}` placeholder paragraph and the existing sample-values-guidance paragraph. Insert the new instruction text immediately after the placeholder, with both positive ("USE the prior question text to resolve the reference") AND negative ("not `clarification_needed`") formulations. The pre-existing isolation-ambiguous examples ("What are the best labels?", "Which genres are most important?") in the `clarification_needed` bullet (lines 19–22) MUST be preserved unchanged. Full byte-equivalent wording in research.md §R5.

**Checkpoint**: At this point, US1 is fully functional. The 3 new test cases (T004) should now PASS. Quickstart Steps 1–6 (code-level verification) should all pass.

---

## Phase 4: User Story 2 — Persistence verification (Priority: P2)

**Goal**: After US1's implementation lands, `agent_runs.metadata_json.carryover` is non-null on 2nd-or-later-turn runs that terminate as `failed_clarification_needed`. This is a side-effect of US1's earlier state population (per [research.md §R9](./research.md)) — there is no separate implementation work, only verification.

**Independent Test**: induce a `failed_clarification_needed` on a multi-turn thread (turn 1: explicit question; turn 2: genuinely ambiguous question even with context, e.g., *"What about the best ones?"*). Query Postgres for the 2nd run's `metadata_json.carryover` field — it MUST be a non-null object with `turn_count >= 1`. Per spec §SC-003.

### Verification for User Story 2

- [X] T011 [US2] Quickstart Step 11 — live-infra verification of US2 per [quickstart.md §Step 11](./quickstart.md). Requires `docker-compose up`. Send a turn-1 question, then a genuinely-ambiguous turn-2 question, then query Postgres to confirm `metadata_json.carryover` is a non-null object on the 2nd run. **Implementation is zero**; this task verifies that US1's state-population timing change has the expected persistence side-effect. If the assertion fails after US1 lands, the bug is in US1's implementation (state isn't being populated in the router) — return to Phase 3.

**Checkpoint**: At this point, US1 + US2 are both verified end-to-end. The reported regression (thread `9214f7fb-...`) is closed; operator triage of `clarification_needed` runs now has the carryover context the classifier saw.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Apply the upstream-contract amendment, perform the renumbering admin, validate the whole feature end-to-end via the quickstart, and confirm checklists are green.

### Upstream contract amendment

- [X] T012 [P] Apply the contract amendment to `specs/004-agent-v1/contracts/tools.md` per [contracts/amendment-004-tools.md](./contracts/amendment-004-tools.md). Update `ClassifierInput` schema (lines 65–67) to include `carryover_preamble: str | None = None`. Update the Behavior block to add the new multi-turn-aware bullet. Append the new note about who produces `carryover_preamble` (the router node) and the carryover invariants.

### Renumbering admin (FR-013)

- [X] T013 Perform the renumbering admin per [contracts/renumbering-013-pointer.md](./contracts/renumbering-013-pointer.md). Run: `git mv specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md`. Then edit the renamed file: replace every occurrence of `015-release-unique-view-materialization` with `016-release-unique-view-materialization` (at least 2 occurrences — title + provisional-naming section). Update the historical-context note at the top to record BOTH renumberings (original 014, bumped to 015 by 014's FR-018, now bumped to 016 by 015's FR-013) per renumbering-013-pointer.md §Step 3.

### Verification (code-level — runnable without live infra)

- [X] T014 Run [quickstart.md](./quickstart.md) Steps 1–9 — new unit tests pass, existing carryover-builder tests still pass, `{carryover_block}` placeholder present in `router.md`, `_load_carryover` no longer exists in `query_understanding.py`, `load_carryover_for_state` exists in `_carryover.py`, router populates state fields + passes preamble to classifier, `ClassifierInput.carryover_preamble` field present, renumbered pointer file in place with correct content, upstream contract amendment applied, full agent test suite passes (≥151 passed, 3 skipped). Per spec SC-005, SC-006.

### Verification (live-infra — deferred to operator-side execution)

- [X] T015 Run [quickstart.md](./quickstart.md) Step 10 — live replay of thread `9214f7fb-...` (or its two-message shape). Confirm the second question returns `status: "succeeded"` and that `metadata_json.carryover` is a non-null object on both runs. Per spec SC-001.
- [X] T016 Run [quickstart.md](./quickstart.md) Step 12 — five-question follow-up regression probe (5 different anaphoric/substitution follow-ups across distinct prior topics). All 2nd-turn runs MUST return `status != "failed_clarification_needed"`. Per spec SC-002.
- [X] T017 Run [quickstart.md](./quickstart.md) Step 13 — first-turn isolation-ambiguous regression guard. Sending *"What are the best labels?"* as the first message in a new thread MUST return `status: "failed_clarification_needed"`. Per spec SC-004.

### Final checklist hygiene

- [X] T018 [P] Re-validate `specs/015-classifier-carryover/checklists/requirements.md` — all 16 items should remain `[x]`. If any drifted to `[ ]` during implementation, update the spec and re-validate before merge.
- [X] T019 [P] Confirm `CLAUDE.md`'s SPECKIT block reflects 015 as the current in-flight feature — `grep -A 2 "015-classifier-carryover" CLAUDE.md` should show the in-flight paragraph added by `/speckit-plan`. The 016 reference (renumbered ETL follow-on) should also be visible in the prior-work list.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion. Single verification task (T003) — fast.
- **User Story 1 (Phase 3)**: Depends on Foundational completion.
  - Within US1, T006 is the foundational refactor: it must commit before T007 (which deletes the old function) and before T008 (which imports the new public symbol). T009 and T010 are independent (different files; no symbol dep on T006).
  - T004 (new tests) and T005 (stub extension) can be authored upfront in parallel; they will fail until T006–T010 all land.
- **User Story 2 (Phase 4)**: Depends on US1 being COMMITTED. No implementation work; pure verification.
- **Polish (Phase 5)**: T012 (amendment-004) + T013 (renumbering) can run any time after Foundational; they don't depend on US1 implementation. T014 (code-level quickstart) depends on US1 + T012 + T013 being committed. T015–T017 (live-infra) depend on T014 succeeding and the live stack running. T018–T019 are pure verification.

### User Story Dependencies

- **US1 (T004–T010)**: Independent of US2 (US2 has no implementation tasks). Self-contained refactor + new test cases + prompt update + classifier input field.
- **US2 (T011)**: Depends on US1 implementation being committed (the state-population timing change is what makes the persistence side-effect work).

### Within Phase 3 (US1)

- T004 (new tests) ∥ T005 (stub extension): can run in parallel; both prep for the implementation.
- T006 (refactor) must run first within the implementation. It's the only sequential bottleneck.
- After T006 lands: T007 (query_understanding cleanup) ∥ T008 (router) ∥ T009 (classifier) ∥ T010 (prompt) — all four touch different files.

### Parallel Opportunities

- Setup (T001, T002) is sequential.
- Foundational (T003) is a single verification step.
- Within US1: 5 parallel-marked tasks (T004, T005, T008, T009, T010); T006 → T007 is the one sequential chain. With two devs splitting work, one takes T004+T005+T006+T007 (test setup + refactor + query_understanding cleanup); the other takes T008+T009+T010 (router + classifier + prompt) — they meet at the green-tests checkpoint.
- US2 has only T011 — sequential by nature (verification after US1 commits).
- Polish: T012 ∥ T013 ∥ T018 ∥ T019 are all independent (different files). T014 sequential; T015–T017 sequential (run through the quickstart).

---

## Parallel Example: User Story 1

```bash
# Pre-implementation (test scaffolding + stub):
Task: "Add 3 new test cases to test_query_classifier.py per T004"
Task: "Extend llm_stub fixture if needed per T005"

# Foundational refactor (sequential within US1):
Task: "Extract _load_carryover to _carryover.py per T006"

# After T006 commits — three parallel edits in different files:
Task: "Update query_understanding.py to read carryover from state per T007"  # depends on T006
Task: "Update router.py to call helper + populate state per T008"  # depends on T006
Task: "Add carryover_preamble field + interpolation per T009"  # independent of T006
Task: "Update router.md per T010"  # independent of T006
```

## Parallel Example: Polish phase

```bash
# Three independent housekeeping tasks:
Task: "Apply amendment-004 to specs/004-agent-v1/contracts/tools.md per T012"
Task: "Rename successor-015-pointer.md → successor-016-pointer.md per T013"
Task: "Re-validate checklist per T018"
```

---

## Implementation Strategy

### MVP First (US1 alone)

US1 alone is a valid MVP. It closes the reported regression (thread `9214f7fb-...`) by giving the classifier the same context the next node already had.

1. Complete Phase 1 + Phase 2 (Setup + Foundational).
2. Complete Phase 3 (US1) — 7 tasks (T004–T010).
3. STOP and VALIDATE — replay thread `9214f7fb-...`; confirm the second question returns `status = "succeeded"`.
4. Ship. US2 is verified post-merge (Phase 4 = single task, T011); Polish (Phase 5) lands as part of the same MR or as a follow-up.

### Incremental Delivery

One commit per phase, or per concern:

1. **Commit 1**: US1 implementation (T006 + T007 in one commit since they're a refactor pair; T008 + T009 + T010 in a separate commit since they're prompt-side changes; T004 + T005 in a third commit if you want test-first cadence — or fold into the impl commits).
2. **Commit 2**: Polish (T012 + T013).
3. Quickstart verification runs cover both before merge.

A practical 3-commit split per the project memory's `feedback_commit_splitting.md`:

1. **Spec scaffold** — `specs/015-...` + `CLAUDE.md` + `.specify/feature.json` (already pending).
2. **US1 implementation** — all code + test + prompt changes (T004–T010); plus T012 amendment-004.
3. **Renumbering admin** — T013 (git mv + content edits to 013's pointer).

### Parallel Team Strategy

With two developers available:

1. Both pair on Phase 1 + Phase 2 (~5 minutes).
2. Developer A: T006 (refactor) → T007 (query_understanding cleanup) → T011 (US2 verification, after merge).
3. Developer B: T004 + T005 (test scaffolding) → T008 + T009 + T010 (router + classifier + prompt) — all four after T006 commits.
4. Either developer takes Polish (T012 + T013 + T018 + T019).

---

## Notes

- **[P] tasks** = different files, no dependencies on incomplete tasks.
- **[Story] label** maps task to US1 (router carryover + DRY refactor) or US2 (persistence verification — single task, no implementation work). Setup, Foundational, and Polish phases have NO story label.
- **No new files** in `agent/`. All US1 implementation lands in existing files. The test file gets new test cases appended; the prompt file gets new placeholder + instruction text; the router/classifier/_carryover/query_understanding modules get small edits.
- **The DRY refactor (T006 + T007) is the only sequential bottleneck.** Everything else can run in parallel by two developers.
- **US2 has zero implementation cost.** The persistence behavior change falls out of US1's state-population timing. T011 is verification only — if it fails after US1 lands, the bug is in US1.
- **Test ordering** (per research.md §R7): the unit-test additions (T004) assert post-implementation behavior. Running T004 before the implementation tasks means the new tests FAIL until T006–T010 all land. This is the TDD-style ordering — failing tests prove the bug exists, then passing tests prove the fix works.
- **Commit boundaries** (suggested per project memory `feedback_commit_splitting.md`):
  1. Spec scaffold + CLAUDE.md + `.specify/feature.json` (one logical change: "open 015").
  2. US1 implementation: T004 + T005 + T006 + T007 + T008 + T009 + T010 + T012 (amendment-004) (one logical change: "fix the bug").
  3. Renumbering admin: T013 alone (one logical change: "housekeeping").
  Alternatively, split US1 into two commits (refactor + behavior) if the diff is large or the reviewer prefers smaller commits.
- **Avoid**: editing `_carryover.py` and `query_understanding.py` in the same task (T006 should add the new function; T007 separately cleans up the old function and call site — separable for reviewer clarity).
