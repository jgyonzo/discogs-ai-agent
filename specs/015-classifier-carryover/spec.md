# Feature Specification: Classifier carryover — multi-turn follow-up questions stop getting rejected

**Feature Branch**: `015-classifier-carryover`
**Created**: 2026-05-11
**Status**: Draft
**Input**: User direction: *"Option A + SDD back-fill"* for the classifier-doesn't-see-prior-context bug diagnosed in conversation. Triggered by thread `9214f7fb-e79c-4c65-8785-8cae6fa27abf` on 2026-05-11.

## Context: a node-vs-node split that loses multi-turn context

On 2026-05-11, the user asked five questions in a single thread. Three succeeded. Two — *"and what is the second one?"* and *"and the top 5?"* — were rejected with `failed_clarification_needed`. Both rejections were "fair" from the classifier's point of view (those questions ARE ambiguous in isolation), but the user had just asked a question that fully resolved what "the second one" and "the top 5" referred to.

Thread `9214f7fb-...` runs in order:

| # | Query | Status | `metadata_json.carryover` |
|---:|---|---|---|
| 1 | *"Which labels have the most stylistic diversity?"* | `succeeded` | `null` (first turn — expected) |
| 2 | *"which is the label with most Electronic releases?"* | `succeeded` | object, `turn_count: 1` |
| 3 | **"and what is the second one?"** | **`failed_clarification_needed`** | **`null`** |
| 4 | *"which is the top 2 labels with more electronic releases"* (user rephrased) | `succeeded` | object, `turn_count: 3` |
| 5 | **"and the top 5?"** | **`failed_clarification_needed`** | **`null`** |

The rationale on run 3 was *"The question is ambiguous and does not specify what metric or data is being referred to as 'the second one'."* On run 5: *"The question is ambiguous about what metric or category the user is referring to as 'top 5'."* Both rationales are correct given what the classifier saw. The bug is that **the classifier saw the bare user_query with zero prior conversation context.**

### Why the classifier sees nothing

The agent graph has two early decision points:

```
user_query → router (query_classifier)  → IF clarification_needed → response_synthesizer → END
                                        → IF complex / simple     → query_understanding → … → END
                                                                     ↑
                                                                     └── carryover is built HERE
                                                                         (build_carryover_preamble
                                                                          in query_understanding.py)
```

The classifier's prompt (`agent/src/discogs_agent/prompts/router.md`) takes only `{user_query}` and `{schema_context_block}` — there is no `{carryover_block}` placeholder. The multi-turn carryover (CLAUDE.md: *"only prior user-query text, capped at 4 turns / 512 tokens, flows into query_understanding"*) is built and consumed in the NEXT node. When the classifier short-circuits to `clarification_needed`, `query_understanding` never runs, no carryover is built, and the persisted `metadata_json.carryover` ends up `null`.

This is a structural bug, not a postmortem of a specific recent decision: the graph wiring has been this way since multi-turn support was introduced, but the case is only visible to users who ask short anaphoric follow-ups ("and the next?", "same but for X", "what about Y").

### What 015 changes

The classifier gets the same multi-turn context the next node already gets. Carryover is built once (in the router, or in a new prelude node — implementation detail), passed through state, consumed by both the router prompt AND query_understanding. The router prompt gains a `{carryover_block}` placeholder and instruction text about resolving short follow-ups against prior turns.

A small persistence improvement folds in: `metadata_json.carryover` gets populated at run start (so even `failed_clarification_needed` runs show what context the classifier had). Today `carryover: null` could mean "first turn (nothing to carry)" OR "classifier short-circuited before the node that builds carryover" — these are indistinguishable on the persisted record.

The fix is the smallest-diff of three options diagnosed in conversation (A = plumb into classifier; B = move carryover to a graph-level prelude; C = make clarification_needed a routable state with retry-on-richer-context). The user picked A — fix the asymmetry by giving the classifier the same context, don't refactor the graph control flow.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Multi-turn follow-up questions don't get rejected (Priority: P1) 🎯 MVP

A user in the middle of a conversation asks a short follow-up that references prior turns by anaphora ("and the next one?", "and the top 5?", "same but for jazz?", "what about 2010?", "show me 10 instead"). The agent resolves the reference against the conversation's prior question texts and routes to code generation, just as it would for an explicit rephrasing. The user no longer has to manually re-state the full question to get an answer.

**Why this priority**: the reported bug is a clear regression on basic multi-turn UX. The user's two failing questions in thread `9214f7fb-...` are exactly the natural shape of follow-up — terse, anaphoric, relying on the prior turn. The agent's multi-turn story (CLAUDE.md: *"light contextual carry-over"*) is specifically designed for this. Fixing this is the whole point of 015.

**Independent Test**: replay thread `9214f7fb-...` (or a new thread with the same shape: first ask *"which is the label with most Electronic releases?"*, then ask *"and what is the second one?"*). On the post-015 agent, the second question MUST NOT terminate as `failed_clarification_needed`; it MUST route through `query_understanding` and produce a chart for the second-ranked label by Electronic releases. Per spec §SC-001, SC-002.

**Acceptance Scenarios**:

1. **Given** a user thread with at least one prior succeeded question that establishes a sort/rank/filter (e.g., *"top labels by Electronic releases"*), **When** the user asks a short anaphoric follow-up (*"and the next one?"*, *"and the top 5?"*), **Then** the agent classifier routes to `simple` or `complex` (not `clarification_needed`), `query_understanding` resolves the anaphora against the carryover preamble, and the run produces a chart.
2. **Given** a user thread with at least one prior succeeded question, **When** the user asks a "same but for X" follow-up (*"same but for jazz"*, *"what about 2010 instead"*), **Then** the classifier routes through the normal path, and the generated SQL substitutes the new filter value while preserving the prior question's shape.
3. **Given** a brand-new thread (no prior turns), **When** the user asks a genuinely ambiguous question (*"What are the best labels?"*, *"Which genres are most important?"* — the canonical isolation-ambiguous examples from the existing router prompt), **Then** the classifier still returns `clarification_needed` and the user gets a clarification prompt. This is a regression guard: 015 narrows clarification_needed's behavior, doesn't disable it.
4. **Given** a thread where the classifier on the second turn DOES see carryover, **When** the operator inspects the persisted `agent_runs.metadata_json.carryover` for that run, **Then** the field is populated (object with `preamble` + `turn_count`), even if the run terminated as `clarification_needed`. Today this field is `null` for any clarification_needed run.

---

### User Story 2 — Operator can distinguish "first turn" from "classifier short-circuited" in run records (Priority: P2)

When an operator triages a failed `clarification_needed` run by looking at `agent_runs.metadata_json.carryover`, the persisted value distinguishes "this was a first-turn run with no prior context to carry" from "this run had prior turns available but terminated before the node that builds carryover ran." Pre-015 both cases persist as `null`, forcing the operator to look up the thread's other runs to figure out which case they're in.

**Why this priority**: P2 because US1 already changes the persistence pattern as a side-effect of building carryover earlier — once carryover is built in the router (or a prelude node), it CAN be persisted before the run terminates. US2 is the explicit guarantee that this happens. Operator-facing improvement; not user-facing.

**Independent Test**: inspect `agent_runs.metadata_json.carryover` for a thread's 2nd-or-later run that terminated as `clarification_needed`. The field MUST be populated as an object (with at least `turn_count` and `preamble`). For the thread's first run (no prior turns), the field MAY be `null` OR an object with `turn_count: 0` — the spec leaves this to implementation, as long as the two cases are distinguishable. Per spec §SC-003.

**Acceptance Scenarios**:

1. **Given** a thread's 2nd run that terminates as `clarification_needed`, **When** the operator queries `agent_runs.metadata_json.carryover`, **Then** the field is an object containing `turn_count >= 1` and a `preamble` listing prior user-query text. This contrasts with the pre-015 behavior of `null`.
2. **Given** a thread's 1st run (no prior turns), **When** the operator queries the same field, **Then** the field is either `null` OR an object with `turn_count == 0`. The two-case distinction is preserved (`null` vs `turn_count: 0` are both valid as long as they're distinguishable from `turn_count >= 1`).

---

### Edge Cases

- **First-turn questions (no prior context)**: classifier behavior MUST be unchanged. With an empty carryover preamble, the classifier sees the same `{user_query}` + `{schema_context_block}` it saw pre-015 — `{carryover_block}` interpolates to an empty string. Genuinely isolation-ambiguous first-turn questions still route to `clarification_needed` (US1 acceptance scenario 3).
- **Long threads (>4 prior turns)**: the carryover preamble is capped at 4 turns / 512 tokens (existing limit from `_carryover.py`). When the cap is reached, the classifier sees the most recent 4 turns. Older context is dropped. This is the same behavior `query_understanding` has today; 015 doesn't change the carryover-build invariants, only the consumers.
- **Cross-thread isolation**: the carryover preamble is built from the SAME thread's history (existing invariant from `_carryover.py`). 015 does not weaken this; the classifier sees only the current thread's prior turns.
- **Compound follow-ups**: a question like *"and the top 5 for jazz instead"* combines anaphora ("and the top 5") with substitution ("for jazz instead"). The classifier should route to `simple`/`complex` (per US1 acceptance scenario 2 logic); query_understanding handles the resolution. 015 doesn't require new classifier sophistication for this — the classifier only decides routing, not the full resolution.
- **Carryover with a previously-failed turn in it**: thread `9214f7fb-...` run 4 had carryover that included run 3's text (`"and what is the second one?"` — which itself failed). The classifier saw a follow-up over a failed prior turn; today this still works (run 4 succeeded) because the classifier doesn't care about prior turn status, only text. 015 preserves this: carryover preamble includes prior user-query text regardless of that turn's terminal status.
- **The pre-existing isolation-ambiguous examples** (*"What are the best labels?"*, *"Which genres are most important?"*) MUST still be classified as `clarification_needed`. These examples are independent of conversation context — even with rich carryover, "the best labels" is missing a metric. The router instruction MUST preserve this case.
- **Persistence sub-bug "first turn = null" vs "short-circuited = null"**: pre-015 these are indistinguishable. US2 makes them distinguishable. The spec leaves the exact distinction to implementation — both "object with `turn_count: 0`" AND "null only on first turn" are defensible.

## Requirements *(mandatory)*

### Functional Requirements

**US1 — Classifier sees the same multi-turn context query_understanding does**

- **FR-001**: The router node (or a new graph-level prelude node — implementer's choice) MUST build the carryover preamble using `build_carryover_preamble` (existing helper at `agent/src/discogs_agent/graph/nodes/_carryover.py`) BEFORE the classifier prompt is invoked. The preamble MUST be available in `AgentState` by the time `query_classifier` runs.
- **FR-002**: `agent/src/discogs_agent/prompts/router.md` MUST gain a `{carryover_block}` placeholder. The placeholder interpolates to the carryover preamble string (or an empty string on the first turn of a thread). Suggested location: between the `{schema_context_block}` placeholder and the final classification instruction.
- **FR-003**: `router.md` MUST gain instruction text directing the classifier on how to use the carryover block. Suggested wording (the implementation may refine):

  > If the question is a short follow-up that references prior turns by anaphora ("and the next one?", "and the top 5?", "same but for X", "what about Y instead?", terse fragments without an explicit subject), use the prior question text in the carryover block above to resolve the reference. Return `simple` or `complex` as appropriate. Do NOT return `clarification_needed` if the prior question text would unambiguously resolve the follow-up.

- **FR-004**: The pre-existing isolation-ambiguous examples in `router.md` (*"What are the best labels?"*, *"Which genres are most important?"*) MUST remain as canonical examples of when `clarification_needed` IS appropriate. These examples are independent of conversation context — even with rich carryover, they're missing a metric. The router instruction MUST preserve this case.
- **FR-005**: The classifier's persisted `metadata_json.route_rationale` (one-sentence rationale field) MUST reflect the classifier's reasoning given the carryover it saw. When a follow-up is correctly resolved, the rationale MAY reference the prior turn (e.g., *"Follow-up referencing prior 'top labels by Electronic releases' question; complex due to ranking + filter."*). This is a softer requirement than FR-001 through FR-004; what matters is the user-facing behavior change.
- **FR-006**: `query_understanding` MUST continue to receive the same carryover preamble (no behavior regression there). The cleanest implementation reads the preamble from `AgentState` instead of re-building it, eliminating the duplicate call to `build_carryover_preamble`. Whether to deduplicate is an implementation choice; the spec requires only that query_understanding's pre-015 behavior is preserved.

**US2 — Operator can distinguish "first turn" from "classifier short-circuited"**

- **FR-007**: The carryover preamble (object with `preamble` and `turn_count` fields, matching the existing shape in `metadata_json.carryover` for successful runs) MUST be persisted on the run record BEFORE the classifier runs. So even runs that terminate as `clarification_needed` end up with a non-null carryover field on a 2nd-or-later turn.
- **FR-008**: For a thread's first turn (no prior turns to carry), the `metadata_json.carryover` field on `agent_runs` MAY be `null` OR an object with `turn_count: 0`. The two-case distinction (`turn_count >= 1` vs first-turn) MUST be unambiguous from the persisted record alone.

**Test surface**

- **FR-009**: New unit tests for the classifier MUST exercise: (a) a follow-up shape with non-empty carryover → expect `complexity = "simple"` or `"complex"`, NOT `"clarification_needed"`; (b) a first-turn isolation-ambiguous question (no carryover) → expect `clarification_needed` (regression guard for pre-015 behavior); (c) a follow-up shape with empty carryover → behavior matches (b), not (a). At least 3 new test cases.
- **FR-010**: Existing tests that exercise the router/query_classifier with empty carryover MUST continue to pass without modification. If any test today implicitly relied on the router NOT receiving carryover, it MUST be updated to assert the new behavior explicitly.

**Contract amendments**

- **FR-011**: `specs/004-agent-v1/contracts/tools.md` (or wherever the `query_classifier` tool's inputs are normatively documented) MUST be amended to record the new carryover input. The amendment lives in this feature's `contracts/amendment-004-tools.md`.
- **FR-012**: If a separate contract document owns the multi-turn carryover invariants (the `_carryover.py` 4-turn / 512-token cap, the same-thread-only rule, etc.), that document MUST be amended to record that the carryover is now consumed by the router in addition to query_understanding. Otherwise this requirement folds into FR-011.

**Renumbering admin**

- **FR-013**: `specs/013-filtered-aggregation-postmortem/contracts/successor-015-pointer.md` MUST be renamed to `successor-016-pointer.md` because 015 is now this spec. The pre-existing renumbering precedent (014's FR-018) established this admin pattern. Content edits per the same pattern: every reference to `015-release-unique-view-materialization` becomes `016-release-unique-view-materialization`; the historical-context note at the top is updated to reflect the second renumbering. The amendment lives in this feature's `contracts/renumbering-013-pointer.md`.

**Bundled hot patches (added 2026-05-11 during 015 implementation)**

The first post-015 production run (`4b781b03-75fc-41a9-ac24-e2aea28a4516`, 2026-05-11) showed the 015 carryover plumbing working as designed — the classifier correctly resolved *"and what is the second one?"* against the prior turn — but exposed two pre-existing-but-now-visible issues downstream:

1. **Ambiguous-column SQL bug.** The LLM (gpt-4o-mini) generated `COUNT(DISTINCT release_id)` in a JOIN of `release_label_bridge` and `release_fact` — both tables expose `release_id`, so DuckDB rejected the SQL with a binder error. The 2-retry budget was exhausted before the LLM converged on the qualified form.
2. **Misleading `failed_safety` user message.** The response synthesizer routed every `failed_safety` case to *"referenced something not allowed by the data contract"* — wrong for `sql_invalid` (binder errors are SQL-quality issues, not contract violations) and `read_only_required` (code-shape issues).

These two are bundled into 015 as prompt-only hot patches (no graph wiring change). The third issue surfaced in the same run — the top-level `agent_runs.errors[]` aggregate is never populated, regardless of which node failed — is a foundational observability gap that exceeds hot-patch scope and is deferred to a future SDD spec.

- **FR-014**: `agent/src/discogs_agent/prompts/code_generator.md` MUST gain a new "Critical rule for JOIN queries" section requiring fully-qualified column references (including inside aggregate functions) whenever a SELECT joins two or more tables. The canonical join-then-count pattern is provided as an example.
- **FR-015**: `agent/src/discogs_agent/prompts/repair_code.md` MUST mirror FR-014's join-qualify rule in its Critical-rules bullets, so the LLM gets the rule on retry as well as on first-attempt.
- **FR-016**: `agent/src/discogs_agent/graph/nodes/response_synthesizer.py` `_build_result_block` MUST detect `terminal_status == "failed_safety"` and surface the violation rule class (`contract` / `sql_quality` / `code_shape` / `other`) into the result_block as a `Failed-safety rules: ... (class: ...)` line. The class is derived from the rule names in `safety_result.violations`.
- **FR-017**: `agent/src/discogs_agent/prompts/response_synthesizer.md` MUST replace the generic "data contract" wording for `failed_safety` with per-class guidance: `contract` keeps the existing wording, `sql_quality` uses "couldn't parse cleanly after retrying — usually a column or join shape that doesn't match the schema", `code_shape` uses "didn't follow the safety contract after retrying". In every class, the synthesizer MUST NOT name specific rule strings (those are for operators).
- **FR-018**: New unit tests at `agent/tests/unit/test_response_synthesizer_failed_safety.py` MUST exercise the classification logic from FR-016 across at least 6 rule shapes (`sql_invalid` → sql_quality; `read_only_required` → code_shape; `forbidden_table`/`forbidden_join`/`ddl_dml` → contract; mixed-with-`sql_invalid` → sql_quality precedence).

### Key Entities

- **`AgentState.carryover_preamble`** (existing field per `graph/state.py:23`) — gains a new producer (the router or a prelude node, per FR-001). Field shape unchanged.
- **`AgentState.carryover_turn_count`** (existing field per `graph/state.py:24`) — same as above.
- **`{carryover_block}` placeholder in `router.md`** (new in 015) — text interpolated from the carryover preamble. Empty string when no prior turns; non-empty otherwise. Mirrors the existing placeholder in `query_understanding.md`.
- **`agent_runs.metadata_json.carryover`** (existing Postgres JSONB column) — pre-015 populated only when query_understanding ran. Post-015 populated as soon as the carryover is built (in the router or prelude node), per FR-007. Field shape unchanged (object with `preamble` and `turn_count`).
- **Renumbered ETL pointer** (existing as `successor-015-pointer.md`; becomes `successor-016-pointer.md` per FR-013).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A thread that mirrors `9214f7fb-...`'s shape — at least one explicit ranked-by-metric question followed by an anaphoric follow-up (*"and the next one?"*, *"and the top 5?"*) — produces a chart on the post-015 agent, with `agent_runs.status == "succeeded"` on the follow-up turn. Verifiable by replaying the thread or by sending the same two-message sequence end-to-end.
- **SC-002**: For at least 5 follow-up-shape questions across distinct prior topics ("and the next?" after a top-1 question; "and the top 5?" after a top-2 question; "same but for jazz" after a rock query; "what about 2010" after a 2020 query; "show me 10 instead" after a default-limit query), `agent_runs.status` is NOT `"failed_clarification_needed"` on the post-015 agent.
- **SC-003**: For any `clarification_needed` run on a 2nd-or-later turn of a thread, `agent_runs.metadata_json.carryover` is a non-null object with `turn_count >= 1` and a non-empty `preamble`. Verifiable by inducing a clarification_needed on a multi-turn thread (or by inspecting historical runs post-015).
- **SC-004**: Genuinely isolation-ambiguous first-turn questions (*"What are the best labels?"*, *"Which genres are most important?"*) STILL return `clarification_needed`. Verifiable by sending one of those questions as the first message in a new thread and asserting `agent_runs.status == "failed_clarification_needed"`. Regression guard for the canonical case.
- **SC-005**: Pre-015 test baseline (148 passed, 3 skipped post-014) continues to pass on the post-015 codebase. New tests per FR-009 add at least 3 passing cases. Total post-015: at least 151 passed, 3 skipped.
- **SC-006**: The renumbered ETL pointer file (`013/contracts/successor-016-pointer.md`) exists; the old `successor-015-pointer.md` does not; the historical-context note reflects both renumberings (013→014 was the first; 014→015 was the second... wait, this is the second renumbering of this same pointer: original 014 → 015 by feature 014; now 015 → 016 by feature 015). Verifiable by `ls` + `grep`.

## Assumptions

- **`build_carryover_preamble` is reusable from the router context.** The existing helper at `agent/src/discogs_agent/graph/nodes/_carryover.py:46` takes an AgentState and returns the preamble + turn_count. Calling it from the router (or a prelude node) requires no signature change. Spec assumes this; implementation MAY refactor if convenient.
- **The classifier's behavior on first-turn questions is unchanged.** Empty carryover preamble → classifier sees the same input it saw pre-015. This assumption is load-bearing for SC-004.
- **The carryover cap (4 turns / 512 tokens) is unchanged.** 015 does not modify the carryover-build invariants; it only changes who consumes the result.
- **Cross-thread isolation is unchanged.** The carryover is built from same-thread history only. 015 inherits this invariant.
- **No constitution amendment required.** Constitution VII.b (prompt-authoring discipline) allows dynamically-rendered placeholders for per-run context. Adding `{carryover_block}` to `router.md` is consistent with VII.b — the placeholder is the legitimate channel for dynamic context, not static schema prose. The instruction text about resolving follow-ups is rule-of-thumb (VII.b carve-out for prompts' rules).
- **Persistence of carryover at run start is mechanically straightforward.** Once the router builds carryover, persisting it to `metadata_json.carryover` is one more JSON-write — the existing serialization path. No schema change.

## Out of Scope

- **Refactoring `clarification_needed` to be routable / retryable** (Option C from the diagnosis). 015 does Option A. Option C would add a new control-flow path through the graph; deferred unless a future regression shows that even with carryover, some follow-up shapes legitimately need a re-classification pass.
- **Moving `build_carryover_preamble` to a graph-level prelude node** (Option B from the diagnosis). 015 does Option A. Option B is the architecturally cleanest refactor but is larger scope; if implementation experience reveals that the router-builds-carryover pattern is awkward in practice (e.g., the router has reason NOT to build carryover in some cases), a future spec can extract the prelude.
- **Extending the carryover preamble to include prior SQL / prior charts / prior dataframes.** CLAUDE.md's "Multi-turn = light contextual carry-over — only prior user-query text" remains in force. 015 does NOT widen the carry-over surface.
- **Classifier improvements unrelated to multi-turn context** (e.g., better domain-knowledge prompting, classification accuracy on edge cases). 015 is scoped to the carryover bug; unrelated classifier tuning is a separate concern.
- **An audit of whether other early-graph nodes also miss context they should have**. The diagnosis is specific to the router. If a future regression shows another node has the same shape of bug, that's a future spec.
- **ETL-side rewrite of `release_unique_view`** — the deferred work tracked by 013's pointer doc (now `successor-016-pointer.md` per FR-013) remains deferred.
- **Populating the top-level `agent_runs.errors[]` aggregate.** The first post-015 production run (`4b781b03-...`, 2026-05-11) surfaced that the run-level `errors[]` array is initialized empty in `api_query.py:164` and never written to anywhere in the codebase — every run's response shows `errors: []` regardless of how many safety / validation / sandbox errors fired internally. This is a foundational observability gap (the per-tool-call `output_json` carries the violations; nothing aggregates them up). Fixing it touches the persistence path and the API response contract; out of scope for 015's bundle. A future SDD spec (provisional `017-run-errors-aggregation` or similar) is the natural place for it.

## Dependencies

- **`agent/src/discogs_agent/graph/nodes/_carryover.py:46`** — `build_carryover_preamble` is the load-bearing helper that 015 calls from a new earlier site.
- **`agent/src/discogs_agent/graph/nodes/router.py`** OR a new prelude node — the surgical site for FR-001.
- **`agent/src/discogs_agent/prompts/router.md`** — the surgical site for FR-002, FR-003, FR-004.
- **`agent/src/discogs_agent/graph/nodes/query_understanding.py:81–118`** — surgical site for FR-006 (no behavior regression; possible DRY cleanup).
- **`agent/src/discogs_agent/graph/state.py:23–24`** — `AgentState.carryover_preamble` and `carryover_turn_count` are the carrier fields; no changes needed, just earlier population.
- **Persistence layer** — `metadata_json.carryover` is written when the run record's metadata is finalized. Implementation MAY need to teach the persistence path to populate this field at run-start rather than (or in addition to) at query_understanding-end.
- **`agent/tests/unit/test_query_classifier.py`** — surgical site for FR-009 (new test cases).
- **Predecessors**: 005-agent-schema-context (introduced the `{schema_context_block}` placeholder pattern; 015 mirrors it with `{carryover_block}`); 004-agent-v1 (defined the classifier's tool contract; 015's FR-011 amends it).
- **Successor (provisional, renumbered for the second time)**: `016-release-unique-view-materialization` — the ETL-side rewrite of the view's `SELECT DISTINCT (~33 cols)` materialization. Originally provisional `014` (per 013); bumped to `015` by 014's FR-018; now bumped to `016` by this spec's FR-013. Remains deferred. 015 does not deliver it.
- **No constitution amendment**: 015 stays inside Principle VII.b's existing carve-out for dynamically-rendered context. No new principles required.
