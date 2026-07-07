# Data Model: LangSmith Tracing for the Collection Agent

**Feature**: 021-langsmith-tracing · **Date**: 2026-07-07

This feature persists nothing locally and adds no snapshot, session, or
tool-payload fields. Its "data model" is (1) the trace-run hierarchy emitted
to LangSmith and (2) the configuration entity that gates it. Existing
entities (`Snapshot`, `CollectionRecord`, `AgentSession`, `WritePlan`,
`ToolDef`) are unchanged.

## 1. Trace-run hierarchy (emitted, not stored)

One conversation turn ⇒ one run tree in the configured LangSmith project.

```text
TurnTrace (run_type=chain, name="run_turn")            1 per user turn
├── LlmCallRun (run_type=llm)                          1..MAX_TOOL_ROUNDS (8)
│     inputs : as-sent request kwargs — [*session.messages,
│             LANGUAGE_REMINDER], model, tools schema
│     outputs: completion message (content and/or tool_calls)
│     usage  : prompt_tokens, completion_tokens, total_tokens
│             (provider-reported, captured by wrap_openai)
└── ToolRun (run_type=tool, name=<registered tool name>) 0..N per turn
      inputs : the arguments _dispatch received for the tool
      outputs: the exact dict returned to the LLM — result payload
               or one of the four error shapes (unknown tool,
               invalid JSON, validation error, tool exception)
```

### TurnTrace

| Attribute | Source | Notes |
|---|---|---|
| name | constant `"run_turn"` | root span, run_type `chain` |
| inputs | `user_text` argument | the user's message for the turn |
| outputs | `run_turn` return value | final answer text, incl. the tool-budget fallback string |
| project | `Settings.langsmith_project` | via the env bridge (`LANGSMITH_PROJECT`) |
| children | all LlmCallRuns + ToolRuns of the turn | nesting via SDK contextvars — no ids threaded through the loop |

Invariants:
- **T-1** Exactly one TurnTrace per `run_turn` invocation when tracing is
  configured; zero when not (FR-001, FR-004).
- **T-2** A turn that ends via the `MAX_TOOL_ROUNDS` safety valve still
  yields a complete TurnTrace containing all rounds (spec US1 sc. 4).

### LlmCallRun

| Attribute | Source | Notes |
|---|---|---|
| inputs | actual `chat.completions.create` kwargs | wire truth: includes the transient `LANGUAGE_REMINDER` that is never in `session.messages` (US1 sc. 5) |
| outputs | the completion response | content and/or tool_calls |
| token usage | response `usage` block | prompt/completion/total; non-streaming call ⇒ always present (research R5) |

Invariants:
- **L-1** Every LLM request of a traced turn appears; none are synthesized
  or elided (FR-002).
- **L-2** Captured inputs are the as-sent payload, not the persisted
  session (FR-002; the two differ by exactly the `LANGUAGE_REMINDER`
  trailing message).

### ToolRun

| Attribute | Source | Notes |
|---|---|---|
| name | registered tool name (`ToolDef.name`) | not the Python function name (research R3) |
| inputs | arguments received by `_dispatch` | for pre-validation failures: the raw arguments string that failed |
| outputs | the dict `_dispatch` returns | success payload or error dict, byte-equal to what is JSON-encoded into the tool message |

Invariants:
- **O-1** Every `_dispatch` invocation of a traced turn yields exactly one
  ToolRun, including all four error shapes (FR-003).
- **O-2** ToolRun creation never alters the dict returned to the LLM, the
  session, or exception behavior (FR-005).

### Credential exclusion (all run types)

- **C-1** No run's inputs/outputs may contain `DISCOGS_USER_TOKEN`,
  `OPENAI_API_KEY`, or `LANGSMITH_API_KEY` values (FR-008). Structurally
  guaranteed today: secrets live only in `Settings` (`SecretStr`) and the
  HTTP client, never in messages, tool args, or tool payloads. Guarded by
  the extended secrets-hygiene test.

## 2. Configuration entity: `Settings` additions

New fields on `collection_agent.settings.Settings` (all optional — absent
env ⇒ tracing off; VII(a) compliant):

| Field | Type | Env alias | Default |
|---|---|---|---|
| `langsmith_tracing` | `bool` | `LANGSMITH_TRACING` | `False` |
| `langsmith_api_key` | `SecretStr \| None` | `LANGSMITH_API_KEY` | `None` |
| `langsmith_endpoint` | `str \| None` | `LANGSMITH_ENDPOINT` | `None` → SDK default |
| `langsmith_project` | `str` | `COLLECTION_AGENT_LANGSMITH_PROJECT` | `"discogs-collection-agent"` |

Validation rules / derived state:

- **Tracing effective** ⇔ `langsmith_tracing is True` **and**
  `langsmith_api_key is not None`. Evaluated once, at `_build_agent`.
- `langsmith_tracing=True` with no key ⇒ one console notice, tracing
  disabled, chat proceeds (research R6; never exit-code 2).
- `langsmith_project` intentionally does **not** alias `LANGSMITH_PROJECT`
  (research R2): the shared repo `.env` value belongs to `agent/`; the
  collection agent writes its *own* project name to `os.environ` at the
  bridge.

### State transition (process-level, at `_build_agent`)

```text
settings loaded
   │
   ├─ tracing effective ──► export LANGSMITH_* to os.environ
   │                        client = wrap_openai(OpenAI(...))
   │                        @traceable / trace: ACTIVE
   │
   └─ not effective ──────► os.environ untouched
                            client = OpenAI(...)          (identical to today)
                            @traceable / trace: NO-OP
```

There are no runtime transitions after construction: tracing is decided
once per process (a REPL session), never per turn.

## 3. Explicitly unchanged

- `AgentSession.messages` — never contains the `LANGUAGE_REMINDER`; tracing
  reads, never writes, session state.
- `ToolDef` / tool registration / `openai_schema()` — no schema or
  registry changes (the 017 agent-tools contract and its 018/019/020
  amendments are untouched; see contracts/tracing.md §5).
- `WritePlan` lifecycle and the CLI confirmation gate — traced as ordinary
  tool activity (`propose_moves` ToolRun), never driven by tracing.
- Snapshot schema, sync journal, prompts.
