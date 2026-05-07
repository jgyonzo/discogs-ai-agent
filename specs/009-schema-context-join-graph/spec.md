# Feature Specification: Schema-context join graph

**Feature Branch**: `009-schema-context-join-graph`
**Created**: 2026-05-07
**Status**: Draft
**Input**: A user-reported bug: the agent generated SQL that joined `master_fact.master_id = release_artist_bridge.release_id` for the question *"show the artist with more masters by decade, exclude Various and Unknown Artist"*. Two distinct identifier namespaces, both `BIGINT`, so the join completed and produced plausible-looking but semantically wrong rows. Thread `fc1a3324-80da-465e-85ce-0359d5bd7633`.

## Overview

This is a silent-failure-class bug, structurally identical to the family addressed by `006-bugfix-postmortem` (silent failures from missing context delivered to the LLM). The agent generated a wrong SQL join because the schema context delivered to the LLM tells it *which tables exist and their grains* but does not tell it *how the tables relate to each other*. Asked a question that spans master grain and release grain, the LLM has no way to know the correct traversal path (`master_fact` → `release_unique_view` on `master_id` → `release_artist_bridge` on `release_id`) and falls back to guessing by name similarity.

The 003 contract has the correct guidance:

> **`specs/003-masters-artists/contracts/duckdb-schema.md` "Counting / joining rules"**: "Use `release_unique_view.master_id` for release-grain joins."

But Constitution VII.b ("Prompt-authoring discipline") explicitly forbids embedding schema information in static prompt prose: schema info MUST flow only through the dynamically-rendered `{schema_context_block}`. The 003 guidance never reaches the LLM — it lives in a spec file the LLM has never read.

This feature closes that gap by extending the schema-context contract (`005/contracts/schema-context.md`) and the producer (`agent/src/discogs_agent/duckdb_layer/schema.py`) to deliver, in the rendered block, the **join graph between allowlisted tables**. The fix is small (~30 LOC + a regression test) but its surface needs to be specified properly because it changes a contract that multiple consumers depend on (`router`, `query_understanding`, `code_generator`, `repair_code`, `query_classifier`, `sql_safety_checker`).

The bug's severity is high (silent wrong answers against the live published catalog); its blast radius for the fix is contained (one rendering function, one test, one contract amendment).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Cross-grain analytical questions return semantically correct SQL (Priority: P1)

A user asks the agent a question that spans master grain and release grain — for example, "show the artist with the most masters by decade, exclude Various and Unknown Artist." The agent generates SQL that joins `master_fact` to `release_artist_bridge` through `release_unique_view` (or `release_fact`) on the correct keys, returns sensible rows, and renders a chart that actually answers the question.

**Why this priority**: The whole point of the agent is "natural-language → correct analytical answer." A silent wrong-answer mode for any reasonable question is a P0 correctness bug; closing the specific class (cross-grain joins) is the necessary fix. The user's reported question is the canonical reproducer.

**Independent Test**: Submit the canonical reproducer query against the live agent. Verify the generated SQL contains `JOIN release_unique_view ... ON ... master_id = ...` (or an equivalent traversal through `release_fact`) AND a separate join on `release_id` to `release_artist_bridge`. Verify it does NOT contain a direct comparison `master_fact.master_id = release_artist_bridge.release_id`. Verify the result rows are non-empty and the chart renders.

**Acceptance Scenarios**:

1. **Given** the published catalog includes `master_fact`, **When** a user submits the canonical reproducer ("show the artist with the most masters by decade, exclude Various and Unknown Artist"), **Then** the agent's generated SQL traverses master ↔ release ↔ artist via the correct foreign-key columns (`master_fact.master_id = release_unique_view.master_id`, `release_unique_view.release_id = release_artist_bridge.release_id`, or an equivalent path through `release_fact`).
2. **Given** the same setup, **When** the user inspects the agent's generated SQL via the frontend's SQL panel, **Then** no comparison appears between `master_fact.master_id` and any `release_*_bridge.release_id` (load-bearing negative test for the bug class).
3. **Given** the same setup, **When** the agent runs the generated SQL against the published DuckDB, **Then** the resulting dataframe contains rows whose `artist_name` values exclude `'Various'` and `'Unknown Artist'` and the count of distinct masters per (decade, artist) is internally consistent with `master_fact.release_count`.

---

### User Story 2 — Other cross-grain questions also work (Priority: P2)

A user asks variations of the same shape: "what are the most prolific labels by master count," "which countries produced the most masters per decade," "which styles have the most masters." Each question requires traversing master ↔ release ↔ a release-grain bridge or denorm. The agent generates SQL with the correct traversal in all cases.

**Why this priority**: P1 closes the specific reported bug. P2 verifies the fix isn't a one-question patch — the same class of error could surface in any cross-grain question. This story locks in the breadth of the fix.

**Independent Test**: Run a small set of cross-grain probe questions through the agent. For each, confirm the generated SQL traverses tables through their documented foreign-key paths and returns non-empty results.

**Acceptance Scenarios**:

1. **Given** a master-to-label cross-grain probe question, **When** the agent generates SQL, **Then** the join chain goes `master_fact` → `release_unique_view` (or `release_fact`) → `release_label_bridge`, never `master_fact.master_id = release_label_bridge.release_id`.
2. **Given** a master-to-style cross-grain probe question (style lives on `release_fact`), **When** the agent generates SQL, **Then** it joins `master_fact` to `release_fact` on `master_id` and reads `style` from `release_fact` (not from `master_fact`, where the column doesn't exist except as `primary_style`).
3. **Given** any of the seven curated demo questions in `specs/008-agent-frontend-v1/contracts/curated-questions.md`, **When** the agent generates SQL, **Then** every cross-table join uses correctly-paired identifier columns (the regression suite from US3 below verifies this).

---

### User Story 3 — A regression test prevents this class of bug from coming back (Priority: P1)

A future contributor adds a new analytical table or modifies the schema-context renderer. The regression test catches any drift that would re-open the silent-wrong-join failure mode.

**Why this priority**: 006-bugfix-postmortem explicitly added Constitution VII.b *because* this family of failure recurs. Without a regression test that fails on the named reproducer, the next ETL change or prompt edit could silently re-introduce the same gap.

**Independent Test**: Run `pytest agent/tests/integration/test_schema_context_join_graph.py`. The test must pass on the post-fix codebase and (verified manually during implementation) fail against the pre-fix codebase.

**Acceptance Scenarios**:

1. **Given** the post-fix codebase, **When** the regression test runs, **Then** it asserts (a) `render_schema_block` output contains the documented join graph, (b) the output contains the master ↔ release traversal hint, and (c) running the canonical reproducer's intended SQL shape against a fixture catalog returns expected rows.
2. **Given** a hypothetical revert of the fix, **When** the regression test runs, **Then** it fails (verified manually during implementation by reverting the rendering change locally and re-running the test).

---

### Edge Cases

- **Catalog without `master_fact`**: When the published DuckDB has no `master_fact`, the rendered block must still be valid (no dangling references to a master ↔ release edge). The current "master_fact is NOT present in this catalog; do not reference it." line stays; the join graph section omits master edges.
- **Token budget**: The added join graph + skeletons must fit within the existing 1200-token budget for the rendered block, including catalogs with all 5 published tables. If the budget tightens, the truncation order in `_TRUNCATION_STEPS` must not drop join-graph content (which is small) before sample values (which are larger).
- **Constitution VII.b interaction**: The fix must NOT add static schema prose to any prompt template (`code_generator.md` etc). All new content lives inside the rendered block, sourced from `render_schema_block`. Reviewer-visible: the fix touches `schema.py` and contract docs; it MUST NOT touch `*.md` prompt files except the prompt files' tests (which assert the placeholder is present).
- **Repair path**: The `repair_code.md` prompt is invoked when generated code fails. The repaired code consumes the same schema-context block, so the fix automatically benefits the repair path. No additional changes there.
- **Other cross-grain questions silently broken**: The bug existed before the user reported it. There may be prior runs in the agent's persistence that produced wrong results. This feature does NOT retroactively flag those runs; it prevents future occurrences.

## Requirements *(mandatory)*

### Functional Requirements

**Schema-context block contract changes**

- **FR-001**: The rendered schema-context block (output of `render_schema_block` in `agent/src/discogs_agent/duckdb_layer/schema.py`) MUST include a "Join graph" section listing the documented foreign-key relationships between allowlisted tables.
- **FR-002**: The "Join graph" section MUST include the master ↔ release traversal explicitly when `has_master_fact = true`: that to bridge `master_fact` to `release_artist_bridge` or `release_label_bridge`, the path goes through `release_unique_view` (or `release_fact`) on `master_id` then `release_id`.
- **FR-003**: The "Join graph" section MUST include explicit anti-patterns to forbid: at minimum, "do NOT join `master_fact.master_id` directly to `release_*_bridge.release_id` — they are different identifier namespaces."
- **FR-004**: When the catalog lacks `master_fact`, the "Join graph" section MUST omit master-side edges and MUST NOT reference `master_fact`.
- **FR-005**: The rendered block MUST stay within the existing token budget (`_TOKEN_BUDGET = 1200`). If the post-fix block exceeds the budget, the truncation logic MUST drop sample values (the existing `_TRUNCATION_STEPS` content) before dropping any join-graph content.

**Contract amendments and prompt discipline**

- **FR-006**: `specs/005-agent-schema-context/contracts/schema-context.md` MUST be amended to document the join-graph section's shape, content, and consumer rules. The amendment lands in the same change set as the producer change.
- **FR-007**: NO static schema prose may be added to any prompt template file (`code_generator.md`, `query_understanding.md`, `router.md`, `repair_code.md`, `response_synthesizer.md`, or any future prompt). The fix MUST flow only through `{schema_context_block}` per Constitution VII.b.

**Behavior**

- **FR-008**: The agent's generated SQL for the canonical reproducer ("show the artist with the most masters by decade, exclude Various and Unknown Artist") MUST traverse `master_fact` → `release_unique_view` (or `release_fact`) → `release_artist_bridge` using correctly-paired identifier columns.
- **FR-009**: The agent's generated SQL MUST NOT compare `master_fact.master_id` directly to any `release_*_bridge.release_id` for the canonical reproducer or for any other cross-grain question of the same shape. This is the load-bearing negative invariant.

**Regression coverage**

- **FR-010**: An integration test MUST exist at `agent/tests/integration/test_schema_context_join_graph.py` that locks in the rendered block's join-graph content (asserts shape and key strings) and (where feasible) the agent's generated-SQL behavior on the canonical reproducer using the stub LLM backend or a recorded golden output.
- **FR-011**: The test MUST be runnable as part of the standard `pytest` invocation in CI; it MUST NOT require the published full catalog (it MAY require a small fixture catalog).

### Key Entities *(include if feature involves data)*

This feature does not introduce new data entities. It modifies the *rendering* of existing entities (the allowlisted tables documented in `001-discogs-etl/contracts/duckdb-schema.md` and `003-masters-artists/contracts/duckdb-schema.md`). The relevant edges in the join graph are:

- `release_fact.release_id` ↔ `release_artist_bridge.release_id` (release × artist grain)
- `release_fact.release_id` ↔ `release_label_bridge.release_id` (release × label grain)
- `release_fact.release_id` ↔ `release_unique_view.release_id` (note: `release_fact` may be row-multiplied by style)
- `release_fact.master_id` ↔ `master_fact.master_id` (release ↔ master)
- `release_unique_view.master_id` ↔ `master_fact.master_id` (release ↔ master, deduplicated by release)

These are facts derived from the published-DuckDB schema contracts, not new design.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The canonical reproducer query ("show the artist with the most masters by decade, exclude Various and Unknown Artist") run against the live agent generates SQL that traverses `master_fact` ↔ `release_unique_view` (or `release_fact`) ↔ `release_artist_bridge` with correctly-paired identifier columns, on at least 9 of 10 attempts (allowing a small margin for LLM nondeterminism on the cheap-model path).
- **SC-002**: 0 of 10 attempts at the canonical reproducer produce a direct comparison `master_fact.master_id = release_artist_bridge.release_id` in the generated SQL.
- **SC-003**: A new integration test (`agent/tests/integration/test_schema_context_join_graph.py`) passes on the post-fix codebase and is verified to fail when the producer change is reverted (manual sanity check during implementation).
- **SC-004**: The rendered schema-context block stays within the 1200-token budget on the full April 2026 catalog (5 published tables, full sample values). No new `schema_context_truncated_for_token_budget` warnings fire in CI's catalog-loading test.
- **SC-005**: No static schema prose appears in any prompt template file. Verifiable by grep: no occurrences of table names (`release_fact`, `release_unique_view`, `release_artist_bridge`, `release_label_bridge`, `master_fact`) inside `agent/src/discogs_agent/prompts/*.md` except inside the documented "Critical rule for `release_fact`" line in `code_generator.md` (which is permitted as an invariant negative rule per `005/contracts/schema-context.md` "Consumer rules"). Net delta: zero new occurrences.
- **SC-006**: The four other cross-grain probe questions from US2 also generate correct traversals on the live agent (no direct master_id ↔ bridge.release_id joins).

## Assumptions

- **Scope is the rendering layer.** The producer (`render_schema_block`) is the only LLM-facing surface that needs to change. The 003/001 contracts are already correct; the bug is that those contracts' join rules are not delivered to the LLM. This feature delivers them.
- **No constitution amendment.** Constitution VII.b already covers the discipline ("schema info comes ONLY via `{schema_context_block}`"); this feature is the load-bearing follow-through. The 005 contract amendment is the artifact.
- **No new agent runtime dependencies.** No new env vars, no new tables, no schema changes in the published DuckDB, no new endpoints, no new prompt files.
- **LLM nondeterminism is bounded by the join graph hint.** With explicit relationship hints in the rendered block, the cheap-model path (`gpt-4o-mini`) reliably picks the correct traversal in the >90% range; the strong-model path is essentially deterministic. SC-001's "9 of 10" allows for the cheap-model variance.
- **Same class of fixes covers labels, styles, countries, and other release-grain attributes.** The join graph is general-purpose; it documents *all* documented FK edges, not just master ↔ artist.
- **The 003 contract's master ↔ release path is the canonical traversal.** When the catalog has `master_fact`, the path through `release_unique_view.master_id` (deduped by release) is the recommended one for "count of masters per X" questions; the path through `release_fact.master_id` is acceptable but row-multiplied by style.
- **Testing strategy: assertion on rendered output + integration where feasible.** The unit-level guarantee is "the rendered block contains the join graph" (cheap, deterministic). The integration-level guarantee ("the agent generates correct SQL for the canonical reproducer") is best done with a recorded golden output or via the stub LLM backend, since calling OpenAI from CI is rate-limited and nondeterministic. The implementation phase will choose the most pragmatic shape; either is acceptable as long as both layers are covered.
- **Out of scope**: retroactive flagging of prior wrong runs; new prompt-discipline rules in the constitution; broader prompt-engineering improvements (e.g., chain-of-thought hinting, separate FK-discovery node in the graph). Those are future work if needed.

## Dependencies

- **Existing `005/contracts/schema-context.md`** — this feature amends it. Amendment shape mirrors how `007/contracts/amendment-004-code-generation.md` amends 004's code-generation contract.
- **Existing `agent/src/discogs_agent/duckdb_layer/schema.py`** — `render_schema_block` is the producer. The fix lands here.
- **Constitution VII.b (Prompt-authoring discipline)** — the load-bearing principle this feature operationalizes.
- **001 + 003 published-DuckDB contracts** — authoritative for what edges exist. This feature only renders, never invents.
- **No dependency on the 008-agent-frontend-v1 work**: that branch is not yet merged. The agent fix lands independently and merges to `main` first; the frontend work merges separately.
