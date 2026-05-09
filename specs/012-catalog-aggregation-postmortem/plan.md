# Implementation Plan: Catalog-aggregation postmortem & spec back-fill

**Branch**: `008-agent-frontend-v1` (back-fill on the active feature branch) | **Date**: 2026-05-09 | **Spec**: [spec.md](./spec.md)
**Input**: Three hotfix commits already landed on 008. This plan documents the design retroactively for SDD discipline.

## Summary

Post-implementation plan. Three fixes are already deployed:

1. `agent/src/discogs_agent/prompts/code_generator.md` — generated-code template includes `memory_limit=1GB` in `duckdb.connect(...)` config (commit `0ae0662`).
2. `docker-compose.yml` — agent-api `tmpfs` for `/tmp/duckdb` sized to `6g` (commit `4143afd`).
3. `agent/src/discogs_agent/duckdb_layer/schema.py` `_DOMAIN_GLOSSARY` entry #3 + `prompts/code_generator.md` "Critical rule" + `prompts/repair_code.md` mirror — steer LLM toward `COUNT(DISTINCT release_id) FROM release_fact GROUP BY X` and away from `release_unique_view` (commit `4143afd`).

This plan covers the contract amendments (the actual code is already in place) plus an inventory of follow-up work.

## Technical Context

**Language/Version**: Python 3.12 (existing agent runtime).
**Primary Dependencies**: existing — `duckdb`, `pydantic-settings`, `pytest`. No new dependencies.
**Storage**: published DuckDB (`:ro` mount), tmpfs at `/tmp/duckdb` (now sized 6 GiB).
**Testing**: pytest. The full agent suite (179 tests) is green post-fix; no new tests added in this back-fill (a synthetic-large-catalog regression test is recorded as deferred work in the spec).
**Target Platform**: Linux container (production), macOS host (dev). Identical behavior on both.
**Project Type**: agent component only (Constitution Principle VI). Touches:

- `specs/004-agent-v1/contracts/code-generation.md` — amended (new clause about memory_limit + tmpfs).
- `specs/005-agent-schema-context/contracts/schema-context.md` — amended (glossary entry #3 rewrite).
- (Optional follow-up) `agent/tests/integration/` — a regression test for catalog-aggregation survivability, deferred.

**Performance Goals**: curated demo questions Q1 + Q4 succeed in <15s end-to-end on the cheap-model path. Verified manually post-fix.

**Constraints**:
- The sandbox memory budget (`1 GiB` DuckDB memory_limit + `6 GiB` tmpfs) MUST be honored by every generated query. Forced via the `code_generator.md` template.
- `release_unique_view` MUST NOT be used for catalog-wide aggregations. Forced via prompt steering (glossary entry #3 + Critical rule).
- Constitution VII.b (prompt-authoring discipline) — no static schema prose was added; all steering lives in the dynamically-rendered glossary OR in invariant rules-of-thumb in the prompt (which VII.b explicitly permits).

**Scale/Scope**: ~5 files touched by the implementation (already committed). 2 contract amendments to add as part of this back-fill. ~1 page of contract markdown each.

## Constitution Check

| Principle | Engaged? | Verdict |
|-----------|----------|---------|
| I — Layered, Contract-First Data Architecture | No | No published-DuckDB schema change. The view's definition is documented as a known-deferred ETL-side issue. |
| II — Streaming, Bounded-Memory Processing | Indirectly | The bug class is exactly an unbounded-spill failure under a too-small budget. The fix lets DuckDB spill within bounded resources, restoring the principle's intent at the agent layer. ✅ |
| III — Reproducible Runs | No | Not engaged. |
| IV — Data Quality Gates | No | Not engaged. |
| V — Agent-Friendly Analytics Surface | Indirectly | The fix adds a "preferred query shape" rule for the agent — `release_fact` + `COUNT(DISTINCT release_id)` over `release_unique_view`. The published-DuckDB surface is unchanged; what changes is the agent's preferred path through it. ✅ |
| VI — Two Components, One Contract | Yes | Fully inside `agent/`. Zero edits to `etl/` or `frontend/`. ✅ |
| VII.a — Configuration sources | Yes | The `memory_limit=1GB` value is hardcoded in the prompt template. **Trade-off**: making it operator-tunable via env var would let a misconfiguration silently weaken the budget. The 1 GiB value is a safety-critical sandbox invariant; same reasoning as 007's RLIMIT_FSIZE_BYTES (which is also a hardcoded constant, not env-driven). ✅ |
| VII.b — Prompt-authoring discipline | Yes — load-bearing | The glossary entry #3 rewrite delivers the steering through the dynamically-rendered `{schema_context_block}`. The "Critical rule" line in `code_generator.md` is a rule-of-thumb (permitted by VII.b's "What prompts MAY contain" carve-out), not static schema prose. ✅ |
| VII.c — Read-only runtime mechanics | Yes — analog | This feature is the symmetric write-side analog of VII.c. It declares the constraints (DuckDB memory_limit, tmpfs cap) and documents their consequences (catalog-wide aggregations must avoid heavyweight view materialization) alongside them. The 004 amendment is the load-bearing artifact. ✅ |

**Gate result**: PASS. The spec back-fill restores SDD discipline that the demo-emergency hotfixes deliberately bypassed.

**Component(s) touched**: `agent/` only.

## Project Structure

### Documentation (this feature)

```text
specs/012-catalog-aggregation-postmortem/
├── spec.md                                              # This back-fill
├── plan.md                                              # This file
├── research.md                                          # The empirical numbers (sizing, repro)
├── contracts/
│   ├── amendment-004-code-generation.md                 # Memory_limit + tmpfs invariants
│   └── amendment-005-schema-context.md                  # Glossary entry #3 rewrite
├── checklists/
│   └── requirements.md                                  # Quality gate
├── quickstart.md                                        # How to verify the fix
└── tasks.md                                             # Already-done implementation + amendment tasks
```

### Source Code (already deployed)

```text
agent/src/discogs_agent/duckdb_layer/schema.py     # _DOMAIN_GLOSSARY entry #3 (commit 4143afd)
agent/src/discogs_agent/prompts/code_generator.md  # memory_limit + Critical rule (0ae0662 + 4143afd)
agent/src/discogs_agent/prompts/repair_code.md     # Critical rule mirror (4143afd)
agent/tests/integration/golden/schema_context_block.txt  # Regenerated golden (4143afd)
docker-compose.yml                                 # tmpfs size=6g (4143afd)
```

`specs/004-agent-v1/contracts/code-generation.md` and `specs/005-agent-schema-context/contracts/schema-context.md` are amended in this back-fill commit.

**Structure Decision**: Implementation already deployed on 008; this back-fill adds spec/plan/research/contracts/quickstart/tasks/checklist + the two contract amendments. No code change in this commit.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(Not applicable — no constitution violations.)

## Phase 0 — Research

See [`research.md`](./research.md) for the long-form. Three decisions:

1. **Why `memory_limit=1GB` (not 4GB or unbounded)**: The cap is a safety-critical sandbox invariant. The 1 GiB value lets DuckDB use enough working memory for the cheap-path query plans (steered by the prompt) while keeping the cgroup blast radius bounded. With prompt steering toward `COUNT(DISTINCT release_id) FROM release_fact`, queries fit in <100 MB of working memory; 1 GiB is generous headroom.

2. **Why tmpfs `size=6g` (not 8g or unlimited)**: The host has 7.75 GiB total RAM. tmpfs eats RAM. 6 GiB cap leaves ~1.75 GiB for the agent process, Postgres connections, Python interpreter, etc. The cap protects the host from OOM if a runaway query fills the spill dir.

3. **Why steer LLM AWAY from `release_unique_view`**: Investigation of the published DuckDB schema revealed the view is defined as `SELECT DISTINCT release_id, master_id, title, ...33 cols total... FROM release_fact`. Every query against it forces DuckDB to materialize a 19M-row × 33-col deduplicated set before any GROUP BY can stream — pathological at full-catalog scale. The cheap path is `SELECT X, COUNT(DISTINCT release_id) FROM release_fact GROUP BY X`, which only tracks per-X distinct sets.

## Phase 1 — Design & Contracts

**Prerequisites**: research.md complete (the three decisions above).

1. **Entities** — none. Skip `data-model.md`.

2. **Contracts** → two amendments:

   a. [`contracts/amendment-004-code-generation.md`](./contracts/amendment-004-code-generation.md) — adds a §3.1.2 "DuckDB connect-config invariants" clause to `004/contracts/code-generation.md` documenting the `memory_limit` + `temp_directory` requirements and a "Sandbox tmpfs sizing" subsection.

   b. [`contracts/amendment-005-schema-context.md`](./contracts/amendment-005-schema-context.md) — replaces glossary entry #3 in `005/contracts/schema-context.md`'s example block with the new wording (already in the schema.py renderer; this amendment makes the contract match the code).

3. **Quickstart** — [`quickstart.md`](./quickstart.md). Walks through verifying both curated questions (Q1, Q4) succeed end-to-end against the live stack.

4. **Agent context update** — `CLAUDE.md` SPECKIT block remains pointed at 008 (this is a back-fill, not a new active feature).

**Output of Phase 1**: two contract amendment files, quickstart, no CLAUDE.md change.

## Re-check Constitution Check after Phase 1 design

Phase 1 produces no new entities, no new APIs, no new env vars, no new dependencies. The two amendments to existing contracts in 004 and 005 are governed by Constitution VI (one contract surface owned by 004 and 005 respectively); they extend rather than override existing prose. Constitution VII.b/VII.c are operationalized correctly.

**Gate result (post-design)**: PASS. No new violations introduced.
