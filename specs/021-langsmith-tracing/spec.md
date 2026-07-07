# Feature Specification: LangSmith Tracing for the Collection Agent

**Feature Branch**: `021-langsmith-tracing`
**Created**: 2026-07-06
**Status**: Draft
**Input**: User description: "LangSmith tracing for the collection-agent. The collection-agent's OpenAI tool-calling loop currently has no observability: no token-usage tracking and no trace review. Add LangSmith tracing via the `langsmith` SDK's plain-OpenAI integration — NOT a LangChain migration (017 research R2's plain-SDK decision stands; the loop in agent.py is untouched behaviorally). Scope: wrap the real OpenAI client at the CLI construction site; instrument so each user turn is one trace tree with LLM calls and tool executions nested under it; configuration via env vars in the existing `.env` pattern. Tracing must be a strict no-op when unconfigured: tests stay offline, no new required config, no behavior change to the agent loop, tools, or write gate. Token usage per turn must be visible. New dependency: `langsmith` only."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review a conversation turn as one trace tree (Priority: P1)

The owner has a conversation with the collection agent, then opens the LangSmith project and finds one trace per user turn. Expanding a trace shows, in order, every LLM request the turn made and every tool execution it triggered — each tool span named after the tool, carrying the arguments it actually received and the result (or error payload) it returned. When a turn misbehaves — a wrong tool choice, a hallucinated answer, a tool-budget exhaustion — the owner can reconstruct exactly what the model saw and did without adding print statements or re-running the conversation.

**Why this priority**: This is the capability the owner misses from the `agent/` component. Every past collection-agent postmortem (018, 019, the 020 replay findings) was diagnosed by manually replaying prompts; turn-level traces make the next incident inspectable directly from the failing session. Without the trace tree, the other stories have nothing to hang off.

**Independent Test**: Configure tracing, run a scripted two-turn conversation (one analytics question, one question that triggers a multi-tool round), and verify in LangSmith: exactly two root traces, with the expected LLM-call and tool spans nested under each.

**Acceptance Scenarios**:

1. **Given** tracing is configured, **When** the owner asks a question that resolves in a single LLM round with no tool calls, **Then** LangSmith shows one root trace for the turn containing exactly one nested LLM call.
2. **Given** tracing is configured, **When** a turn triggers tool calls (e.g., `filter_records` then a narration round), **Then** the root trace contains each LLM request and one child span per tool execution, showing the tool's name, its arguments, and its returned payload.
3. **Given** tracing is configured, **When** a tool returns an error payload (unknown tool, invalid arguments, tool exception), **Then** that error payload is visible in the corresponding tool span exactly as the LLM received it.
4. **Given** tracing is configured, **When** a turn hits the tool-round safety valve, **Then** the trace shows all rounds up to the budget so the owner can see the loop the model was stuck in.
5. **Given** tracing is configured, **When** the owner inspects a traced LLM request, **Then** the request payload reflects what was actually sent — including the transient decision-point language reminder that is never persisted to the session — so traces are faithful to the wire, not to the stored session.

---

### User Story 2 - Track token usage per turn (Priority: P2)

The owner wants to know what conversations cost. Each traced LLM call records its token usage (prompt, completion, total) as reported by the provider, and LangSmith aggregates usage per trace, so the owner can see what any given turn cost in tokens and watch usage trends across sessions — e.g., confirming that a lean-listing change actually shrank prompt sizes.

**Why this priority**: Token tracking is the second half of the stated need, but it is only meaningful once traces exist (US1). It requires no additional instrumentation beyond faithful capture of provider-reported usage.

**Independent Test**: Run one traced turn, open its trace, and verify prompt/completion/total token counts are present on each LLM call and aggregate at the trace root.

**Acceptance Scenarios**:

1. **Given** tracing is configured, **When** a turn completes, **Then** every LLM call in its trace carries the provider-reported prompt, completion, and total token counts.
2. **Given** several traced turns, **When** the owner views the project in LangSmith, **Then** per-trace token totals are visible without manual arithmetic.

---

### User Story 3 - Zero footprint when unconfigured (Priority: P1)

A developer (or CI) runs the agent or its test suite on a machine with no tracing configuration. Nothing changes: the agent answers identically, no network calls to any tracing service are attempted by the test suite, no warning noise is emitted for the missing configuration, and no new configuration is required to run anything that ran before.

**Why this priority**: Co-equal with US1 because it is a hard constraint, not a nice-to-have: the test suite's offline guarantee (213 tests, no live API calls) and the agent's behavioral contracts (017 §4 write gate, 018–020 amendments) must survive this feature unconditionally. A tracing feature that alters untraced behavior is a regression.

**Independent Test**: With all tracing environment variables absent, run the full test suite offline and a live conversation; both behave exactly as on current `main`.

**Acceptance Scenarios**:

1. **Given** no tracing configuration, **When** the full test suite runs, **Then** all tests pass offline and no test exercises or requires the tracing service.
2. **Given** no tracing configuration, **When** the owner runs a live conversation, **Then** agent behavior (answers, tool dispatch, write gating, session state) is unchanged from current `main`.
3. **Given** tracing is configured but the tracing service is unreachable or the credential is invalid, **When** the owner runs a conversation, **Then** every turn still completes normally — tracing degrades silently (at most a log-level notice) and never blocks, delays materially, or fails a turn.

---

### Edge Cases

- **Tracing enabled, service down or key invalid**: turns must complete normally; trace delivery failure is not an agent failure (US3, scenario 3).
- **Tracing enabled mid-project history**: traces contain the full message history of the session so far (the loop resends the session each round); this is accepted — it is what makes a trace self-contained.
- **Sensitive payloads**: traces necessarily carry the owner's collection data, prompts, and the personal-token-synced snapshot content (never the token itself). Sending conversation content to the tracing service is an accepted, owner-only decision (see Assumptions); credentials (Discogs token, tracing key) must never appear in trace payloads.
- **Stubbed LLM clients in tests**: test stubs are never wrapped for tracing; instrumentation must not require tests to change or to stub the tracing service.
- **Write-path turns**: a turn that produces a write plan is traced like any other turn (the proposal tool span is visible), but tracing observes only — the write gate's confirm-before-execute flow is untouched and `execute_plan` remains unreachable by the model.
- **Tool-round budget exhaustion**: the fallback "could not complete within the tool budget" turn is still a trace tree (all rounds visible) — that is precisely the turn the owner most wants to inspect.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When tracing is configured, every user turn MUST produce exactly one root trace in the configured tracing project, encompassing all LLM requests and all tool executions of that turn.
- **FR-002**: Every LLM request within a traced turn MUST appear as a nested run carrying the request actually sent (including transient, never-persisted messages) and the provider-reported token usage (prompt, completion, total).
- **FR-003**: Every tool execution within a traced turn MUST appear as a nested run named after the tool, carrying the arguments the tool received and the payload it returned — including error payloads (unknown tool, invalid JSON, validation failure, tool exception) exactly as returned to the LLM.
- **FR-004**: Tracing MUST be activated solely by environment configuration following the component's existing `.env` pattern: an enable flag, a credential, and an optional project name. Absent that configuration, tracing MUST be a strict no-op — no network calls to the tracing service, no warnings, no new required configuration for any existing workflow.
- **FR-005**: The feature MUST NOT change agent behavior in any configuration: identical LLM-visible messages, identical tool dispatch and error semantics, identical session state, and an untouched write gate (`propose_moves`-only; CLI-confirmed execution) whether tracing is on, off, or failing.
- **FR-006**: The test suite MUST continue to run fully offline with no tracing configuration and no dependency on the tracing service; existing tests MUST NOT need modification to accommodate instrumentation, and stub LLM clients MUST NOT be wrapped.
- **FR-007**: Failures in trace delivery (unreachable service, invalid credential, timeouts) MUST NOT fail, block, or materially delay a conversation turn; degradation is silent or at most a log-level notice.
- **FR-008**: Trace payloads MUST NOT contain credentials (the Discogs user token or the tracing credential itself).
- **FR-009**: The integration MUST add exactly one new runtime dependency (the tracing SDK) and MUST NOT introduce an LLM-framework migration; the existing plain-SDK tool-calling loop remains the architecture of record (017 research R2 decision stands).

### Key Entities

- **Turn trace**: the root observability record for one user turn; owns the ordered set of LLM-call runs and tool runs produced by that turn; aggregates token usage.
- **LLM-call run**: one request/response against the model within a turn; carries the as-sent message payload and provider-reported token usage.
- **Tool run**: one tool execution within a turn; carries tool name, received arguments, and returned payload (result or error).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A scripted live conversation of 3 turns (one no-tool turn, one multi-tool turn, one turn producing a tool error) yields exactly 3 root traces in LangSmith, and 100% of the LLM requests and tool executions in those turns appear as nested runs with the correct names, arguments, and payloads.
- **SC-002**: For every traced LLM call, prompt/completion/total token counts are present and match the provider-reported usage; per-turn totals are readable in the tracing UI without manual computation.
- **SC-003**: The full test suite passes offline with zero tracing configuration and zero network calls to the tracing service, with no existing test modified to accommodate the feature.
- **SC-004**: With tracing unconfigured, a replayed reference conversation produces behavior indistinguishable from current `main` (same answers modulo LLM nondeterminism, same tool calls, same write-gate prompts).
- **SC-005**: With tracing configured but the tracing credential invalidated, a live conversation completes every turn normally with no user-visible failure.
- **SC-006**: A new trace is visible in the tracing project within 60 seconds of its turn completing (real-time review, not batch export).

## Assumptions

- The named tracing service (LangSmith) is a requirement-level owner decision, not an implementation leak: the owner already operates LangSmith for the `agent/` component and wants the collection agent in the same pane of glass.
- Sending conversation content — including synced collection data embedded in prompts and tool payloads — to LangSmith is acceptable: this is a single-owner personal tool and the owner already accepts the same exposure for the `agent/` component. Only credentials are excluded (FR-008).
- The owner has (or will create) a LangSmith account and API key; no team/multi-user trace access is needed.
- Instrumentation points are the CLI construction site (where the real LLM client is built) and the agent's turn/tool boundaries; tests inject stub clients and therefore never cross a traced boundary. This is why FR-006 costs nothing: the injectable-client design (017) already separates real and test wiring.
- Trace retention, sampling, and dashboarding are LangSmith's stock behavior; no custom retention or export requirements for v1.
- No tracing of the sync pipeline (Discogs API calls) in this feature — scope is the conversational loop (LLM + tools). Sync observability, if ever wanted, is a separate feature.
- The 020 transient language reminder appearing in trace payloads (US1 scenario 5) is desired, not incidental: traces must show the wire truth.
