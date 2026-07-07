# Implementation Plan: LangSmith Tracing for the Collection Agent

**Branch**: `021-langsmith-tracing` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/021-langsmith-tracing/spec.md`

## Summary

Give the collection agent the observability the `agent/` component already
has: every user turn becomes one LangSmith trace tree (LLM calls with token
usage + tool executions nested under it), activated purely by environment
configuration and a strict no-op otherwise. The technical approach (research
R1) is the `langsmith` SDK's plain-OpenAI integration — `wrap_openai` around
the real client at the CLI construction site, a `@traceable` root span on
`Agent.run_turn`, and a `langsmith.trace` tool span around each dispatch —
**not** a LangChain migration; 017 research R2's plain-SDK loop stays the
architecture of record (spec FR-009). Exactly one new dependency
(`langsmith`), zero changes to loop semantics, tools, prompts, or the §4
write gate, and the 213-test offline suite runs unmodified.

**Component(s) touched**: `collection-agent/` only (plan gate requirement).
No ETL, `agent/`, or `frontend/` changes; no DuckDB contract involvement.

## Technical Context

**Language/Version**: Python 3.12 (`collection-agent/pyproject.toml`, `requires-python >=3.12`)
**Primary Dependencies**: existing — `openai>=1.40`, `pydantic>=2.7`, `pydantic-settings>=2.4`, `rich>=13`; new — `langsmith>=0.3` (the single new dependency, FR-009)
**Storage**: none added — snapshot JSON untouched; traces live in LangSmith's cloud, nothing tracing-related is persisted locally
**Testing**: pytest (`cd collection-agent && pytest`), 213 tests at branch point, fully offline — stub LLM clients injected via the 017 injectable-client seam; suite must stay offline and unmodified (FR-006)
**Target Platform**: developer laptop terminal (macOS/Linux), single-owner CLI (`python -m collection_agent chat`)
**Project Type**: CLI component inside the four-component monorepo
**Performance Goals**: tracing adds no user-perceivable turn latency — trace delivery is background/batched; new traces visible in LangSmith ≤ 60 s after turn completion (SC-006)
**Constraints**: strict no-op when unconfigured (FR-004); trace-delivery failure never fails a turn (FR-007); no credentials in trace payloads (FR-008); no LangChain, one new dependency (FR-009); existing tests unmodified and offline (FR-006/SC-003)
**Scale/Scope**: single owner, conversational cadence (≤ ~10 LLM calls + tool executions per turn at `MAX_TOOL_ROUNDS = 8`); 300–1k-record snapshot payloads inside traced messages

### Load-bearing existing facts

- `cli.py::_build_agent` is the only place the **real** OpenAI client is
  constructed; tests construct `Agent` directly with stubs and never enter
  `_build_agent`. This seam is why FR-006 costs nothing (017 design).
- `cli.py:152` already documents the env-bridging pattern this feature
  reuses: *"the OpenAI SDK only reads os.environ; our key comes from the
  repo .env via pydantic-settings, so pass it explicitly."* The `langsmith`
  SDK has the same shape (reads `os.environ`, not `.env`), so tracing config
  must flow settings → SDK explicitly (research R2).
- The owner's repo-root `.env` **already defines** `LANGSMITH_TRACING`,
  `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` (consumed
  by `agent/` through LangChain's implicit env detection). Reusing these
  names means zero new required setup for the owner — but the project name
  must NOT be inherited (research R2): collection-agent traces get their own
  LangSmith project so the two components' traces don't interleave.
- `tests/conftest.py::settings` builds `Settings(_env_file=None, ...)` —
  tests never read the real `.env`, so new tracing fields default to
  disabled in every existing test without modification.
- `agent.py::run_turn` sends `[*session.messages, LANGUAGE_REMINDER]` — the
  wire payload differs from the persisted session by design (020 finding 7).
  Client-level wrapping (`wrap_openai`) captures the wire payload, which is
  exactly what US1 scenario 5 requires; session-level instrumentation would
  lie about what the model saw.

## Constitution Check

*GATE: evaluated against Constitution v1.2.1 before Phase 0; re-checked after Phase 1 design (below).*

| Principle / Constraint | Verdict | Notes |
|---|---|---|
| I. Layered, contract-first data architecture | N/A | No pipeline layer touched; no published contract changed. |
| II. Streaming, bounded memory | N/A | No XML/Parquet processing touched. |
| III. Reproducible runs (manifest/logs) | N/A | ETL-scoped; collection-agent sync journal untouched. |
| IV. Data quality gates | N/A | No layer outputs changed. |
| V. Agent-friendly analytics surface | N/A | DuckDB surface untouched. |
| VI. Components & Contracts | **PASS** | Work lives entirely in `collection-agent/`; the new dependency lands in its own `pyproject.toml`; no cross-component imports (guarded by existing `test_no_cross_imports.py`). Sharing `LANGSMITH_*` env-var *names* with `agent/`'s `.env` usage is configuration convention, not code coupling — each component still runs end-to-end without the other. |
| VII(a). Configuration from settings | **PASS (design-critical)** | All tracing config enters through new `Settings` fields (`pydantic-settings`); no hardcoded endpoints, project names, or flags. The settings → `os.environ` bridge at the CLI construction site is the documented consequence of the SDK reading only `os.environ` — same pattern, same justification, as the existing OpenAI `api_key` pass-through (`cli.py:152`). Default project name is a `Settings` default, not a literal at the call site. |
| VII(b). Prompt-authoring discipline | **PASS** | Zero prompt changes; `prompts/system.md` and the rendered `{attribute_block}` untouched. |
| VII(c). Read-only runtime mechanics | N/A | No read-only resource introduced. |
| Secrets constraint | **PASS** | `LANGSMITH_API_KEY` becomes a `SecretStr` settings field, `.env`-sourced, gitignored as ever; never logged, never persisted, excluded from trace payloads (FR-008). Existing `test_secrets_hygiene.py` pattern extends to the new secret. |
| Scope guardrails | **PASS** | Conversational loop only; sync pipeline explicitly out of scope (spec Assumptions). No ETL/agent-v1 scope smuggled. |

**Initial gate: PASS — no violations, Complexity Tracking not required.**

## Project Structure

### Documentation (this feature)

```text
specs/021-langsmith-tracing/
├── spec.md              # /speckit-specify output (done)
├── checklists/
│   └── requirements.md  # spec quality gate (done, all pass)
├── plan.md              # This file
├── research.md          # Phase 0 output (R1–R6)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── tracing.md       # Phase 1 output — observability contract
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
collection-agent/
├── pyproject.toml                        # + "langsmith>=0.3" dependency
├── src/collection_agent/
│   ├── settings.py                       # + 4 tracing fields (Settings)
│   ├── cli.py                            # _build_agent: env bridge + wrap_openai
│   └── agent.py                          # @traceable on run_turn; tool span in _dispatch
└── tests/
    ├── conftest.py                       # + autouse LANGSMITH_* env-scrub fixture
    └── unit/
        ├── test_tracing_noop.py          # NEW — no-op & wiring guarantees
        └── test_secrets_hygiene.py       # + LANGSMITH_API_KEY coverage
```

**Structure Decision**: existing `collection-agent/` src-layout is extended
in place — three source files touched, no new modules beyond one new test
file. No other component directory is modified.

## Design Outline

*(Detail and rejected alternatives in research.md R1–R6; entities in
data-model.md; the normative surface in contracts/tracing.md.)*

1. **Dependency** — add `langsmith>=0.3` to `collection-agent/pyproject.toml`
   (FR-009: exactly one).
2. **Settings** (`settings.py`, VII(a)) — new fields, all optional, all
   defaulting to "tracing off":
   `langsmith_tracing: bool = False` (`LANGSMITH_TRACING`),
   `langsmith_api_key: SecretStr | None` (`LANGSMITH_API_KEY`),
   `langsmith_endpoint: str | None` (`LANGSMITH_ENDPOINT`),
   `langsmith_project: str = "discogs-collection-agent"`
   (`COLLECTION_AGENT_LANGSMITH_PROJECT` — deliberately NOT
   `LANGSMITH_PROJECT`, research R2, so `agent/` traces and collection-agent
   traces land in separate LangSmith projects).
3. **CLI construction site** (`cli.py::_build_agent`) — when
   `settings.langsmith_tracing` and an API key are present: export the
   `LANGSMITH_*` values from settings into `os.environ` (the documented
   bridge; the SDK and its `@traceable` gating read only `os.environ`), then
   build the real client as `wrap_openai(OpenAI(...))`. Otherwise construct
   the client exactly as today — no wrapper object in the unconfigured path.
   Config error (tracing on, key missing) degrades to a one-line console
   notice + tracing off, never an exit (FR-007 spirit: observability never
   blocks the tool).
4. **Turn root span** (`agent.py`) — `@traceable(name="run_turn",
   run_type="chain")` on `Agent.run_turn`. No-op when `LANGSMITH_TRACING`
   is absent from the process env (which is always true for tests, research
   R4). The wrapped client's LLM calls auto-nest under it via contextvars,
   carrying the as-sent payload (incl. the transient `LANGUAGE_REMINDER`)
   and provider-reported token usage (research R5).
5. **Tool spans** (`agent.py::_dispatch`) — wrap the dispatch body in
   `langsmith.trace(name=<tool name>, run_type="tool", inputs=<validated
   args>)`, recording the returned payload — including the four error-dict
   shapes — as span outputs (FR-003). Dispatch semantics (error dicts, no
   raises) are byte-identical with tracing on or off (FR-005).
6. **Test hardening** — autouse conftest fixture deletes `LANGSMITH_*` from
   the environment for every test (guards a developer shell that exported
   them; research R4); new `test_tracing_noop.py` asserts the unconfigured
   path builds an unwrapped client, that `run_turn`/`_dispatch` behavior is
   unchanged, and that no tracing env leaks into stub-client requests; one
   `test_secrets_hygiene.py` addition covers the new secret. Existing tests:
   zero edits (FR-006).
7. **Docs** — `collection-agent/README.md` gains the tracing env-var table
   and a "view your traces" pointer (quickstart.md is the feature-local
   version).

## Post-Design Constitution Re-Check

Re-evaluated after Phase 1 artifacts (research.md, data-model.md,
contracts/tracing.md, quickstart.md): verdicts unchanged — **PASS**. The
design added no new component coupling (VI), kept every runtime value
settings-sourced with the `os.environ` bridge documented alongside its
consequence (VII(a), mirroring the existing OpenAI-key comment), touched no
prompts (VII(b)), and introduced no read-only-resource mechanics (VII(c)).
Complexity Tracking remains empty.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
