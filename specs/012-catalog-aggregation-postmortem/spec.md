# Feature Specification: Catalog-aggregation postmortem & spec back-fill

**Feature Branch**: `008-agent-frontend-v1` (back-fill on the active feature branch; not its own branch)
**Created**: 2026-05-09
**Status**: Draft (post-implementation back-fill)
**Input**: Three hotfix commits landed directly on 008 over 2026-05-08/09 to unblock Demo Day. This spec retroactively documents the bugs and the fixes per project SDD discipline.

## Overview

This is a **post-mortem-shaped back-fill spec**, mirroring `006-bugfix-postmortem`. Three hotfixes were landed on `008-agent-frontend-v1` without their normal Spec Kit cycle because they surfaced as production failures during demo prep:

| Date | Commit | Symptom | Hotfix |
|------|--------|---------|--------|
| 2026-05-08 | `0ae0662` | Sandbox subprocess SIGKILL'd (`exit_code=-9`, empty stderr) on full-catalog aggregations. cgroup OOM-killer reaped the largest child of agent-api. | Add `"memory_limit": "1GB"` to the generated-code `duckdb.connect(...)` template. |
| 2026-05-09 | `4143afd` (today) | DuckDB OOMException with temp_directory filling at 3.4 GiB → then 1.7 GiB. Even with memory_limit, queries against `release_unique_view` exhausted the host-default tmpfs. | Bump tmpfs to `/tmp/duckdb:size=6g` in `docker-compose.yml`. |
| 2026-05-09 | `4143afd` (today) | Investigation revealed `release_unique_view` is defined as `SELECT DISTINCT (~33 cols) FROM release_fact`. Every query against it forces DuckDB to materialize a 19M-row × 33-col deduplicated set — pathological even for trivial GROUP BYs. | Rewrite the schema-context glossary entry #3 + the `code_generator.md` "Critical rule" + the `repair_code.md` reminder to steer the LLM toward `COUNT(DISTINCT release_id) FROM release_fact GROUP BY X` for catalog-wide aggregations. |

All three fixes are deployed and verified by manual demo testing (curated Q1 "Show releases by decade" + Q4 "Top countries" both succeed end-to-end against the full April 2026 catalog post-fix).

The fixes are entangled because they all surfaced from the same incident class — **catalog-wide aggregations exhausting DuckDB's working/spill budget**. They span two contract surfaces (`004/contracts/code-generation.md` for the connect-config and tmpfs constraints; `005/contracts/schema-context.md` for the glossary entry) and one runtime control plane (the docker-compose tmpfs entry).

This spec captures the diagnosis and the contract amendments so the next reader understands *why* each fix is in place, and the discipline doesn't drift on the next feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Catalog-wide aggregations succeed without OOM (Priority: P1)

A user submits any agent question that requires aggregating across the full Discogs catalog (counting releases by decade, by country, by format, etc.). The agent generates SQL that fits within the sandbox's memory + temp budget, executes successfully, and returns a chart artifact.

**Why this priority**: Three of the seven curated demo questions (Q1, Q3, Q4) require catalog-wide aggregations. Without these fixes, each one nondeterministically failed with either silent SIGKILL or visible OutOfMemoryException — Demo Day was blocked.

**Independent Test**: Submit Q1 "Show releases by decade as a bar chart" and Q4 "What are the top 15 countries by number of releases?" against the live agent. Both should return HTTP 200 with `status: "succeeded"` and a populated `chart_artifact`, end-to-end in <15s.

**Acceptance Scenarios**:

1. **Given** the agent stack is running with the patched configuration, **When** the user submits Q1, **Then** the response is HTTP 200, status `succeeded`, and the chart renders.
2. **Given** the same setup, **When** the user submits Q4, **Then** the response is HTTP 200, status `succeeded`, and the chart renders.
3. **Given** the same setup, **When** the user inspects the agent's generated SQL via the SQL panel, **Then** it queries `release_fact` directly (not `release_unique_view`) for catalog-wide aggregations, using `COUNT(DISTINCT release_id) GROUP BY X`.

---

### User Story 2 — Failures are legibly classified, not silent (Priority: P2)

When a query genuinely exhausts the sandbox's resources (e.g., a hypothetical query that needs >2 GiB temp even with the cheapest plan), the failure mode is observable: DuckDB raises a real `OutOfMemoryException` that the validator can extract and the response synthesizer can describe to the user. No more `exit_code=-9` with empty stderr.

**Why this priority**: P1 closes the specific reported failures. P2 ensures the fail-loud property holds for the *next* heavy query — which isn't a known repro but could occur as the catalog grows. Mirrors 006's discipline-vs-individual-bug split.

**Independent Test**: Inspect any historical run that hit memory pressure post-fix; confirm the validator output contains `exception_type: "OutOfMemoryException"` and a parseable `exception_message`, not `exit_code: -9`.

**Acceptance Scenarios**:

1. **Given** a query that legitimately exceeds 1 GiB working memory + 6 GiB temp, **When** the sandbox runs it, **Then** DuckDB raises `OutOfMemoryException` with an informative message; the validator records it; the user sees a controlled-failure response.

---

### Edge Cases

- **Catalog grows past 6 GiB temp footprint**: the same fail-loud path engages; we'd need to bump tmpfs again. The `schema_context_over_budget_after_truncation` warning would not catch it (that's about the rendered prompt, not query execution).
- **A future curated question** asks for unique-release counts that *truly* benefit from `release_unique_view` (e.g., a single-release lookup): the prompt explicitly carves out that case (`WHERE release_id = N` is fine).
- **An LLM regression** where the model picks `release_unique_view` despite the prompt: the agent's retry path engages, the LLM gets the OOM error in the repair prompt, and ideally regenerates with `release_fact`. If retries exhaust, the controlled-failure path engages (no 500).

## Requirements *(mandatory)*

### Functional Requirements

**Sandbox runtime budget**

- **FR-001**: The generated-code `duckdb.connect(...)` config MUST set `"memory_limit": "1GB"`. The cap forces DuckDB to spill rather than allocate unbounded; the spill destination is `temp_directory`.
- **FR-002**: The agent-api container's `/tmp/duckdb` tmpfs MUST be sized to at least 6 GiB. Default tmpfs (~half of host RAM) was insufficient for legitimate query plans even after the prompt steering.

**Prompt discipline for catalog-wide aggregations**

- **FR-003**: For "count releases by X" questions, the agent MUST be steered toward `SELECT X, COUNT(DISTINCT release_id) FROM release_fact GROUP BY X`. This pattern bounds DuckDB's working memory by the cardinality of `X` (typically tens to hundreds of groups), not by the catalog row count.
- **FR-004**: The agent MUST be steered AWAY from `release_unique_view` for catalog-wide aggregations. The view is defined as `SELECT DISTINCT *` over release_fact (33 cols) and forces DuckDB to materialize the entire deduplicated set on every query — pathological at full-catalog scale.
- **FR-005**: `release_unique_view` is still permitted for spot-check queries on a single release (`WHERE release_id = N`). The prompt carves out this case explicitly.

**Contracts**

- **FR-006**: `specs/004-agent-v1/contracts/code-generation.md` MUST be amended to record the `memory_limit` requirement on the generated-code connect config and the `/tmp/duckdb:size=6g` tmpfs requirement on the agent-api container.
- **FR-007**: `specs/005-agent-schema-context/contracts/schema-context.md` glossary entry #3 MUST reflect the new prompt steering. The schema-context renderer (the `_DOMAIN_GLOSSARY` tuple) is the source of truth; the contract documents what the renderer emits.

### Out-of-scope

- **Architectural fix to `release_unique_view`** in the ETL component: the view's `SELECT DISTINCT *` definition is the underlying root cause. The proper fix is on the ETL side (define the view as a materialized table, or use `DISTINCT ON (release_id)`, or simply use a LEFT JOIN of `clean_releases` with the format/genre summaries instead). This is an ETL-side bug deferred to a separate spec under `001-discogs-etl/` or a follow-up `013-` feature. It does not block the agent's V1.
- **RLIMIT_AS in the sandbox**: the OS-level address-space cap discussed in the earlier diagnosis was not implemented. With the `memory_limit` + tmpfs + prompt steering combo, the cgroup OOM-killer is no longer reached on the curated demo paths. RLIMIT_AS remains a defensible defense-in-depth addition for a future spec.
- **Regression test** for catalog-aggregation survivability: requires a fixture catalog large enough to expose budget pressure (the existing seed fixture is too small). Out of scope for this back-fill; flagged as future work.

### Key Entities *(include if feature involves data)*

This feature does not introduce new entities. It strengthens existing contracts:

- The published-DuckDB schema (`001-discogs-etl/contracts/duckdb-schema.md`) is referenced but not modified — its NULL-tolerance is what produces the data shapes that exposed the bug.
- The agent's generated-code shape (`004/contracts/code-generation.md`) gets stricter constraints on the connect config.
- The agent's schema-context glossary (`005/contracts/schema-context.md`) gets a rewritten entry #3.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Curated demo Q1 "Show releases by decade" succeeds end-to-end (HTTP 200, `status: "succeeded"`, populated `chart_artifact`) on the live agent with the full April 2026 catalog. Verified manually post-fix.
- **SC-002**: Curated demo Q4 "What are the top 15 countries by number of releases?" succeeds end-to-end. Verified manually post-fix.
- **SC-003**: The agent's generated SQL for catalog-wide aggregations queries `release_fact` directly (not `release_unique_view`). Verifiable by inspecting any successful run's `agent_tool_calls.input_json` row for the `sandbox_executor` node.
- **SC-004**: The full agent test suite remains green: `pytest tests/` → 179 passed, 2 skipped.
- **SC-005**: The schema-context block stays within `_TOKEN_BUDGET = 1600` (post-011 ceiling). Verifiable by `read_schema_context` returning `rendered_token_count <= 1600`.
- **SC-006**: No `agent_runs` row with `status: "failed_validation"` AND `validator_output.exit_code: -9` for the seven curated demo questions on the post-fix codebase. (The `exit_code=-9` mode is what the cgroup OOM-killer produces; if it appears, FR-001 + FR-002 are insufficient and we need RLIMIT_AS.)

## Assumptions

- **The fixes are landed on `008-agent-frontend-v1`**, not main. They merge to main as part of 008's eventual MR.
- **No constitution amendment.** Constitution VII.b (prompt-authoring discipline) and VII.c (read-only runtime mechanics) are the disciplinary analogs. The prompt-steering work operationalizes VII.b for the SQL-shape side. The memory_limit + tmpfs work is the symmetric write-side analog of VII.c (006/007 established the read-side). Both already-existing principles cover this; no new principle needed.
- **The ETL-side root cause is a known-deferred problem.** The 31.7M-row × 33-col `SELECT DISTINCT *` view definition is the underlying issue. The agent's contract amendments here are workarounds; the structural fix lives on the ETL side and is captured as out-of-scope above.
- **Demo timing.** The fixes were applied directly on 008 because the demo was imminent. The proper SDD discipline (branch off main per fix → spec → implement → merge) was deliberately skipped under time pressure. This back-fill spec restores the discipline post-hoc; the next feature should resume the normal cycle.
- **The prompt's flip-flop is part of the record.** During the cascade, the LLM was briefly told to PREFER `release_unique_view` (wrong) before being corrected to AVOID it. The intermediate state is not preserved as its own change; the final state (avoid the view for aggregations) is what landed.

## Dependencies

- **`004/contracts/code-generation.md`** — amended (new clause about memory_limit + tmpfs).
- **`005/contracts/schema-context.md`** — amended (glossary entry #3 rewritten; the existing renderer is already in sync via 4143afd).
- **Constitution VII.b + VII.c** — disciplinary analogs; no amendment.
- **`007-sandbox-fsize-budget/`** — same fix family (sandbox resource budget). 012 extends 007's discipline to memory + temp.
- **`009-schema-context-join-graph/`** — same fix family (prompt steering via schema-context). 012 extends 009's discipline to query-shape preferences.
- **`011-token-budget-recalibration/`** — sibling calibration adjustment.
- **No dependency on `010-jsonb-nan-sanitization/`** — orthogonal (010 is the persistence-write boundary; 012 is the sandbox-runtime boundary).
