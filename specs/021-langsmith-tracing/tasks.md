# Tasks: LangSmith Tracing for the Collection Agent

**Input**: Design documents from `/specs/021-langsmith-tracing/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R6), data-model.md, contracts/tracing.md, quickstart.md

**Tests**: included — the spec makes test guarantees load-bearing (FR-006, SC-003: 213-test suite stays offline and unmodified; component convention: no live API calls in tests). Live-replay validation tasks follow the repo's SC-audit convention (017 SC-002, 019 SC-001/2, 020 SC-002).

**Organization**: by user story. US1 (P1, trace tree) and US3 (P1, zero footprint) are co-equal P1s; US1 is sequenced first because US3's verification targets the instrumentation US1 introduces. US2 (P2, token usage) is expected to be zero-code (research R5) — its phase is pure verification.

**Component**: `collection-agent/` only. All paths below are repo-relative.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = trace tree per turn · US2 = token usage · US3 = zero footprint

---

## Phase 1: Setup

**Purpose**: the single new dependency (FR-009).

- [X] T001 Add `"langsmith>=0.3"` to `[project].dependencies` in `collection-agent/pyproject.toml` (under a `# 021 — tracing` comment, matching the file's per-feature comment style) and reinstall the editable env (`cd collection-agent && pip install -e ".[dev]"`); verify `python -c "from langsmith import traceable, trace; from langsmith.wrappers import wrap_openai"` succeeds

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the configuration entity every story reads, plus the test-suite hardening that must be in place before any instrumentation lands (research R4: no instrumentation may ship without the offline guarantee).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add the four tracing fields to `Settings` in `collection-agent/src/collection_agent/settings.py` per data-model.md §2: `langsmith_tracing: bool = False` (alias `LANGSMITH_TRACING`), `langsmith_api_key: SecretStr | None = None` (alias `LANGSMITH_API_KEY`), `langsmith_endpoint: str | None = None` (alias `LANGSMITH_ENDPOINT`), `langsmith_project: str = "discogs-collection-agent"` (alias `COLLECTION_AGENT_LANGSMITH_PROJECT` — deliberately NOT `LANGSMITH_PROJECT`, research R2); add a `# --- LangSmith tracing (021) ---` section comment explaining the project-name separation from `agent/`
- [X] T003 Add unit tests for the new fields in `collection-agent/tests/unit/test_settings_tracing.py` (new file): defaults ⇒ tracing off (`langsmith_tracing is False`, key `None`, project `"discogs-collection-agent"`); env aliases populate each field; `COLLECTION_AGENT_LANGSMITH_PROJECT` is honored while a `LANGSMITH_PROJECT` env var is ignored by `Settings`; `langsmith_api_key` is a `SecretStr` (repr does not leak the value)
- [X] T004 [P] Add an autouse fixture in `collection-agent/tests/conftest.py` that `monkeypatch.delenv`s every `LANGSMITH_*` variable (`LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`, `LANGSMITH_PROJECT`) for every test, with a docstring citing FR-006/SC-003 (a developer shell with exported LangSmith vars must never flip `@traceable` live during a test run); do NOT modify any existing fixture or test

**Checkpoint**: config surface exists and the suite is tracing-proof — instrumentation can now land safely.

---

## Phase 3: User Story 1 — Review a conversation turn as one trace tree (Priority: P1) 🎯 MVP

**Goal**: with tracing configured, every `run_turn` emits one LangSmith trace tree — `run_turn` chain root, client-level `llm` runs carrying the as-sent payload (incl. the transient `LANGUAGE_REMINDER`) and one `tool` span per `_dispatch` (incl. all four error-dict shapes) — per contracts/tracing.md §2.

**Independent Test**: quickstart §2–§3 — a scripted conversation produces the expected trace trees in the `discogs-collection-agent` LangSmith project.

### Implementation for User Story 1

- [X] T005 [US1] Decorate `Agent.run_turn` with `@traceable(name="run_turn", run_type="chain")` in `collection-agent/src/collection_agent/agent.py` (import `traceable` at module top); add a comment stating the no-op contract (inactive unless `LANGSMITH_TRACING` is in the process env — research R4) and update the module docstring's "plain SDK" paragraph to mention the observe-only tracing layer (021)
- [X] T006 [US1] Wrap the dispatch body in `Agent._dispatch` in `collection-agent/src/collection_agent/agent.py` with a `langsmith.trace(name=<registered tool name>, run_type="tool", inputs=...)` context recording the returned dict (success payload or any of the four error shapes) as outputs before returning it — the unknown-tool path uses the requested name; dispatch semantics (error dicts, no raises, session mutation by tools) must be byte-identical (contracts/tracing.md §3.1, spec FR-003/FR-005)
- [X] T007 [P] [US1] Implement the tracing-effective gate and env bridge in `_build_agent` in `collection-agent/src/collection_agent/cli.py`: when `settings.langsmith_tracing` and `settings.langsmith_api_key` are both set, export `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT` (only if set), and `LANGSMITH_PROJECT` ← `settings.langsmith_project` into `os.environ`, then build `llm_client=wrap_openai(OpenAI(api_key=...))`; otherwise construct the plain `OpenAI` client exactly as today (no wrapper object — research R4); comment the bridge with the same justification pattern as the existing OpenAI-key pass-through at `cli.py:152` (VII(a): values sourced from settings; the SDK reads only `os.environ`)
- [X] T008 [US1] Add behavioral-identity tests in `collection-agent/tests/unit/test_tracing_noop.py` (new file): with tracing env absent (guaranteed by T004), a stub-client `Agent` (reuse the stub pattern from `tests/integration/test_agent_loop.py`) produces identical `run_turn` answers, identical tool dispatch results, and identical error dicts for all four `_dispatch` error shapes as before instrumentation; `MAX_TOOL_ROUNDS` fallback text unchanged; no `LANGSMITH_*` key appears in `os.environ` after a turn
- [X] T009 [US1] Live SC-001 / US1-scenario-5 audit (quickstart §2–§3): with the repo `.env`'s real LangSmith key, run the 3-turn scripted conversation (no-tool turn, multi-tool turn, tool-error turn — force the error with an unknown-tool or invalid-arg prompt); verify in LangSmith: exactly 3 root traces; every LLM call and tool execution nested with correct names/args/payloads; the traced request payload shows the trailing `LANGUAGE_REMINDER` (wire truth); record findings (trace URLs + screenshots optional) in a "Live validation" note appended to `specs/021-langsmith-tracing/quickstart.md`

**Checkpoint**: US1 fully functional — traces reviewable in LangSmith; MVP deliverable.

---

## Phase 4: User Story 3 — Zero footprint when unconfigured (Priority: P1)

**Goal**: unconfigured ⇒ strict no-op (unwrapped client, no network, no warnings, behavior identical to `main`); misconfigured or failing tracing never blocks a turn (contracts/tracing.md §3, spec FR-004/FR-005/FR-007).

**Independent Test**: quickstart §4–§5 — offline suite passes with zero LangSmith traffic; chat works unchanged without config and with a bogus key.

### Implementation for User Story 3

- [X] T010 [US3] Add the degraded-config path to `_build_agent` in `collection-agent/src/collection_agent/cli.py`: `langsmith_tracing=True` but no API key ⇒ print one dim console notice ("tracing enabled but LANGSMITH_API_KEY is not set — continuing without tracing"), leave `os.environ` untouched, build the plain unwrapped client; never exit with `EXIT_CONFIG` for tracing-only misconfiguration (research R6, SC-005 spirit)
- [X] T011 [US3] Extend `collection-agent/tests/unit/test_tracing_noop.py` with construction-site wiring tests, calling `_build_agent` with isolated `Settings` (dummy OpenAI key, tmp snapshot path — reuse the conftest `settings` fixture pattern): (a) tracing unconfigured ⇒ `agent.llm` is a plain `openai.OpenAI` instance with no tracing wrapper and `os.environ` gains no `LANGSMITH_*` keys; (b) flag-without-key ⇒ same as (a) plus the notice is emitted (capture rich console output); (c) flag+key set ⇒ `os.environ` carries the four bridged values with `LANGSMITH_PROJECT == "discogs-collection-agent"` and the client is wrapped (assert via `wrap_openai`'s distinguishing attribute, e.g. the patched `create` no longer being the plain SDK bound method — pick the cheapest stable check); monkeypatch-restore env in all cases
- [X] T012 [US3] Full-suite offline verification (SC-003/FR-006): run `cd collection-agent && env -u LANGSMITH_TRACING -u LANGSMITH_API_KEY -u LANGSMITH_ENDPOINT -u LANGSMITH_PROJECT pytest` — all tests pass with no LangSmith network traffic; then verify via `git diff main -- collection-agent/tests` that no existing test function was modified (only `conftest.py` additions and the two new test files)
- [X] T013 [US3] Live SC-004/SC-005 audit (quickstart §4–§5): (a) comment out the LangSmith vars in `.env`, run a short chat — behavior identical to `main`, no tracing notice, nothing lands in LangSmith; (b) set `LANGSMITH_API_KEY` to a bogus value, chat — every turn completes normally (at most background delivery-failure log lines), then restore `.env`; append results to the quickstart "Live validation" note

**Checkpoint**: both P1 stories hold — traces when configured, provably zero footprint when not.

---

## Phase 5: User Story 2 — Track token usage per turn (Priority: P2)

**Goal**: provider-reported token usage visible on every traced LLM call and aggregable per turn (spec FR-002/SC-002). Expected zero-code: `wrap_openai` captures the non-streaming `usage` block natively (research R5).

**Independent Test**: quickstart §3 token checks.

### Implementation for User Story 2

- [X] T014 [US2] Live SC-002 audit: on the T009 traces (or a fresh traced conversation), verify every LLM run carries prompt/completion/total token counts matching the provider `usage` block, and per-trace totals render in the LangSmith project view; append results to the quickstart "Live validation" note. If usage is missing on any run, STOP — that falsifies research R5; amend research.md and plan a fix task before proceeding (do not hand-compute tokens)

**Checkpoint**: all three user stories independently validated.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T015 [P] Extend `collection-agent/tests/unit/test_secrets_hygiene.py` to cover the new secret per its existing pattern: `LANGSMITH_API_KEY` is `SecretStr`-typed, never appears in `repr(settings)`, and is absent from tool payloads / session messages (FR-008, contracts/tracing.md §4)
- [X] T016 [P] Document tracing in `collection-agent/README.md`: env-var table (the four vars, defaults, "absent ⇒ no-op"), the project-name separation from `agent/`, a "review your traces" pointer to the LangSmith project, and the one-line failure-tolerance statement (tracing never blocks a turn)
- [X] T017 Final gate: run `cd collection-agent && pytest` (full suite, tracing vars scrubbed by the T004 fixture), record the new total test count (baseline 213) for the post-merge CLAUDE.md/README refresh, and re-verify the contracts/tracing.md §3 guarantees checklist against the implementation
- [X] T018 Run the complete quickstart.md acceptance-mapping table end-to-end (SC-001…SC-006 — T009/T013/T014 cover most; fill any gap, notably SC-006's ≤60 s visibility timing) and mark each SC pass/fail in the quickstart "Live validation" note

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: none — start immediately
- **Foundational (P2)**: needs T001 (langsmith importable for nothing yet, but the editable reinstall); T002 → T003; T004 independent
- **US1 (P3)**: needs Phase 2 complete (T005/T006 need T001; T007 needs T002; T008 needs T004's scrub guarantee)
- **US3 (P4)**: needs US1's T007 (T010 refines the same `_build_agent` gate); T011 → after T010; T012/T013 → after all code tasks
- **US2 (P5)**: verification only — needs US1 live (T009)
- **Polish (P6)**: T015/T016 anytime after Phase 2; T017/T018 last

### Task-level notes

- Same-file sequences (no [P]): T005 → T006 (`agent.py`); T007 → T010 (`cli.py`); T008 → T011 (`test_tracing_noop.py`)
- Live tasks T009/T013/T014/T018 need the owner's real LangSmith key and OpenAI key — interactive terminal sessions, not CI

### Parallel Opportunities

```text
Phase 2:  T002→T003  ∥  T004
Phase 3:  (T005→T006)  ∥  T007          # agent.py vs cli.py
Phase 6:  T015  ∥  T016
```

---

## Implementation Strategy

**MVP first (US1)**: T001–T009 delivers reviewable traces end-to-end — stop and validate in LangSmith before hardening. **Then US3** (T010–T013) locks the zero-footprint guarantees the suite must carry forever. **US2** (T014) is a checkbox if research R5 holds. Total: 18 tasks, 3 of them [P]-parallelizable pairs, 4 live-validation tasks following the repo's SC-audit convention.

Suggested commit grain (owner convention — split by concern): Phase 1+2 as "feat(021): tracing config + test hardening"; Phase 3 as "feat(021): turn/tool/LLM trace instrumentation"; Phase 4 as "feat(021): no-op + degraded-config guarantees"; Phase 6 as "docs/tests(021): hygiene, README, final gates".
