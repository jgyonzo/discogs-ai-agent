# Implementation Plan: Schema-context join graph

**Branch**: `009-schema-context-join-graph` | **Date**: 2026-05-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-schema-context-join-graph/spec.md`

## Summary

Extend the rendered schema-context block — the only LLM-facing surface for catalog facts per Constitution VII.b — to deliver the documented foreign-key relationships between allowlisted tables. The fix is one rendering function (`render_schema_block` in `agent/src/discogs_agent/duckdb_layer/schema.py`), one regression test, one amendment to `005/contracts/schema-context.md`, and one optional tightening of the domain glossary. No new env vars, no new dependencies, no schema changes in the published DuckDB, no changes to any prompt template.

The bug surfaced via a master ↔ artist cross-grain question. The fix is general-purpose: the join graph documents *all* the FK edges (master ↔ release, release ↔ bridges) so the same class of failure can't recur for any other cross-grain question (master ↔ labels, master ↔ styles, etc.).

## Technical Context

**Language/Version**: Python 3.12 (existing agent runtime).
**Primary Dependencies**: existing — `duckdb`, `pandas`, `pytest`, `tiktoken` (already used for the token-budget check). No new dependencies.
**Storage**: published DuckDB (`:ro` mount), no persistence schema change.
**Testing**: pytest. New test under `agent/tests/integration/`. Existing test fixtures (`seed_duckdb`, `agent_env`) remain unchanged. The new test exercises `render_schema_block` directly (deterministic) and additionally asserts on a recorded-golden snapshot of the rendered block to lock in the join-graph wording.
**Target Platform**: Linux container (production), macOS host (dev). Identical behavior on both.
**Project Type**: agent component only (Constitution Principle VI). Zero edits to `etl/` or `frontend/`. Touches:

- `agent/src/discogs_agent/duckdb_layer/schema.py` — extend `render_schema_block` with a "Join graph" section; possibly extend the domain glossary with one entry on cross-grain joins.
- `specs/005-agent-schema-context/contracts/schema-context.md` — amended (new section documenting the join-graph block; landed in the same change set).
- `agent/tests/integration/test_schema_context_join_graph.py` — new regression test.
- `agent/tests/unit/test_schema.py` (or wherever existing `render_schema_block` tests live) — extended assertions for the new section's presence in the rendered output.

**Performance Goals**: same as existing — `render_schema_block` runs once at startup and is cached. The new section adds ~150-250 tokens to the rendered block; the 1200-token budget has ~700 tokens of headroom on the full April 2026 catalog (the 005 spec sized the budget against ~487 rendered tokens). Token-budget overhead is negligible.

**Constraints**:
- The rendered block stays within `_TOKEN_BUDGET = 1200`.
- The truncation order in `_TRUNCATION_STEPS` MUST drop sample values, NOT join-graph content, if the budget is exceeded (FR-005).
- No static schema prose in any prompt template (FR-007 + Constitution VII.b).
- The fix MUST be backwards-compatible with the existing `SchemaContext` TypedDict shape — no new required fields. The producer adds the join graph inside the existing `rendered_block` string; consumers that read only `tables` / `has_master_fact` continue to work.

**Scale/Scope**: ~30-50 LOC in `schema.py` (the join-graph builder + integration into `render_schema_block`). One new test file (~80-150 LOC). One contract amendment (~50 lines of new markdown). No public API changes. No new endpoints.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Engaged? | Verdict |
|-----------|----------|---------|
| I — Layered, Contract-First Data Architecture | No | No published-DuckDB schema change. The join graph the renderer produces is *derived* from facts already in the 001/003 contracts; it doesn't define new edges. |
| II — Streaming, Bounded-Memory Processing | No | Pipeline-side principle; not engaged. |
| III — Reproducible Runs | No | Not engaged. |
| IV — Data Quality Gates | No | Not engaged. |
| V — Agent-Friendly Analytics Surface | Indirectly | The fix enforces (via the rendered block) the join rules documented in 003's "Counting / joining rules" section. It's the load-bearing follow-through that makes V's surface-stability promise actually visible to the LLM. ✅ |
| VI — Two Components, One Contract | Yes | Fully inside `agent/`. Zero edits to `etl/`, zero to `frontend/`. The published DuckDB is consumed `:ro` and unmodified. ✅ |
| VII.a — Configuration sources | No | No new env vars; the join graph is data-derived (read from `tables` and `has_master_fact`), not operator-tunable. The hardcoded edge list inside the renderer is *contract-derived*, not configuration. |
| VII.b — Prompt-authoring discipline | **Yes — load-bearing** | This feature operationalizes VII.b. It moves contract-derived join-rule guidance from spec files (which the LLM never reads) into the dynamically-rendered `{schema_context_block}` (which is the only legitimate surface per VII.b). It does NOT modify any prompt template. ✅ |
| VII.c — Read-only runtime mechanics | No | Not engaged. The DuckDB read-only mount is unchanged; the temp-directory remediation from 006 still applies. |

**Gate result**: PASS. Zero violations to record. The feature is the canonical implementation of VII.b for the master ↔ release boundary.

**Component(s) touched**: `agent/` only.

## Project Structure

### Documentation (this feature)

```text
specs/009-schema-context-join-graph/
├── spec.md                                          # Already written
├── plan.md                                          # This file
├── research.md                                      # Phase 0 — wording + test strategy
├── contracts/
│   └── amendment-005-schema-context.md              # Verbatim §"Join graph" insertion text
├── checklists/
│   └── requirements.md                              # 16/16 PASS
├── quickstart.md                                    # Manual reproducer + regression-test invocation
└── tasks.md                                         # Phase 2 output (/speckit-tasks)
```

No `data-model.md`: this feature introduces no new entities. The join graph is *derived* from the published-DuckDB schema (the entities are already documented in `001/contracts/duckdb-schema.md` and `003/contracts/duckdb-schema.md`).

### Source Code (repository root)

```text
agent/
├── src/discogs_agent/duckdb_layer/
│   └── schema.py                                    # MODIFIED — add `render_join_graph(...)` + integrate into `render_schema_block`
└── tests/
    ├── integration/
    │   └── test_schema_context_join_graph.py        # NEW — regression test
    └── unit/
        └── test_schema.py                           # MODIFIED — assertion that the new section appears
```

`specs/005-agent-schema-context/contracts/schema-context.md` is amended in the same change set — that file lives outside `agent/` but is the contract this feature is updating.

**Structure Decision**: agent-only patch + 005-contract amendment. Same shape as 007's amendment to `004/contracts/code-generation.md`. The constitution is **not** amended.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

(Not applicable — no constitution violations.)

## Phase 0 — Research

Three focused decisions. The full long-form is in [`research.md`](./research.md); the recap below is what the Constitution Check trail needs to know.

1. **Rendered block format for the join graph**: a separate "Join graph" section listed AFTER the table/grain block and the sample-values block, BEFORE the domain glossary. Format: a small list of edges in `table.column ↔ table.column` form, plus a "Cross-grain traversal hints" mini-block enumerating the master ↔ release ↔ bridge paths, plus an explicit "Forbidden joins" line. Reason: the LLM reads top-down; placing the graph adjacent to the glossary keeps relationship facts visually grouped with rule-style guidance. The wording is paraphrased verbatim from `003/contracts/duckdb-schema.md` "Counting / joining rules".

2. **Test strategy for the regression**: the integration test exercises `render_schema_block` directly (deterministic — no LLM) and asserts on (a) presence of the "Join graph" section header, (b) presence of the master ↔ release edge when `has_master_fact = true`, (c) presence of the explicit anti-pattern line, (d) absence of master-side edges when `has_master_fact = false`. This is cheap, deterministic, and CI-friendly. We do NOT call OpenAI from CI (rate limits, nondeterminism, cost); SC-001's "9 of 10 attempts" is a manual smoke-test gate during implementation, not a CI assertion. The CI assertion is "the rendered block delivers the right facts to the LLM"; the live SQL behavior follows from that.

3. **Glossary update vs. dedicated section**: a dedicated "Join graph" section (Decision 1) AND a tightened glossary entry mentioning that bridges are not unique on `release_id` (one row per artist/label per release). The glossary edit is a one-line addition; it reinforces the join graph without duplicating it.

**Output**: [`research.md`](./research.md) with the long-form decisions, the proposed exact wording for the rendered block, and the alternatives considered.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete (decisions 1–3 above resolved).

1. **Entities** — none. Skip `data-model.md`.

2. **Contracts** → one document under [`contracts/`](./contracts/):

   **[`amendment-005-schema-context.md`](./contracts/amendment-005-schema-context.md)** — the exact prose to land in `specs/005-agent-schema-context/contracts/schema-context.md`. Adds:
   - A new subsection under "Rendered block format" documenting the "Join graph" block: where it appears in the rendered output, what edges it lists, and the explicit anti-patterns it must include.
   - An update to "Consumer rules" reaffirming that the new section is subject to Constitution VII.b (no static prose duplication in prompts).
   - Backwards-compat note: `SchemaContext` TypedDict shape unchanged (no new required fields).

   No standalone "API" or "schema" contract is created; the agent's HTTP API and the published DuckDB schema are unchanged. The 005 amendment is the only contract change.

3. **Quickstart** → [`quickstart.md`](./quickstart.md). Walks through:
   - The manual reproducer ("show the artist with more masters by decade, exclude Various and Unknown Artist") against the live agent — confirms post-fix the SQL traverses correctly.
   - The regression-test invocation (`pytest agent/tests/integration/test_schema_context_join_graph.py`).
   - How to inspect the rendered block locally.
   - A short before/after comparison of the rendered block.

4. **Agent context update** → ✅ Already done: the `CLAUDE.md` SPECKIT block was updated to point at this plan immediately after the spec was written.

**Output of Phase 1**: `contracts/amendment-005-schema-context.md`, `quickstart.md`. CLAUDE.md already updated.

## Re-check Constitution Check after Phase 1 design

Phase 1 produces no new entities, no new APIs, no new env vars, no new dependencies, no new prompt files. The only artifact crossing 009's boundary is the amendment to `005/contracts/schema-context.md` — that is governed by Constitution VII.b, which the amendment satisfies by extending the canonical surface (the rendered block) rather than introducing a sidecar prose channel.

**Gate result (post-design)**: PASS. No new violations introduced.
