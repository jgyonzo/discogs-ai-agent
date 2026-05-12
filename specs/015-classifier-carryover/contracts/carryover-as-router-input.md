# Contract: Multi-turn carryover is a router-and-understanding input

**Source feature**: `015-classifier-carryover`
**Owner**: `agent/src/discogs_agent/graph/nodes/_carryover.py` (producer); `router_node` + `query_understanding_node` (consumers).
**Status**: normative.

This contract names the multi-turn carryover preamble as a cross-node input — produced once in the router (or upstream), consumed by both the router's classifier call AND query_understanding. Pre-015 the preamble was an internal detail of `query_understanding`; 015 promotes it to a graph-level input that the router needs first.

---

## Production: who builds the carryover

The carryover preamble is built by `load_carryover_for_state(state)`, a public function in `agent/src/discogs_agent/graph/nodes/_carryover.py`. The function:

1. Reads the request-scoped DB session (`current_session()`).
2. Reads `state["thread_id"]` (UUID).
3. Calls `RunRepo(session).fetch_recent_for_thread(...)` with the configured turn cap.
4. Drops the current run's row if present (avoids echoing the current question).
5. Converts ORM rows to `PriorTurn(user_query=...)` instances.
6. Calls `build_carryover_preamble(prior_turns, token_budget)` with the configured token budget.
7. Returns `(preamble_or_None, turn_count)`.

**Invariants** (preserved across 015):

- **Same-thread only.** The fetch is keyed by `thread_id`; cross-thread carryover is structurally impossible.
- **Soft enrichment.** When the DB session is absent (e.g., a unit test invoking a node without bound persistence), the function returns `(None, 0)`. Carry-over is never load-bearing — the agent still works on first turns and in test environments.
- **User-query text only.** `PriorTurn` carries only `user_query: str`. SQL, generated code, final responses, and dataframe previews are NEVER part of the preamble. This is the load-bearing invariant CLAUDE.md calls *"light contextual carry-over"*.
- **Turn cap.** Capped at `settings.THREAD_CARRYOVER_TURNS` (default 4 per CLAUDE.md). Older turns are dropped.
- **Token budget.** Capped at `settings.THREAD_CARRYOVER_TOKEN_BUDGET` (default 512 per CLAUDE.md). The newest-N turns are kept until the budget is reached.
- **Status filter.** Carryover includes runs whose status is in `("succeeded", "failed_clarification_needed")` (per existing `_CARRYOVER_STATUSES` in `query_understanding.py`). Other failure modes (validation failures, safety failures, internal errors) are excluded — the user's intent on those wasn't unambiguous either.

---

## Consumption: who reads the carryover

### Consumer 1: `router_node` (NEW in 015)

The router invokes `load_carryover_for_state(state)` BEFORE calling `query_classifier`. The result is:

1. Written into `AgentState`:
   - `state["carryover_preamble"] = preamble`
   - `state["carryover_turn_count"] = turn_count`
2. Passed into `ClassifierInput(carryover_preamble=preamble, ...)`.

The classifier's prompt (`prompts/router.md`) interpolates the preamble into the `{carryover_block}` placeholder; the LLM uses prior question text to resolve anaphoric follow-ups.

### Consumer 2: `query_understanding_node` (changed in 015)

`query_understanding` no longer calls `load_carryover_for_state` itself. Instead it reads from state:

```python
carryover_preamble = state.get("carryover_preamble")
turn_count = state.get("carryover_turn_count", 0) or 0
```

The values are guaranteed-populated by the router (or `(None, 0)` if the router's load returned that). The local `_load_carryover` function in `query_understanding.py:39–73` is deleted as part of 015 (DRY cleanup).

---

## Why one production site, two consumers

Pre-015, the carryover was built inside `query_understanding`. The router (an earlier node) had no access to it. When the classifier returned `clarification_needed`, the graph short-circuited to `response_synthesizer` and `query_understanding` never ran — so:

1. The classifier made its decision without prior context.
2. No carryover was ever built.
3. `metadata_json.carryover` persisted as `null`, indistinguishable from a true first-turn run.

The fix is to move the carryover production to the earliest node that needs it (the router) and let downstream nodes read from state. This:

- Closes the routing-bug class (FR-001 through FR-005).
- Closes the persistence-ambiguity class (FR-007, FR-008): carryover is in state before any short-circuit can happen.
- Eliminates the duplicate DB fetch (FR-006 DRY cleanup): one load, two reads.

---

## Persistence contract

`AgentState.carryover_preamble` and `AgentState.carryover_turn_count` flow into `agent_runs.metadata_json.carryover` via the post-graph metadata-write at `api_query.py:237–255`. The existing serialization logic:

```python
carryover_meta = (
    {"turn_count": carryover_turn_count, "preamble": carryover_preamble}
    if (carryover_preamble or carryover_turn_count)
    else None
)
```

is unchanged by 015. What changes is *when* the state fields get populated — pre-015 inside `query_understanding`, post-015 inside the router. This gives `clarification_needed` runs a non-null carryover automatically, with zero persistence-layer code change.

**Persistence invariant**:

- `metadata_json.carryover IS NULL` ⟺ "no prior turns to carry" (first-turn run) OR "graph never reached the router" (run-level internal error).
- `metadata_json.carryover IS NOT NULL` ⟹ "router ran AND prior turns existed AND the preamble was built." `turn_count >= 1` is guaranteed.

---

## Backward-compatibility invariants

015 does NOT change:

- The shape of `AgentState.carryover_preamble` / `carryover_turn_count` (existing fields; same types).
- The shape of `metadata_json.carryover` (existing JSON shape; same `turn_count`/`preamble` keys).
- The shape of `build_carryover_preamble` or `PriorTurn` (the pure helpers in `_carryover.py`).
- The token-budget cap or turn cap (env-driven; same defaults).
- The `query_classifier` tool's output schema (`ClassifierOutput` is unchanged).
- The cross-thread isolation guarantee.

015 adds ONE new field to `ClassifierInput` (`carryover_preamble: str | None = None`) with a default to preserve backward compatibility for any caller (test or future tool) that doesn't pass it.

---

## Constitution compliance

- **VII.b** (Prompt-authoring discipline): the carryover preamble is dynamic per-run context. Adding `{carryover_block}` to `router.md` and the supporting instruction text uses the legitimate placeholder channel + rule-of-thumb prompt content. No static schema prose is added to any prompt template.
- **VII.a** (Configuration sources): the token-budget cap (`settings.THREAD_CARRYOVER_TOKEN_BUDGET`) and turn cap (`settings.THREAD_CARRYOVER_TURNS`) remain settings-sourced. 015 doesn't introduce new hardcoded literals — the existing env-driven plumbing is called from one additional site.
- **VI** (Two Components, One Contract): producer (`_carryover.py`) and both consumers (`router`, `query_understanding`) live within `agent/`. The contract document itself (this file) lives in 015's spec directory; references to `004/contracts/tools.md` and `005/contracts/schema-context.md` are cross-spec but agent-internal.

---

## Verification

A unit test in `agent/tests/unit/test_query_classifier.py` (added by 015 per spec FR-009) exercises the contract by:

1. Calling `query_classifier(ClassifierInput(carryover_preamble="...", ...))` with a non-empty preamble + an anaphoric follow-up → asserts `complexity` is `simple` or `complex`.
2. Calling the same with `carryover_preamble=None` → asserts `complexity` is `clarification_needed` (regression guard for first-turn behavior).
3. Calling with a rich preamble + a canonical isolation-ambiguous question ("best labels") → asserts `complexity` is `clarification_needed` (regression guard that carryover doesn't override genuinely-ambiguous questions).

Together these prove the contract's behavior at the unit level. Spec §SC-001 + SC-004 cover the end-to-end verification path.

---

## Implementation pointer

Implementation lands as part of 015:

- `agent/src/discogs_agent/graph/nodes/_carryover.py` — gains `load_carryover_for_state` (extracted from `query_understanding.py`).
- `agent/src/discogs_agent/graph/nodes/router.py` — invokes the new helper before `query_classifier`; populates state; passes preamble into `ClassifierInput`.
- `agent/src/discogs_agent/graph/nodes/query_understanding.py` — drops the local `_load_carryover`; reads carryover from state.
- `agent/src/discogs_agent/tools/query_classifier.py` — `ClassifierInput.carryover_preamble`; `_render_prompt` interpolation.
- `agent/src/discogs_agent/prompts/router.md` — `{carryover_block}` placeholder + instruction text per research §R5.
- `agent/tests/unit/test_query_classifier.py` — 3 new test cases per research §R7.
- This contract document records the cross-node carryover-flow as normative.
