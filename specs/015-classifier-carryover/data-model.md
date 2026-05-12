# Data Model: 015-classifier-carryover

**Date**: 2026-05-11
**Scope**: this feature is *plumbing-only*. No new database tables, columns, or persisted entities; no new domain concepts. The artifacts that change are (a) runtime state-field populations and their timing, (b) one tool-input schema field, (c) one prompt placeholder, (d) one shared helper function location. This document enumerates each artifact and its before/after shape — read it as a glossary of state shapes, not a database schema.

---

## Entity 1: `AgentState.carryover_preamble` and `AgentState.carryover_turn_count`

**Location**: `agent/src/discogs_agent/graph/state.py:23-24`. Existing fields, not new.

**Type**:
- `carryover_preamble: str | None` — the rendered preamble string, or `None` on first turn.
- `carryover_turn_count: int` — count of prior turns the preamble includes (0 on first turn).

**Pre-015 population timing**:
- Set inside `query_understanding_node` at `query_understanding.py:117–118`, AFTER the classifier ran.
- On `clarification_needed` runs, query_understanding never ran → these fields stayed at their default-`None`/`0` values → `metadata_json.carryover` persisted as `null`.

**Post-015 population timing**:
- Set inside `router_node` at the new call site, BEFORE the classifier runs.
- On `clarification_needed` runs, the router populated the state before short-circuiting → `metadata_json.carryover` persists as a non-null object on 2nd-or-later turns.
- The `query_understanding` write to these fields is removed (state is already populated upstream by the router).

**Invariant (preserved across 015)**: the rendered preamble is built from the same-thread prior `user_query` text only — never SQL, generated code, or final_response. Capped at 4 turns / 512 tokens per `settings.THREAD_CARRYOVER_TURNS` and `settings.THREAD_CARRYOVER_TOKEN_BUDGET`. This invariant is enforced inside `build_carryover_preamble` (existing); 015 doesn't touch it.

---

## Entity 2: `ClassifierInput.carryover_preamble` (NEW field)

**Location**: `agent/src/discogs_agent/tools/query_classifier.py:25-27` — the existing `ClassifierInput` pydantic model.

**Type** (post-015):
- `carryover_preamble: str | None = None` — Pydantic field with default `None` for backward compatibility (per research §R6).

**Producer**: the router node, passing `state["carryover_preamble"]` (post-015 populated) into `ClassifierInput`.

**Consumer**: `_render_prompt` in `query_classifier.py:36-53`, interpolating `(payload.carryover_preamble or "")` into the `{carryover_block}` placeholder of `router.md`.

**Backward-compat invariant**: existing callers that don't pass `carryover_preamble` get `None` by default. The prompt-render path defensively converts `None` → `""`. Pre-015 callers (e.g., the 4 existing classifier tests) continue to work without modification.

---

## Entity 3: `{carryover_block}` placeholder in `router.md`

**Location**: `agent/src/discogs_agent/prompts/router.md`. New placeholder + surrounding instruction text.

**Type**: prompt-template string. Mirrors the existing `{carryover_block}` placeholder in `query_understanding.md` (the only other prompt that already uses this placeholder name).

**Pre-015**: placeholder does not exist. Router prompt has only `{schema_context_block}` and `{user_query}` (plus `{cheap_model}` / `{strong_model}` for the JSON-format instruction).

**Post-015**: placeholder is inserted between `{schema_context_block}` and the sample-values-guidance paragraph. The exact placement + instruction text is pinned by research.md §R5.

**Render shape**:
- Non-empty preamble: text of the form `"Recent conversation (prior user questions in this thread, oldest first):\n  1. <user_query_1>\n  2. <user_query_2>\n..."` (same shape as query_understanding sees).
- Empty preamble (first turn): empty string `""`. The "Recent conversation context" heading still renders, with no body below. Acceptable per research §R5.

---

## Entity 4: `load_carryover_for_state` helper (EXTRACTED + RENAMED)

**Pre-015 location**: `agent/src/discogs_agent/graph/nodes/query_understanding.py:39-73`. Private function `_load_carryover`, scoped to that one module.

**Post-015 location**: `agent/src/discogs_agent/graph/nodes/_carryover.py`. Public function `load_carryover_for_state`, importable from both `router.py` and `query_understanding.py`.

**Signature** (unchanged from the pre-extraction version):

```python
def load_carryover_for_state(state: AgentState) -> tuple[str | None, int]:
    """Pull prior runs for this thread and build the preamble.

    Returns (preamble_or_None, turn_count). Soft-degrades to
    (None, 0) when no session is bound or thread_id is missing —
    carry-over is never load-bearing.
    """
```

**Producer**: invoked by `router_node` per research §R1. Reads from `agent_runs` table via `RunRepo.fetch_recent_for_thread` (existing).

**Consumer**: the router populates `state["carryover_preamble"]` + `state["carryover_turn_count"]` from the return value. `query_understanding` then reads those state fields (no longer calls the helper).

**Module placement rationale**: `_carryover.py` already hosts `build_carryover_preamble` + `PriorTurn` + the token-budget logic. Adding the DB-fetching helper here makes the module the single load-bearing surface for the carryover pipeline. The underscore prefix on the module name signals "package-internal," but the public functions inside (no underscore) are stable symbols for cross-node import.

---

## Entity 5: `agent_runs.metadata_json.carryover`

**Location**: existing Postgres JSONB column on `agent_runs`. JSON key is `carryover`. Shape is unchanged by 015.

**Pre-015 observed values**:
- First turn of a thread: `null`.
- 2nd+ turn, `status = succeeded` (or `succeeded_empty`): `{"turn_count": N, "preamble": "Recent conversation ..."}`.
- **2nd+ turn, `status = failed_clarification_needed`**: `null` (bug — the classifier short-circuited before the state-write at `query_understanding.py:117–118`).
- 2nd+ turn, other failed statuses: depends on where the run terminated; typically `null` if it failed before query_understanding ran.

**Post-015 observed values**:
- First turn of a thread: `null` (unchanged — per research §R4, the decision is to keep null for first turn).
- 2nd+ turn, any non-internal-error terminal status: `{"turn_count": N >= 1, "preamble": "Recent conversation ..."}` (NEW — `failed_clarification_needed` runs now also have non-null carryover, because the router populated state before short-circuiting).
- Run-level internal errors that terminate before the router runs: still `null` (the router never ran → state was never populated).

**Distinguishability invariant (FR-008)**: `null` ⟺ "no prior turns" OR "graph never reached the router." Any non-null object ⟺ "had prior turns AND the router ran." For operator triage, `null` on a 2nd-or-later turn is now a meaningful signal: it specifically means "the run was killed before the router (e.g., internal error in the entry point)," not "the classifier short-circuited."

---

## Entity 6: Renumbered ETL pointer document

**Location**: `specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md` (pre-015) → `successor-016-pointer.md` (post-015).

**Type**: Markdown document. Filename + content change.

**Filename invariant**: matches the referenced provisional spec number. Pre-013, `014`; pre-014, `015`; pre-015, `016` (this round).

**Content change** per research §R10: every `015-release-unique-view-materialization` → `016-release-unique-view-materialization`. The historical-context note at the top grows to record both renumberings.

---

## What is explicitly NOT a data-model entity in 015

For clarity:

- **No new database tables** — Postgres is untouched. No migration.
- **No new columns** — `agent_runs`, `agent_tool_calls`, `agent_model_usage` shapes are unchanged.
- **No new DuckDB tables/views** — the published DuckDB contract is untouched.
- **No new LangGraph state keys** — `AgentState.carryover_preamble` and `carryover_turn_count` already existed; 015 only changes their population timing.
- **No new prompt template** — `router.md` is amended, not replaced. `query_understanding.md` is unchanged.
- **No new tool** — `query_classifier` is amended (one new input field), not split.

---

## Validation rules from spec requirements

| Spec FR | Validation rule | Entity affected |
|---------|----------------|-----------------|
| FR-001 | `load_carryover_for_state(state)` is invoked in `router_node` BEFORE `query_classifier(...)`; state fields are populated before the classifier call | Entity 1, Entity 4 |
| FR-002 | `router.md` contains the `{carryover_block}` placeholder; `_render_prompt` interpolates it | Entity 3 |
| FR-003 | `router.md` contains instruction text directing the classifier on follow-up resolution | Entity 3 |
| FR-004 | `router.md` preserves the pre-existing isolation-ambiguous examples for `clarification_needed` | Entity 3 |
| FR-006 | `query_understanding.py` reads carryover from state, not from a local `_load_carryover` call (the local function is deleted) | Entity 1, Entity 4 |
| FR-007 | `metadata_json.carryover` is populated on `clarification_needed` runs on 2nd-or-later turns | Entity 5 |
| FR-008 | `metadata_json.carryover` distinguishes "first turn" (null) from "2nd+ turn with prior context" (object with turn_count ≥ 1) | Entity 5 |
| FR-013 | Renamed pointer file exists; old path does not | Entity 6 |

---

## State transitions

The only "state transition" relevant to this feature is the lifecycle of a single agent run where the classifier (now informed by carryover) routes a follow-up correctly:

```text
api_query.py creates run row (metadata_json = {}) →
api_query.py initializes AgentState with thread_id, user_query, schema_context →
router_node:
  load_carryover_for_state(state) → (preamble, turn_count)
  state["carryover_preamble"] = preamble    # NEW in 015
  state["carryover_turn_count"] = turn_count # NEW in 015
  query_classifier(ClassifierInput(
      user_query=state["user_query"],
      schema_context=state["schema_context"],
      carryover_preamble=preamble,           # NEW in 015
  )) →
  classifier's _render_prompt interpolates {carryover_block} →
  LLM sees prior turns → routes follow-up to simple/complex →
  state["route"] = {complexity: "complex", selected_model: "gpt-4o", rationale: "..."}
router_edge → "query_understanding" (NOT "response_synthesizer")
query_understanding_node:
  preamble = state.get("carryover_preamble")  # read, not call helper
  turn_count = state.get("carryover_turn_count", 0)
  (rest of query_understanding logic unchanged)
…
sandbox_executor / chart_validator / response_synthesizer …
api_query.py post-graph metadata write:
  carryover_meta = {"turn_count": turn_count, "preamble": preamble} (now non-null on 2nd+ turn) →
  run_repo.update_metadata(run_id, carryover=carryover_meta, …)
```

The clarification-needed branch (which was the bug case pre-015) now also benefits: even if `router_edge` returns `"response_synthesizer"` (the short-circuit path), `state["carryover_preamble"]` and `state["carryover_turn_count"]` were populated before the short-circuit, so the post-graph metadata write captures them. **The bug case becomes self-documenting** — operators see what context the classifier had when it decided to clarify.

No other state transitions are introduced or modified.
