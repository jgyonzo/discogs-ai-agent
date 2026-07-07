# Contract: Collection-Agent Tracing (Observability Surface)

**Feature**: 021-langsmith-tracing · **Date**: 2026-07-07 · **Status**: Draft
**Scope**: `collection-agent/` only. This is a NEW contract; it amends no
existing contract (see §5).

This contract defines the observability surface the collection agent emits
to LangSmith and the configuration that gates it. It is normative for the
implementation and for any future feature that touches the agent loop: a
change that breaks a MUST here is a contract change and needs a documented
amendment.

## §1 Configuration

| Env var | Meaning | Required? |
|---|---|---|
| `LANGSMITH_TRACING` | enable flag (truthy ⇒ on) | no — absent ⇒ tracing off |
| `LANGSMITH_API_KEY` | LangSmith credential (secret) | no — absent ⇒ tracing off (with a notice if the flag is set) |
| `LANGSMITH_ENDPOINT` | override API endpoint | no — absent ⇒ SDK default |
| `COLLECTION_AGENT_LANGSMITH_PROJECT` | LangSmith project for THIS component | no — default `discogs-collection-agent` |

- All values MUST be sourced through `Settings` (pydantic-settings over the
  repo-root `.env`), per Constitution VII(a). The single permitted
  `os.environ` write is the documented bridge at the CLI construction site,
  executed only when tracing is effective.
- **Tracing effective** ⇔ flag truthy AND key present. Any other
  combination MUST behave as tracing-off; flag-without-key additionally
  emits one console notice and MUST NOT exit with a configuration error.
- The component MUST NOT read or write `LANGSMITH_PROJECT` from `.env`:
  that name is reserved for `agent/`. The bridge writes the *component's*
  project value (from `COLLECTION_AGENT_LANGSMITH_PROJECT` / its default)
  into the process env.

## §2 Emitted run tree

When tracing is effective, each `run_turn` invocation MUST emit exactly one
run tree:

- **Root**: run_type `chain`, name `run_turn`; inputs = the user's turn
  text; outputs = the final answer text (including the tool-budget fallback
  answer).
- **LLM child runs**: one per `chat.completions.create` call, carrying the
  as-sent request payload — which includes the transient decision-point
  language reminder that is never persisted to the session — and the
  provider-reported token usage (prompt/completion/total).
- **Tool child runs**: one per `_dispatch` invocation, named with the
  registered tool name, inputs = the arguments received, outputs = the
  exact dict returned to the LLM — success payload **or** any of the four
  error shapes (unknown tool, invalid JSON arguments, argument validation
  failure, tool exception).

When tracing is not effective, zero runs MUST be emitted and zero network
calls made to the tracing service.

## §3 Non-interference guarantees

1. **Behavioral identity**: with tracing on, off, or failing, the agent's
   LLM-visible messages, tool dispatch results, error semantics, session
   state, and the §4 write gate of `contracts/agent-tools.md` (017) MUST be
   identical. Tracing observes; it never participates.
2. **Never-blocking**: trace delivery failures (unreachable endpoint,
   invalid key, timeouts) MUST NOT raise into, fail, or materially delay a
   turn. Delivery is background/batched; final flush rides process exit.
3. **Unwrapped-when-off**: the unconfigured path MUST construct the plain
   OpenAI client with no tracing wrapper object in the call chain.
4. **Test surface**: the pytest suite MUST run with tracing forcibly not
   effective regardless of the developer's shell environment (autouse
   env-scrub), and stub LLM clients MUST never be wrapped.

## §4 Secrets

Run payloads (inputs, outputs, metadata) MUST NOT contain the values of
`DISCOGS_USER_TOKEN`, `OPENAI_API_KEY`, or `LANGSMITH_API_KEY`.
`LANGSMITH_API_KEY` is a `SecretStr` settings field under the repo secrets
constraint: gitignored `.env`, never logged, never persisted to the
snapshot or session.

## §5 Relationship to existing contracts

- `specs/017-discogs-collection-agent/contracts/agent-tools.md` (and its
  018/019/020 amendment deltas): **untouched**. No tool added, removed, or
  reshaped; no prompt change; the write gate is unchanged. Tracing is a new,
  orthogonal surface — hence a new contract file rather than a fourth
  amendment.
- `contracts/discogs-consumption.md`, `contracts/snapshot-schema.md`:
  untouched (sync pipeline out of scope).
- Published DuckDB contracts: not involved (Constitution VI: this component
  does not consume them in the conversational path).
