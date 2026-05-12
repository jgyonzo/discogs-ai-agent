# Research: 015-classifier-carryover

**Date**: 2026-05-11
**Purpose**: Resolve the implementation choices the spec deliberately left open, and pin exact wording / signatures / test shapes the contracts and tasks need.

The spec's "Edge Cases" + FR-001 + FR-008 flagged three open choices to be resolved here: where to build the carryover (router vs. prelude node); whether to extract `_load_carryover` as a shared helper; and what shape `metadata_json.carryover` takes on a thread's first turn. This research nails those and adds wording + test-coverage decisions that fall out.

---

## R1. Implementation site for carryover-building

**Decision**: Build the carryover INSIDE the `router` node, by calling an extracted-and-renamed `load_carryover_for_state(state)` helper. No new prelude node.

**Rationale**:

- The router is the first node after the API entry point. There is no node between API-entry and router today; adding one is a graph-wiring change that 014's spec explicitly deferred (Out of Scope: *"Moving build_carryover_preamble to a graph-level prelude node — 015 does Option A"*).
- The router already calls one tool (`query_classifier`) and writes one state field (`state["route"]`); adding a `_load_carryover` call before the tool invocation is a one-line addition + one state-mutation pair. Minimal blast radius.
- `query_understanding` (lines 39–73 of `query_understanding.py`) currently hosts `_load_carryover` as a private helper. The function is pure-DB + pure-builder logic that has nothing query-understanding-specific in it — it was always misplaced as a private function of one node when in fact two nodes need it. The extraction is mechanical.
- The router node was structurally the wrong place to omit context. Fixing the asymmetry at the lowest-cost site keeps the architectural shape unchanged.

**Alternatives considered**:

- *Add a thin new prelude node "load_carryover" that runs before router*: rejected. Architecturally cleanest (single-purpose nodes), but adds a graph-wiring change (new node + new edge) for what's effectively a one-line state-population. Worth doing if a future spec extracts more shared prelude work (e.g., user-context loading, feature-flag resolution); not load-bearing for 015 alone.
- *Duplicate `_load_carryover` inline in the router*: rejected. DRY violation. The helper would diverge between the two call sites the first time someone fixes a bug in one and forgets the other.
- *Move `_load_carryover` inside `query_classifier` (the tool)*: rejected. The tool is a thin LLM wrapper that today takes only its own inputs. Pulling DB-querying logic into a tool function breaks the tool/node separation the codebase respects elsewhere.

---

## R2. Extracted helper signature + naming

**Decision**: Rename the extracted function `load_carryover_for_state` (public — no leading underscore) and place it in `agent/src/discogs_agent/graph/nodes/_carryover.py` alongside the existing `build_carryover_preamble` and `PriorTurn` dataclass. The signature is unchanged from today's private version:

```python
def load_carryover_for_state(state: AgentState) -> tuple[str | None, int]:
    """Pull prior runs for this thread and build the preamble.

    Reads from the request-scoped session set by the API. If no
    session is bound (e.g., a unit test invoking the node in
    isolation), returns ``(None, 0)`` — carry-over is a soft
    enrichment, never load-bearing.
    """
    # ... body verbatim from query_understanding.py:39-73 ...
```

`_carryover.py`'s module name keeps the leading underscore (private to the package per convention) but the public function inside it is no-underscore — so it can be imported as a stable symbol by both nodes. The existing `build_carryover_preamble` is also already a public function inside this module; we follow the same pattern.

**Rationale**:

- `_carryover.py` is the natural home: it already hosts `build_carryover_preamble` + `PriorTurn` + the token-budget logic. Adding the DB-fetching `load_carryover_for_state` here makes the module the single load-bearing surface for the whole carryover pipeline.
- Public-symbol-in-private-module is consistent with the existing pattern (`build_carryover_preamble` is itself a public symbol inside the `_carryover.py` module). The underscore on the module signals "implementation detail of `nodes/`," not "internal to one node."
- The new name `load_carryover_for_state` is more descriptive than the pre-extraction `_load_carryover` (which was ambiguous about whether "load" meant "fetch from DB" or "populate into state"). The new name makes the AgentState-shaped input explicit.

**Alternatives considered**:

- *Keep the underscore (`_load_carryover_for_state`)*: rejected. The underscore-prefix convention signals "module-internal" — but now it's used by two nodes, both outside `_carryover.py`. Stripping it is correct.
- *Place the function in `nodes/__init__.py` or a new `nodes/_shared.py`*: rejected. The function is part of the carryover concept; co-locating it with `build_carryover_preamble` minimizes mental load.

---

## R3. `query_understanding` reads carryover from state (DRY)

**Decision**: After the extraction (R2), `query_understanding.py:81` changes from:

```python
carryover_preamble, turn_count = _load_carryover(state)
```

to:

```python
carryover_preamble = state.get("carryover_preamble")
turn_count = state.get("carryover_turn_count", 0) or 0
```

The local `_load_carryover` function (current lines 39–73) is deleted. The import (lines 19–21) is replaced with a single import of `PriorTurn` and `build_carryover_preamble` from `_carryover.py` if still needed elsewhere — actually the only call to `build_carryover_preamble` was inside the now-deleted `_load_carryover`, so the imports also get pruned (a small cleanup).

The state-population at lines 117–118 (`state["carryover_preamble"] = carryover_preamble` etc.) is also removed — the router populated these fields before invoking the classifier (per R1), so the values are already in state by the time query_understanding runs.

**Rationale**:

- DRY. Single load site (router); single read site (query_understanding). Future bug fixes to the carryover-load logic happen in one place.
- Performance: avoids a duplicate `fetch_recent_for_thread` DB call per run (today both the router — if 015 lands — and query_understanding would call it; after DRY, only router does).
- Correctness: the router already populates the state fields, so query_understanding reading from state is guaranteed-non-None-only-if-non-first-turn. Same semantics as today.

**Alternatives considered**:

- *Keep both call sites; let `_load_carryover` use a per-run cache*: rejected. Caches are state. Keeping the function purely-functional and reading the result from `AgentState` is cleaner.
- *Skip the DRY refactor; just add the new router call*: rejected. Would leave behind dead code (the private function in query_understanding.py) and double the carryover-fetch cost per run.

---

## R4. First-turn persistence shape

**Decision**: First-turn `metadata_json.carryover` remains `null`. Non-first-turn runs get `{"turn_count": N >= 1, "preamble": "Recent conversation ..."}`. The two cases are distinguishable: `null` ⟺ "no prior turns," and any non-null object ⟺ "had prior turns."

The existing persistence logic in `api_query.py:240–245` already produces this behavior:

```python
carryover_meta = (
    {"turn_count": carryover_turn_count, "preamble": carryover_preamble}
    if (carryover_preamble or carryover_turn_count)
    else None
)
```

`carryover_preamble` is `None` on first turn (per `build_carryover_preamble`'s early-return when `prior_runs` is empty) and `carryover_turn_count` is `0`. The `if (preamble or turn_count)` condition evaluates `False` → `carryover_meta = None` → persisted as `null`.

After 015 lands (router populates state earlier), the same logic produces:
- First turn: `state["carryover_preamble"] = None`, `state["carryover_turn_count"] = 0` → persisted `null` (same as today).
- 2nd+ turn, succeeded: same as today (object persisted).
- **2nd+ turn, `failed_clarification_needed`**: state was populated by the router *before* the short-circuit → object persisted (NEW — pre-015 this was `null`).

**Rationale**:

- Zero persistence-layer code change. The desired behavior falls out of US1's earlier-population.
- The two-case distinguishability the spec required (FR-008) is preserved: `null` only happens on first turn; non-null implies prior turns existed.
- An alternative shape (`{"turn_count": 0, "preamble": null}` on first turn) would require adding logic to `api_query.py`. Not worth the change for a downstream-equivalent representation.

**Alternatives considered**:

- *Persist `{"turn_count": 0, "preamble": null}` on first turn (option A from FR-008)*: rejected. Requires extra code; downstream consumers would need to handle two object shapes. The `null` form already distinguishes the case unambiguously.

---

## R5. Exact wording for `router.md` instruction text + placeholder placement

**Decision**: Insert the `{carryover_block}` placeholder + the new instruction text BETWEEN the `{schema_context_block}` placeholder block and the routing-instruction block. The placement mirrors `query_understanding.md`'s ordering. Exact text:

```markdown
You are the **router** for a Discogs music-catalog analytics agent.

Classify the user's question into exactly one of:

- `simple` — single-table aggregation, simple filter, standard chart.
  Example: "Show releases by decade." "Distribution of primary formats."
  Routes to the cheap model tier.
- `complex` — joins, window functions, CTEs, outlier detection, period
  comparisons, derived metrics. Example: "Which labels have the most
  stylistic diversity?" "Detect outlier years for House releases."
  Routes to the strong model tier.
- `unsupported` — references metrics or fields the published catalog
  does not contain. Refer to the schema block below for the available
  tables, columns, and grains. Categories that are NEVER present:
  prices, ratings, user counts, reviews. If the question requires
  unavailable data, return `unsupported`.
- `clarification_needed` — the question is ambiguous about what metric
  to use. Examples: "What are the best labels?" "Which genres are most
  important?". Return `clarification_needed`.

Schema context (allowlist + sample distinct values + domain rules):

{schema_context_block}

Recent conversation context (prior user questions in this thread):

{carryover_block}

If the user's question is a short follow-up that references prior turns
by anaphora ("and the next one?", "and the top 5?", "same but for X",
"what about Y instead?", terse fragments without an explicit subject),
USE the prior question text above to resolve the reference. Return
`simple` or `complex` (not `clarification_needed`) if the prior context
unambiguously identifies the metric / table / filter the follow-up
inherits. The `clarification_needed` examples above ("the best labels",
"most important genres") are for questions that are genuinely ambiguous
even with full conversation context — they're missing a metric, not a
referent.

Use the sample distinct values to decide whether a referenced filter
value is in the catalog. If a user asks about "Techno" and the
`release_fact.style` sample contains "Techno", classify as `simple` or
`complex`, NOT `unsupported`. Only return `unsupported` when the
required data category (prices, ratings, user counts, reviews) is
genuinely absent.

Return JSON exactly:

```json
{{"complexity": "<bucket>", "selected_model": "<model_or_null>", "rationale": "<one sentence>"}}
```

For `simple` use `selected_model = "{cheap_model}"`. For `complex` use
`selected_model = "{strong_model}"`. For `unsupported` and
`clarification_needed` use `selected_model = null`.

User question:

{user_query}
```

The new content sits between the existing schema-context block and the existing sample-values guidance. The new block introduces `{carryover_block}` as a placeholder and immediately follows it with instruction text on how to use it.

When `{carryover_block}` interpolates to an empty string (first turn), the prompt still renders cleanly — the heading "Recent conversation context (prior user questions in this thread):" appears with no body below it. This is slightly imperfect (a heading with no content), but the model treats it as "no prior context, fall through to normal classification." Acceptable; if it turns out to confuse the cheap model on first-turn questions, a follow-up can wrap the heading in a conditional.

**Rationale**:

- The placement mirrors `query_understanding.md`. Consistent prompt structure across the two consumers makes future maintenance easier.
- The instruction text uses BOTH a positive formulation ("USE the prior question text") AND a negative formulation ("not `clarification_needed`"), per the lesson learned from 013/014: LLMs resolve ambiguous guidance by inventing shortcuts. Explicit positive + negative is stronger than either alone.
- The instruction text explicitly preserves the canonical isolation-ambiguous examples ("the best labels", "most important genres"). This is regression protection for US1 acceptance scenario 3 / SC-004.
- Anaphoric examples are concrete: "and the next one?", "and the top 5?", "same but for X", "what about Y instead?", "terse fragments without an explicit subject". The set covers the actual user behaviors observed in thread `9214f7fb-...` + common variations.

**Alternatives considered**:

- *Conditional heading (omit the "Recent conversation context" heading when carryover is empty)*: rejected. Would require either Jinja-style templating (the prompts are `.format()`-based today, not Jinja) or a Python-side conditional in `_render_prompt`. Acceptable cost increase if the empty-heading shape proves to confuse the model; not load-bearing for 015 launch.
- *Inline the instruction text into the existing `clarification_needed` bullet*: rejected. The bullet would balloon to multiple paragraphs and lose its parallel structure with the other three bullets. Keeping the new instruction as its own paragraph (with a clear separator) is more readable.
- *Insert the new block BEFORE the bullets*: rejected. The bullets are the classification rubric; they need to be read first so the model understands the buckets. The new block tells the model how to *evaluate* the buckets — it belongs after the rubric.

---

## R6. `ClassifierInput` schema change (backward compat)

**Decision**: Add `carryover_preamble: str | None = None` to `ClassifierInput`. Default `None` for backward compatibility with any caller (e.g., a test) that doesn't pass it.

```python
class ClassifierInput(BaseModel):
    user_query: str
    schema_context: dict[str, object]
    carryover_preamble: str | None = None  # ← NEW in 015
```

`_render_prompt` in `query_classifier.py:36-53` adds one line to the `.format()` call:

```python
system_body = template.format(
    schema_context_block=schema_block,
    carryover_block=(payload.carryover_preamble or ""),  # ← NEW in 015
    cheap_model=settings.CHEAP_MODEL,
    strong_model=settings.STRONG_MODEL,
    user_query="(see user message below)",
)
```

When `carryover_preamble is None`, `(payload.carryover_preamble or "")` evaluates to `""`, so the prompt renders with an empty `{carryover_block}` (the empty-heading shape from R5).

**Rationale**:

- Default-None preserves backward compatibility with all existing tests that pass only `user_query` + `schema_context`. The existing 4 test cases (`test_simple_query_routes_to_simple`, etc.) MUST continue to pass without modification per spec FR-010 — this is what makes them pass.
- The pattern matches the existing `query_understanding.py:84-89` template-format call, which does the same `(carryover_preamble or "")` defensive default.

**Alternatives considered**:

- *Make `carryover_preamble` required (no default)*: rejected. Would force every existing test to be updated, including unit tests that don't care about carryover. Pointless churn.
- *Use an empty string `""` as the default*: rejected. `None` is more semantically meaningful ("we didn't receive any") than empty string ("we received empty"). The `(value or "")` defensive default at the prompt-render call handles either.

---

## R7. Test surface — 3+ new cases for `test_query_classifier.py`

**Decision**: 3 new test cases, all using the existing `llm_stub` fixture pattern. The stub already matches on `user_query` text (per the Explore findings), so the test surface is:

```python
def test_follow_up_with_carryover_routes_to_complex(schema: dict) -> None:
    """Anaphoric follow-up + non-empty carryover MUST resolve to
    simple/complex, NOT clarification_needed (the 015 trigger case)."""
    carryover = (
        "Recent conversation (prior user questions in this thread, oldest first):\n"
        "  1. which is the label with most Electronic releases?\n"
    )
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="and what is the second one?",
                schema_context=schema,
                carryover_preamble=carryover,
            )
        )
    assert out.complexity != "clarification_needed", (
        f"Follow-up with carryover should resolve to simple/complex; "
        f"got {out.complexity!r} with rationale {out.rationale!r}"
    )
    assert out.complexity in ("simple", "complex")
    assert out.selected_model is not None


def test_follow_up_without_carryover_treats_as_first_turn(schema: dict) -> None:
    """Empty carryover (carryover_preamble=None or "") MUST classify
    a follow-up-shape question as clarification_needed — same as
    pre-015 behavior. Regression guard."""
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="and what is the second one?",
                schema_context=schema,
                carryover_preamble=None,
            )
        )
    assert out.complexity == "clarification_needed", (
        f"Follow-up with EMPTY carryover should still need clarification; "
        f"got {out.complexity!r}"
    )


def test_isolation_ambiguous_with_carryover_still_needs_clarification(
    schema: dict,
) -> None:
    """A canonical isolation-ambiguous question ('best labels',
    'most important genres') is missing a METRIC, not a referent.
    Even with rich carryover, it MUST still return
    clarification_needed. Regression guard for the pre-015
    classifier behavior on first-turn ambiguous questions."""
    rich_carryover = (
        "Recent conversation (prior user questions in this thread, oldest first):\n"
        "  1. Show releases by decade.\n"
        "  2. Distribution of primary formats.\n"
    )
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="What are the best labels?",
                schema_context=schema,
                carryover_preamble=rich_carryover,
            )
        )
    assert out.complexity == "clarification_needed", (
        f"'best labels' is ambiguous independently of carryover; "
        f"got {out.complexity!r} with carryover present"
    )
```

The `llm_stub` fixture is consulted via the existing test infrastructure; the stub already has match logic on user_query keywords (per the 4 existing test cases). The stub may need a small extension to handle the new test queries — research §R8 covers this.

**Rationale**:

- Three cases cover the three load-bearing behaviors: (1) the trigger case is fixed; (2) empty-carryover behaves like first-turn; (3) canonical isolation-ambiguous still bites. Together they prove SC-001 + SC-004.
- The test inputs use the actual queries from thread `9214f7fb-...` so the regression-protection is visible to a reader.

**Alternatives considered**:

- *Add 5+ cases covering more follow-up shapes*: rejected as overengineering. The 3 cases cover the three semantic categories; adding more variants of the same category doesn't strengthen the test surface. Future regressions can add cases.
- *Move the new tests to a new file `test_classifier_carryover.py`*: rejected. Co-locating with existing classifier tests keeps the discovery surface unified.

---

## R8. `llm_stub` fixture extension (if needed)

**Decision**: Inspect the existing `llm_stub` fixture (in `agent/tests/conftest.py` or similar). If it pattern-matches on user_query text alone, it will need to be taught the new test queries OR taught to consider the carryover block when the user_query is an anaphoric fragment.

This is a small implementation detail that doesn't affect the spec or contracts. The plan flags it for `/speckit-tasks` to handle as a sub-task of T-test-stub. If the stub needs no change, even better.

**Rationale**:

- The fixture lives in conftest; if it just inspects the system+user message and pattern-matches keywords, we may need to add patterns for "second one" → "simple" classifier reply, etc.
- Worst case: 3 new patterns + a complex-classification stub reply. Cheap.

---

## R9. Persistence path is unchanged

**Decision**: `api_query.py:237–255` is NOT touched. The existing logic reads `final_state.get("carryover_preamble")` and writes `metadata_json.carryover`. After 015, the router populates these fields in state BEFORE the classifier runs, so on every terminal status the state has the carryover values, and the post-graph metadata-write naturally persists them.

The state-population code currently lives in `query_understanding.py:117–118`:

```python
state["carryover_preamble"] = carryover_preamble
state["carryover_turn_count"] = turn_count
```

After 015 (per R1 + R3), this moves to the router node. The query_understanding write disappears (state was already populated upstream).

**Rationale**:

- Smallest persistence-layer change: zero. The existing write path is correct as-is; what changes is *when in the run lifecycle* the state fields get populated.
- No new persistence tests required — the existing path is unmodified.

---

## R10. Renumbering admin (FR-013) — content edits

**Decision**: Mirror 014's renumbering pattern exactly.

1. `git mv specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md specs/013-filtered-aggregation-postmortem/contracts/successor-016-pointer.md`
2. Inside the renamed file:
   - Document title: `015-release-unique-view-materialization` → `016-release-unique-view-materialization`.
   - Provisional naming section: same replacement.
   - The historical-context note at the top is **updated** (not replaced) to reflect both renumberings. New version:

```markdown
*Note: this document was originally drafted as `successor-014-pointer.md`
during 013's `/speckit-plan` phase, when "014" was the provisional spec
number for this deferred ETL fix. On 2026-05-10, the cross-grain-join
postmortem (`014-cross-grain-join-postmortem`) took 014, so the ETL
follow-on was renumbered to "015" by 014's FR-018. On 2026-05-11, the
classifier-carryover spec (`015-classifier-carryover`) took 015, so the
ETL follow-on was renumbered AGAIN to "016" by 015's FR-013. See
`specs/014-cross-grain-join-postmortem/contracts/renumbering-013-pointer.md`
and `specs/015-classifier-carryover/contracts/renumbering-013-pointer.md`
for the two renumbering records.*
```

**Rationale**:

- Identical pattern to 014's FR-018, just incremented. The historical note grows by one paragraph; future renumberings (should they happen) keep appending.
- Preserves git-blame on the renamed file via `git mv`.

**Alternatives considered**:

- *Stop using provisional numbers altogether for deferred work*: tempting but out of scope for 015. A future cleanup spec could rewrite 013's pointer to use a stable placeholder (e.g., "TBD-release-unique-view-materialization") instead of a number, eliminating renumberings. Recorded here for future consideration.

---

## R11. Open questions surfaced during research — NONE

All design questions from the spec are resolved above. No `[NEEDS CLARIFICATION]` markers remain.

---

## Summary of file edits the implementation will perform

For `tasks.md` (next phase) to enumerate:

| File | Change | FR(s) |
|------|--------|-------|
| `agent/src/discogs_agent/graph/nodes/_carryover.py` | Move `_load_carryover` here from `query_understanding.py`; rename to `load_carryover_for_state` (public) | FR-001 prep |
| `agent/src/discogs_agent/graph/nodes/router.py` | Call `load_carryover_for_state(state)`; populate `state["carryover_preamble"]` + `state["carryover_turn_count"]`; pass `carryover_preamble` into `ClassifierInput` | FR-001, FR-007 |
| `agent/src/discogs_agent/graph/nodes/query_understanding.py` | Delete local `_load_carryover` function (lines 39–73); replace call at line 81 with `state.get` reads; remove unused imports; delete state-write at lines 117–118 | FR-006 (DRY cleanup) |
| `agent/src/discogs_agent/tools/query_classifier.py` | Add `carryover_preamble: str \| None = None` to `ClassifierInput`; add `carryover_block` to `_render_prompt`'s `.format()` call | FR-002 |
| `agent/src/discogs_agent/prompts/router.md` | Insert `{carryover_block}` placeholder + new instruction text per R5 | FR-002, FR-003, FR-004 |
| `agent/tests/unit/test_query_classifier.py` | Add 3 new test cases per R7 | FR-009 |
| `agent/tests/conftest.py` (or wherever `llm_stub` lives) | Extend stub to handle new test queries IF needed per R8 | FR-009 (test-stub side) |
| `specs/004-agent-v1/contracts/tools.md` | Document `carryover_preamble` in `ClassifierInput` schema | FR-011 |
| `specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md` | `git mv` to `successor-016-pointer.md`; content edits per R10 | FR-013 |
| `specs/015-classifier-carryover/contracts/*` | 3 contract documents (Phase 1 deliverable) | n/a (contract authoring) |

7 distinct source-file edits + 2 documentation edits + 3 new contract documents.
