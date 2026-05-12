# Implementation Plan: Classifier carryover — multi-turn follow-up questions stop getting rejected

**Branch**: `015-classifier-carryover` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md)
**Input**: Forward implementation. Triggered by thread `9214f7fb-e79c-4c65-8785-8cae6fa27abf` on 2026-05-11 — a structural wiring bug where the classifier (router) sees `{user_query}` + `{schema_context_block}` only, while query_understanding (the next node) additionally sees `{carryover_block}`. Two short follow-up questions (*"and what is the second one?"*, *"and the top 5?"*) were rejected as `clarification_needed` because the classifier had no prior context.

## Summary

Forward implementation, two work streams + one admin task:

1. **US1 (P1) — Carryover flows into the router.** The `router` node loads the carryover preamble into `AgentState` *before* invoking the `query_classifier` tool. The classifier's `ClassifierInput` schema gains an optional `carryover_preamble` field. The router prompt (`prompts/router.md`) gains a `{carryover_block}` placeholder + instruction text on resolving short anaphoric follow-ups against prior turns. The pre-existing isolation-ambiguous examples (*"What are the best labels?"*) are preserved.

2. **US2 (P2) — Carryover is persisted at run start.** Because the router now populates `state["carryover_preamble"]` and `state["carryover_turn_count"]` BEFORE the classifier short-circuits, the post-graph persistence path in `api_query.py:237–255` (unchanged) naturally writes the carryover into `agent_runs.metadata_json` even on `failed_clarification_needed` terminations. No persistence-layer code change required — the fix falls out of US1's earlier carryover-population.

3. **Renumbering admin (FR-013).** `013/contracts/successor-015-pointer.md` → `successor-016-pointer.md`. Same pattern 014's FR-018 established. Second renumbering of this same pointer (014 took 014; 015 takes 015).

Plus three contract amendments: amend the `query_classifier` tool contract in `004/contracts/tools.md`; amend the multi-turn carryover invariants in `005/contracts/schema-context.md` (or wherever they're normatively documented); add the new `forbidden_join` rule's analog — i.e., a new "Carryover is a router-and-understanding input" contract document under this feature's `contracts/`.

**Key implementation decision (from the Explore findings):** the cleanest shape is to **extract `_load_carryover` from `query_understanding.py` into the shared `_carryover.py` module**, then call it from BOTH router and query_understanding. `query_understanding` becomes a read-from-state consumer (DRY). This is a single small refactor that satisfies US1 + US2 + the spec's optional DRY cleanup in FR-006.

## Technical Context

**Language/Version**: Python 3.12 (existing agent runtime).
**Primary Dependencies**: existing — `pydantic`, `sqlalchemy`, `tiktoken` (already used by `_carryover.py` for token-budget cap), `pytest`. No new dependencies.
**Storage**: published DuckDB (`:ro`) + Postgres for run records. No schema changes. The `agent_runs.metadata_json` JSONB column already carries `carryover` on succeeded runs; 015 ensures it also carries it on `clarification_needed` runs.
**Testing**: pytest. Existing classifier tests use an `llm_stub` fixture (per `tests/unit/test_query_classifier.py`). New tests will follow the same pattern. The `_carryover.py` helpers already have unit tests at `tests/unit/test_carryover_builder.py` — those don't change.
**Target Platform**: Linux container (production), macOS host (dev). Implementation is pure Python stdlib + existing deps; platform-portable.
**Project Type**: agent component only (Constitution Principle VI). Touches:

- `agent/src/discogs_agent/graph/nodes/_carryover.py` — extract `_load_carryover` here as a shared helper (currently lives privately in `query_understanding.py:39–73`). FR-001 surgical site.
- `agent/src/discogs_agent/graph/nodes/router.py` — call the extracted helper before `query_classifier`; pass the preamble into `ClassifierInput`; populate `state["carryover_preamble"]` + `state["carryover_turn_count"]`. FR-001 + FR-007 surgical site.
- `agent/src/discogs_agent/graph/nodes/query_understanding.py:81` — replace the local `_load_carryover(state)` call with a read from state (`state.get("carryover_preamble")` + `state.get("carryover_turn_count")`). FR-006 (the optional DRY refactor — we'll do it). Remove the local `_load_carryover` function (lines 39–73) since it's been extracted.
- `agent/src/discogs_agent/tools/query_classifier.py` — `ClassifierInput` gains `carryover_preamble: str | None = None`; `_render_prompt` interpolates `{carryover_block}`. FR-002 surgical site.
- `agent/src/discogs_agent/prompts/router.md` — `{carryover_block}` placeholder inserted between `{schema_context_block}` and the routing instructions; new instruction text about resolving short follow-ups. FR-002 + FR-003 + FR-004 surgical site.
- `agent/tests/unit/test_query_classifier.py` — 3 new test cases (follow-up with carryover routes to simple/complex; isolation-ambiguous first-turn still routes to clarification_needed; empty carryover treats query like a first-turn). FR-009 surgical site.
- `agent/tests/unit/test_carryover_builder.py` — no change. The helper function's contract is unchanged.
- `specs/004-agent-v1/contracts/tools.md` — amend `query_classifier`'s input schema. FR-011 (via this feature's `contracts/amendment-004-tools.md`).
- `specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md` — rename to `successor-016-pointer.md` + content edits. FR-013 (via this feature's `contracts/renumbering-013-pointer.md`).

**Performance Goals**: no perf-budget change. `_load_carryover` is a single SQL query (`fetch_recent_for_thread`, indexed by `thread_id` per `agent_runs_thread_id_idx`); it now runs in the router instead of query_understanding (slight earlier in the pipeline, same cost). Token-budget cap on the preamble (4 turns / 512 tokens) is unchanged.

**Constraints**:
- `_load_carryover` MUST gracefully degrade when `current_session()` returns `None` (existing behavior — unit tests invoke nodes without a session bound). Same gracefully-degrade-to-`(None, 0)` semantics carry over.
- The classifier MUST behave identically on first-turn questions (empty carryover → same output as today). Existing tests at `test_query_classifier.py` cover this; they must continue to pass without modification.
- Constitution VII.b: the carryover is *dynamic per-run context*, not static schema prose. Adding `{carryover_block}` to `router.md` uses the legitimate placeholder channel. The instruction text about resolving follow-ups is a rule-of-thumb tied to the prompt's role.
- The carryover-load result MUST be populated into `AgentState` (`carryover_preamble` + `carryover_turn_count`) by the router so the post-graph persistence in `api_query.py:240–245` naturally surfaces it on every terminal status (including `clarification_needed`).

**Scale/Scope**: ~6 source files changed in `agent/`, 2 test modules touched (one new test set; one no-op), 3 documentation files touched (2 contract amendments + 1 renumbering). ~30 min implementation + ~30 min tests + verification.

## Constitution Check

| Principle | Engaged? | Verdict |
|-----------|----------|---------|
| I — Layered, Contract-First Data Architecture | No | No published-DuckDB schema change. |
| II — Streaming, Bounded-Memory Processing | No | Not engaged. |
| III — Reproducible Runs | Indirectly | The carryover write is deterministic per-thread (`fetch_recent_for_thread` query + token-budget trim). Re-running a thread with the same prior turns produces the same preamble. ✅ |
| IV — Data Quality Gates | No | Not engaged. |
| V — Agent-Friendly Analytics Surface | No | Not engaged. No schema-context block change. |
| VI — Two Components, One Contract | Yes | Fully inside `agent/`. Zero edits to `etl/` or `frontend/`. ✅ |
| VII.a — Configuration sources | Yes — *honored* | The token-budget cap (4 turns / 512 tokens) is sourced from `settings.THREAD_CARRYOVER_TURNS` and `settings.THREAD_CARRYOVER_TOKEN_BUDGET` (existing env-driven configuration in `_carryover.py:62–63`). 015 doesn't introduce new hardcoded literals — same plumbing, called from one new site. ✅ |
| VII.b — Prompt-authoring discipline | Yes — load-bearing | The carryover preamble is dynamic per-run context (built from prior `user_query` text). Adding `{carryover_block}` to `router.md` mirrors the existing `query_understanding.md` placeholder — the legitimate channel for dynamic context. The new instruction text about resolving short follow-ups is rule-of-thumb (VII.b carve-out for prompts' rules), not catalog-fact description. ✅ |
| VII.c — Read-only runtime mechanics (analog) | No | Not engaged. |

**Gate result**: PASS. The plan respects Principles I–VII without exception. The only nuance worth surfacing (VII.b) is load-bearing-but-clean: 015 uses the same placeholder channel as query_understanding's existing carryover plumbing, applied symmetrically to the router.

**Component(s) touched**: `agent/` only.

## Project Structure

### Documentation (this feature)

```text
specs/015-classifier-carryover/
├── spec.md                                              # Already written
├── plan.md                                              # This file
├── research.md                                          # Phase 0 — implementation choices + exact wording
├── data-model.md                                        # Phase 1 — taxonomic entities (no DB schema)
├── contracts/
│   ├── amendment-004-tools.md                           # query_classifier input schema gains carryover_preamble
│   ├── carryover-as-router-input.md                     # New contract — names carryover as a router-and-understanding input
│   └── renumbering-013-pointer.md                       # Admin: 013's successor-015-pointer → successor-016-pointer
├── checklists/
│   └── requirements.md                                  # Already written; all 14 items pass
├── quickstart.md                                        # Phase 1 — verification procedure (replay 9214f7fb + new classifier tests)
└── tasks.md                                             # Phase 2 — `/speckit-tasks` output (NOT created here)
```

### Source Code (this feature — to-be-changed)

```text
agent/src/discogs_agent/graph/nodes/_carryover.py        # Extract _load_carryover here as a public helper (FR-001 prep)
agent/src/discogs_agent/graph/nodes/router.py            # Call _load_carryover; populate state; pass to classifier (FR-001, FR-007)
agent/src/discogs_agent/graph/nodes/query_understanding.py  # Drop local _load_carryover; read carryover from state (FR-006 DRY)
agent/src/discogs_agent/tools/query_classifier.py        # ClassifierInput.carryover_preamble; render {carryover_block} (FR-002)
agent/src/discogs_agent/prompts/router.md                # New placeholder + follow-up resolution instructions (FR-003, FR-004)

agent/tests/unit/test_query_classifier.py                # 3+ new test cases (FR-009)

specs/004-agent-v1/contracts/tools.md                    # ClassifierInput contract amended (FR-011)
specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md → successor-016-pointer.md  # Rename + content (FR-013)
```

**Structure Decision**: agent-component-only forward implementation. Mirrors 014's documentation layout (contracts/ has 3 documents: one upstream amendment, one new contract-doc that doesn't have a pre-existing target, one renumbering admin). The implementation surface is small (~5 code files + 1 test module); the documentation surface carries the back-fill weight.

**One architectural decision worth surfacing inline**: `_load_carryover` is currently a private function inside `query_understanding.py` (lines 39–73). The cleanest implementation extracts it to `_carryover.py` (the existing pure-function module that already hosts `build_carryover_preamble` and the `PriorTurn` dataclass). This makes the carryover module the single load-bearing surface for both consumers (router and query_understanding). The extraction is mechanical: the existing function's body moves verbatim; only the name changes from private `_load_carryover` to a public `load_carryover_for_state` (or similar). See research.md §R2 for the naming + signature decision.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Nothing to track. Constitution Check passed with no violations. VII.b is engaged but load-bearing-and-clean — the carryover is dynamic per-run context flowing through the legitimate placeholder channel, mirroring the existing `query_understanding.md` pattern.
