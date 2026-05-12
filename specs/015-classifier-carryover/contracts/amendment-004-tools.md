# Amendment to `004/contracts/tools.md` — `ClassifierInput` gains `carryover_preamble`

**Source feature**: `015-classifier-carryover`
**Target file**: `specs/004-agent-v1/contracts/tools.md` §2.2 `query_classifier`
**Predecessor**: 004-agent-v1 (defined the original `ClassifierInput` schema).

This amendment records the new optional `carryover_preamble` field on `ClassifierInput`. The classifier now receives the same multi-turn carryover preamble that `query_understanding` already receives; this closes the structural bug where short follow-up questions were rejected as `clarification_needed` despite being unambiguous in conversation context.

---

## §2.2 — replacement schema

The current `query_classifier` schema in `004/contracts/tools.md` (around lines 62–73) reads:

```python
class ClassifierInput(BaseModel):
    user_query: str
    schema_context: SchemaReaderOutput

class ClassifierOutput(BaseModel):
    complexity: Literal["simple", "complex", "unsupported", "clarification_needed"]
    selected_model: str | None              # null for unsupported / clarification_needed
    rationale: str
```

Replace `ClassifierInput` with:

```python
class ClassifierInput(BaseModel):
    user_query: str
    schema_context: SchemaReaderOutput
    carryover_preamble: str | None = None  # ← Added 2026-05-11 by 015
```

`ClassifierOutput` is unchanged.

---

## §2.2 — replacement Behavior section

The current Behavior block reads:

```markdown
**Behavior**:
- Wraps the cheap-tier LLM with the `router.md` prompt.
- The LLM returns JSON; the tool validates against
  `ClassifierOutput`.
- Schema-aware: if the query references a column/concept not
  in the allowlist, the classifier MUST return `unsupported`.
```

Replace with:

```markdown
**Behavior**:
- Wraps the cheap-tier LLM with the `router.md` prompt.
- The LLM returns JSON; the tool validates against
  `ClassifierOutput`.
- Schema-aware: if the query references a column/concept not
  in the allowlist, the classifier MUST return `unsupported`.
- **Multi-turn-aware (added 015)**: when `carryover_preamble` is
  non-null, the classifier MUST use the prior question text to
  resolve short anaphoric follow-ups (e.g., "and the next one?",
  "and the top 5?", "same but for X", "what about Y instead?").
  In that case the classifier returns `simple` or `complex`, NOT
  `clarification_needed`. When `carryover_preamble` is `None` or
  the empty string, the classifier MUST behave identically to
  the pre-015 baseline — genuinely isolation-ambiguous questions
  ("the best labels", "most important genres") still return
  `clarification_needed`.
```

---

## §2.2 — new note about who populates `carryover_preamble`

Append the following paragraph immediately after the Behavior block:

```markdown
**Producer**: the `router` node (per `004/contracts/graph.md §router`)
loads the carryover preamble via
`agent.graph.nodes._carryover.load_carryover_for_state` BEFORE
invoking `query_classifier`, and passes the result through
`ClassifierInput.carryover_preamble`. The router also writes the
preamble into `AgentState.carryover_preamble` so downstream nodes
(query_understanding) can read it without a second DB fetch.
`query_understanding` no longer calls the loader itself — it reads
from state.

**Carryover invariants** (unchanged from the carryover module's
existing contract): preamble is built from same-thread prior
`user_query` text only, capped at 4 turns / 512 tokens (per
`settings.THREAD_CARRYOVER_TURNS` and
`settings.THREAD_CARRYOVER_TOKEN_BUDGET`). Carries only the
`user_query` text — never SQL, generated code, or final responses.
See `015/contracts/carryover-as-router-input.md` for the cross-node
carryover-flow contract.
```

---

## Why this matters

Pre-015, the classifier saw only `user_query` + `schema_context` and made a routing decision on the bare input. Short follow-up questions like *"and the second one?"* — perfectly unambiguous in conversation context but mechanically ambiguous in isolation — got rejected as `clarification_needed`. The user would have to manually rephrase the full question to get an answer.

Adding `carryover_preamble` to `ClassifierInput` is the smallest schema change that closes the bug. The router node was always the right place to build carryover; pre-015 it was simply built one node too late.

---

## Constitution compliance

- **VII.b** (Prompt-authoring discipline): the carryover preamble is dynamic per-run context (built from prior turn texts in the same thread). Adding `{carryover_block}` to `router.md` mirrors the existing `query_understanding.md` placeholder — the legitimate channel for dynamic context.
- **Principle VI** (Two Components, One Contract): producer (router node) and consumer (classifier tool) both live entirely within `agent/`. ETL and frontend components are not touched.

---

## Verification

After implementation:

- `grep "carryover_preamble" agent/src/discogs_agent/tools/query_classifier.py` returns at least 2 matches (schema field + render call).
- `grep "carryover_block" agent/src/discogs_agent/prompts/router.md` returns 1 match (the new placeholder).
- A unit test in `agent/tests/unit/test_query_classifier.py` exercises `ClassifierInput(carryover_preamble="...")` and asserts the result is `simple` or `complex`, not `clarification_needed` (per spec FR-009 / research §R7).

---

## Implementation pointer

Implementation lands as part of 015:

- `agent/src/discogs_agent/tools/query_classifier.py` — `ClassifierInput` gains `carryover_preamble: str | None = None`; `_render_prompt` passes it through to the template `.format()` call.
- `agent/src/discogs_agent/graph/nodes/router.py` — calls `load_carryover_for_state(state)` and passes the result into `ClassifierInput`.
- `specs/004-agent-v1/contracts/tools.md` §2.2 — receives the schema + behavior amendments per this document.
