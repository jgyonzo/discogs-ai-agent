# Research: LangSmith Tracing for the Collection Agent

**Feature**: 021-langsmith-tracing · **Date**: 2026-07-07
**Sources**: `langsmith` Python SDK (plain-OpenAI integration: `wrap_openai`,
`@traceable`, `trace` context manager), existing component code
(`agent.py`, `cli.py`, `settings.py`, `tests/conftest.py`), owner's
repo-root `.env` (variable names only), 017 research R2 (architecture of
record), 020 replay finding 7 (transient reminder).

---

## R1 — Instrumentation approach: `langsmith` SDK over the plain OpenAI client

**Decision**: Use the `langsmith` SDK's native plain-OpenAI integration:
`langsmith.wrappers.wrap_openai` around the real client, `@traceable` for
the turn root span, `langsmith.trace` for tool spans. No framework change.

**Rationale**:
- The spec's target service is LangSmith (owner decision — same pane of
  glass as `agent/`), and the `langsmith` SDK is its first-party client. It
  explicitly supports non-LangChain apps: `wrap_openai` patches
  `chat.completions.create` to emit an `llm`-type run with the exact request
  kwargs and the provider-reported `usage` block; `@traceable` / `trace`
  build the surrounding tree via `contextvars`, so nesting is automatic —
  no run-id threading through the loop.
- The 017 architecture (deterministic tools, injectable client, CLI-owned
  write gate) is load-bearing for four merged features' guarantees. The SDK
  approach observes it without restructuring anything.
- One dependency, ~10 lines of integration — satisfies FR-009 by
  construction.

**Alternatives considered**:
- **LangChain/LangGraph migration** (the option that prompted this feature's
  scoping conversation): rejected. It reverses 017 research R2 for zero
  functional gain — tracing is available without it — and every deliberate
  deviation in the loop (transient `LANGUAGE_REMINDER` sent-not-persisted,
  four-tier error-dict dispatch, session state threaded into tools,
  `propose_moves`-only write gate) would need custom callbacks/adapters to
  survive the framework's own loop. Net complexity up, behavioral-regression
  risk up, and the spec forbids it (FR-009).
- **OpenTelemetry + OTLP export to LangSmith**: LangSmith accepts OTel
  traces, but the mapping to LangSmith's LLM-native run model (token usage,
  message payloads, run types) is manual attribute-schema work, and it adds
  two+ dependencies (`opentelemetry-sdk`, exporter). Right answer only if
  the owner wanted vendor-neutral tracing; they asked for LangSmith parity.
- **Manual `RunTree` construction / raw LangSmith REST**: maximal control,
  but re-implements exactly what `wrap_openai`/`traceable` already do
  (batching, flushing, nesting, usage extraction). More code to get the same
  traces.

---

## R2 — Configuration surface: settings fields + explicit `os.environ` bridge; a dedicated project name

**Decision**: Four new `Settings` fields (VII(a)):

| Field | Env var | Default |
|---|---|---|
| `langsmith_tracing: bool` | `LANGSMITH_TRACING` | `False` |
| `langsmith_api_key: SecretStr \| None` | `LANGSMITH_API_KEY` | `None` |
| `langsmith_endpoint: str \| None` | `LANGSMITH_ENDPOINT` | `None` (SDK default endpoint) |
| `langsmith_project: str` | `COLLECTION_AGENT_LANGSMITH_PROJECT` | `"discogs-collection-agent"` |

At the CLI construction site, when tracing is enabled and a key is present,
export these values into `os.environ` (`LANGSMITH_TRACING`,
`LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` if set, `LANGSMITH_PROJECT` ←
`settings.langsmith_project`) before building the wrapped client.

**Rationale**:
- The `langsmith` SDK — including the `@traceable` no-op gate — reads
  `os.environ`, not `.env`. The component's config pipeline is
  pydantic-settings over the repo-root `.env` (`cli.py:152` documents this
  exact mismatch for the OpenAI key and resolves it with an explicit
  pass-through). Bridging settings → `os.environ` at one site keeps VII(a)
  intact: values are *sourced* from settings; the env write is a documented
  transport to an SDK that offers no other global configuration point for
  decorator-gated tracing.
- Reusing the repo-standard variable names (`LANGSMITH_TRACING`,
  `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`) means the owner's existing
  `.env` — which already defines all three for the `agent/` component —
  lights this feature up with **zero new required setup** (FR-004's "no new
  required config" holds: absent vars ⇒ no-op).
- The **project name is deliberately NOT shared**. `agent/` consumes
  `LANGSMITH_PROJECT` implicitly via LangChain env detection; if the
  collection agent inherited it, both components' traces would interleave in
  one LangSmith project. A dedicated `COLLECTION_AGENT_LANGSMITH_PROJECT`
  (default `discogs-collection-agent`) gives each component its own project
  in the same organization — same pane of glass, separate panes.

**Alternatives considered**:
- **Let the SDK read the shell environment directly (no settings fields)**:
  rejected — violates VII(a) (runtime behavior keyed to config that never
  passes through `Settings`), and `.env` values would silently *not* apply
  because nothing exports `.env` to the shell; tracing would only work for
  users who hand-export vars, contradicting the component's documented
  config story.
- **Pass a `langsmith.Client(api_key=…, api_url=…)` object everywhere
  instead of the env bridge**: `wrap_openai` accepts a client, but the
  `@traceable`/`trace` call sites in `agent.py` bind at import/decoration
  time, before any `Settings` instance exists; threading a client object
  into the `Agent` would grow its constructor surface for a pure
  observability concern. The env bridge configures all three integration
  points at one site.
- **Inherit `LANGSMITH_PROJECT`**: rejected per above (trace interleaving
  with `agent/`).

---

## R3 — Instrumentation points: construction-site wrap + two spans inside `agent.py`

**Decision**:
1. `cli.py::_build_agent` — `llm_client=wrap_openai(OpenAI(api_key=…))`
   only on the configured path; the unconfigured path constructs the client
   exactly as today (no wrapper object at all).
2. `agent.py::Agent.run_turn` — decorated `@traceable(name="run_turn",
   run_type="chain")`; the turn's user text is the traced input, the final
   answer the traced output.
3. `agent.py::Agent._dispatch` — body wrapped in
   `with langsmith.trace(name=<tool name>, run_type="tool",
   inputs=<parsed/validated args>)`, ending with the returned payload
   (result **or** error dict) as outputs.

**Rationale**:
- `_build_agent` is the only construction site of a real client (017's
  injectable seam); wrapping there and only there is what makes FR-006 free
  — stubs constructed by tests never pass through it.
- Wrapping at the **client** level (not around session state) is the only
  way to satisfy US1 scenario 5: `run_turn` sends
  `[*messages, LANGUAGE_REMINDER]` — the wire payload — and `wrap_openai`
  records the actual call kwargs, transient reminder included. Any
  instrumentation that serialized `session.messages` would misrepresent
  what the model saw (the exact failure 020 finding 7 fought).
- `_dispatch` is the single chokepoint through which every tool execution
  and all four error shapes (unknown tool, bad JSON, validation error, tool
  exception) already flow — one span site covers FR-003 exhaustively,
  including the error payloads *as the LLM receives them*.
- `langsmith` becomes a direct import of `agent.py`. Acceptable: it is a
  declared runtime dependency (the one FR-009 allows), and both `traceable`
  and `trace` are documented no-ops when tracing is disabled — the module
  imports and runs offline (tests) without a LangSmith account or network.

**Alternatives considered**:
- **Zero-touch `agent.py` (wrap only at the CLI)**: cannot produce tool
  spans or a per-turn root — client wrapping alone yields flat, per-LLM-call
  traces with no turn grouping. Fails FR-001/FR-003.
- **`@traceable` on each tool `fn` at registration** (decorating
  `ToolDef.fn`): spans would carry the Python function name, not the
  registered tool name; misses `_dispatch`'s pre-validation error paths
  (unknown tool / bad JSON / validation failure), which are precisely the
  interesting ones in a postmortem. Rejected.
- **A separate `tracing.py` indirection module with graceful
  import-or-stub**: defensive shimming for a hard dependency that is
  guaranteed installed; adds a layer with no consumer benefit. Rejected —
  YAGNI.

---

## R4 — No-op and offline-test guarantees

**Decision**: Rely on the SDK's documented gating — `@traceable` /
`trace` / `wrap_openai` create and send no runs unless tracing is enabled
in the process env — plus two belt-and-suspenders measures:
(a) an **autouse conftest fixture** that `monkeypatch.delenv`s every
`LANGSMITH_*` variable for every test, and (b) the unconfigured CLI path
never wraps the client at all.

**Rationale**:
- Tests already construct `Settings(_env_file=None, …)` and stub clients,
  so no test crosses a configured tracing boundary today. The autouse scrub
  closes the one residual hole: a developer (or CI) shell where
  `LANGSMITH_*` happens to be exported would otherwise flip `@traceable`
  live during a test run — sending test traffic to a real LangSmith project
  and violating SC-003's zero-network guarantee. The fixture makes the
  offline property unconditional rather than environmental.
- Leaving the unconfigured client unwrapped (rather than "wrap always,
  gate at send time") keeps the untraced production path byte-identical to
  today's — the strongest possible form of FR-005's no-behavior-change and
  trivially verifiable in a unit test (`assert client is the plain OpenAI
  instance`).
- New tests live in a new file (`test_tracing_noop.py`); existing tests are
  untouched (FR-006). Adding an autouse fixture to `conftest.py` adds
  behavior *around* existing tests without editing any of them — within the
  spec's letter and intent (no test needs modification to accommodate the
  feature; the fixture is protection, not accommodation).

**Alternatives considered**:
- **Trust the SDK gating alone**: leaves SC-003 hostage to the developer's
  shell. Rejected.
- **A pytest network-block plugin** (e.g. socket disabling): broader hammer
  than needed and a new dev dependency; the suite's offline property has
  been maintained by construction so far. Rejected for this feature (could
  be a future hardening feature repo-wide).

---

## R5 — Token usage capture

**Decision**: No custom code. `wrap_openai` records the OpenAI response's
`usage` block (prompt/completion/total tokens) on each `llm` run; LangSmith
aggregates per-trace totals natively (US2/SC-002).

**Rationale**: The loop calls `chat.completions.create` non-streaming
(`agent.py:124`), so `usage` is present on every response object — the
wrapper's happy path. Nothing in the component computes or logs tokens
itself, so there is no drift risk against a second bookkeeping system.

**Alternatives considered**: manual usage extraction into a local ledger
(out of scope — the spec wants visibility in LangSmith, not a second cost
store; the `agent/` component's `cost_logger` analog is a different,
service-shaped need).

---

## R6 — Failure semantics and delivery latency

**Decision**: Accept the SDK's background-batching model as the FR-007
mechanism: runs are queued in-process and posted by a background thread;
delivery failures (bad key, unreachable endpoint, timeouts) surface as SDK
log lines, never as exceptions in the turn path. Flush-on-exit is the SDK's
`atexit` hook — no explicit flush call in the REPL loop. The
tracing-on-but-key-missing configuration degrades at `_build_agent` to a
single console notice + tracing disabled (never a config-error exit — the
agent must stay usable when only observability is misconfigured).

**Rationale**: satisfies FR-007 (turns never blocked/failed by tracing) and
SC-005 (invalid key ⇒ conversation proceeds) with zero custom retry code;
background posting typically lands traces in seconds, comfortably inside
SC-006's 60 s. The REPL is long-lived, so batch delivery is continuous;
`atexit` covers the final partial batch on `/exit`.

**Alternatives considered**:
- **Synchronous flush per turn**: guarantees SC-006 tightly but couples turn
  latency to LangSmith availability — exactly what FR-007 forbids. Rejected.
- **Exit-code 2 (config error) when tracing enabled but key absent**:
  consistent with the CLI's strictness about *required* config, but tracing
  is optional infrastructure; failing chat for it inverts the feature's
  no-footprint principle. Rejected in favor of notice-and-continue.

---

## Resolved-unknowns summary

| Unknown | Resolution |
|---|---|
| SDK vs LangChain vs OTel | `langsmith` SDK plain-OpenAI integration (R1) |
| Config surface under VII(a) | 4 `Settings` fields + one-site `os.environ` bridge (R2) |
| Project-name collision with `agent/` | dedicated `COLLECTION_AGENT_LANGSMITH_PROJECT`, default `discogs-collection-agent` (R2) |
| Span topology | `run_turn` chain root; client-level `llm` runs; `_dispatch` tool spans (R3) |
| Wire-truth requirement (US1 sc. 5) | client-level wrapping captures as-sent kwargs incl. `LANGUAGE_REMINDER` (R3) |
| Offline-test guarantee | SDK gating + autouse env-scrub + unwrapped unconfigured path (R4) |
| Token usage | provider `usage` via `wrap_openai`, no custom code (R5) |
| Failure/latency semantics | background batching, notice-and-continue degradation, `atexit` flush (R6) |

No `NEEDS CLARIFICATION` items remain.
