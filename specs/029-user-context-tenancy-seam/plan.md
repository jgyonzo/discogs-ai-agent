# Implementation Plan: User-context tenancy seam

**Branch**: `029-user-context-tenancy-seam` (worked on `claude/collection-agent-roadmap-boujgu`) | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/029-user-context-tenancy-seam/spec.md`

## Summary

Give the collection agent's serving runtime a place where "this belongs to
that user" lives, without changing anything the owner can observe. A new
`tenancy/` package adds a **user context** (one user's settings view, Discogs
credential, snapshot store, scan session, chat, sync runner and LLM handle)
and a **context registry** that builds contexts lazily. Each context owns its
own web app instance built by the unchanged `create_web_app`, so per-user
chat busy-locks, scan supersede and sync occupancy fall out of the existing
closures with a zero-line diff in `scan/` and `web/`. Per-user values reach
the existing code as an effective settings view; the Discogs credential
becomes an `httpx.Auth` strategy; the rate-limit state becomes a shareable
budget owned by the registry. `serve` is recomposed through the local
context. One new setting, zero new dependencies, no pre-existing test
modified.

**Component(s) touched**: `collection-agent` only. `etl/`, `agent/`,
`frontend/` untouched; eval pipeline, vision prompt, static page, `scan/` and
`web/` packages untouched.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI + uvicorn, httpx, openai SDK, langsmith, pydantic / pydantic-settings — **zero new dependencies** (`httpx.Auth` is the credential extension point)
**Storage**: existing file artifacts only. Implicit local user: unchanged paths. Other users: `data/users/<user_id>/` with the same file set and formats. No database.
**Testing**: pytest, `cd collection-agent && pytest`; FastAPI TestClient, `FakeDiscogsClient`, `httpx.MockTransport`, stub LLMs; no live API calls (639 tests today; about +50 expected)
**Target Platform**: owner's machine or the 027 container, trusted home LAN — unchanged
**Project Type**: single component — CLI-launched web service inside `collection-agent/`
**Performance Goals**: none new. Context lookup is a dictionary read under a lock; app construction happens once per user.
**Constraints**: local behavior byte-identical; all pre-existing tests pass unmodified; no route input selects a user; a non-implicit context can never use the owner's credential; one worker process
**Scale/Scope**: up to ~10 user contexts in one process; 1 new package (3 modules), 4 edited modules, 1 new setting, 3 contract documents (1 new, 2 amendments covering 5 contracts)

## Constitution Check

*Constitution v1.2.1.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Layered contract-first data | N/A–PASS | No ETL layer touched. The seam is contract-first: NEW `contracts/user-context.md` plus amendments written at plan time |
| II. Streaming/bounded memory | N/A | No XML/pipeline work |
| III. Reproducible runs | N/A–PASS | ETL-scoped; sync keeps its journaled, resumable semantics, now per snapshot path |
| IV. Data quality gates | N/A | No layer outputs changed |
| V. Agent-friendly surface | N/A | Published DuckDB untouched |
| VI. Components & contracts | PASS | `collection-agent` only; no cross-component imports; no new component (the new web client is D2 and will carry the constitution amendment) |
| VII(a) Config sources | PASS | One new settings field (`COLLECTION_AGENT_USERS_DIR`); per-user values are settings-sourced through the effective view; user-id grammar and the reserved id are domain constants, like 025's barcode length |
| VII(b) Prompt authoring | PASS | No prompt touched |
| VII(c) Read-only mechanics | N/A–PASS | No read-only resource introduced. Daemon sync thread semantics unchanged; disposal consequence documented (research R10) |
| Secrets constraint | PASS | Sanctioned `get_secret_value` sites stay at three, in the same files; non-implicit settings views carry no credential; audit passes unmodified |
| Workflow gates | PASS | Spec → plan artifacts committed per phase; component named above |

**Post-design re-check**: PASS — the design added no violations; Complexity
Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/029-user-context-tenancy-seam/
├── spec.md              # + clarifications recorded at plan time
├── plan.md              # this file
├── research.md          # R1–R13
├── data-model.md        # entities, effective settings, layout, errors
├── quickstart.md        # run + owner validation checklist
├── contracts/
│   ├── user-context.md                        # NEW contract
│   ├── amendment-017-discogs-consumption-5.md # credential strategy + shared budget
│   └── amendment-scope-per-user.md            # 028 web-ui-api, 022 scan-api,
│                                              #   022 journal, 017 snapshot: scope wording
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (next phase)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── tenancy/                  # NEW package — the only composition point
│   │   ├── __init__.py
│   │   ├── ids.py                # user-id grammar, reserved id, path containment
│   │   ├── context.py            # UserContext, UserProfile, effective settings,
│   │   │                         #   activation, per-user app construction
│   │   └── registry.py           # ContextRegistry, user-directory protocol
│   ├── discogs/
│   │   ├── client.py             # + auth (httpx.Auth) and budget params; token
│   │   │                         #   unwrap stays here; no-credential ⇒ DiscogsAuthError
│   │   └── ratelimit.py          # + RateBudget (shared state, lock, shared backoff);
│   │                             #   RateLimitGovernor keeps its interface
│   ├── settings.py               # token optional; + users_dir field
│   ├── cli.py                    # token gate in main(); _cmd_serve composed via
│   │                             #   registry.local(); gates/messages/order unchanged
│   ├── scan/                     # UNCHANGED
│   ├── web/                      # UNCHANGED
│   ├── snapshot/                 # UNCHANGED
│   └── tools/                    # UNCHANGED
└── tests/
    ├── unit/                     # ids, effective settings, registry lifecycle,
    │                             #   RateBudget concurrency, client auth strategy,
    │                             #   token-gate characterization, structural guards
    └── integration/              # two-user isolation suite, per-user occupancy,
                                  #   failure isolation, shared budget across
                                  #   contexts, local byte-equality regression
```

**Structure Decision**: one new package composing over untouched `scan/` and
`web/` (028's "composition, not modification", research R1). Edits to existing
modules are additive optional parameters with today's behavior as the default.

## Design highlights (what tasks will encode)

1. **Characterization first.** Before any source change, add tests that pin
   today's observable behavior the refactor could disturb: token-less exit
   code and message for every subcommand, the wire headers of a Discogs
   request, single-thread governor sleep sequences. They must pass before and
   after, unmodified.
2. **Rate budget** (R5). Extract `RateBudget`; make it thread-safe with a
   shared backoff deadline cleared by its owner; governor and client gain an
   optional `budget`. No budget ⇒ private budget ⇒ today's behavior.
3. **Credential strategy** (R4). `DiscogsClient(…, auth=None)`; the default
   builds the personal-token strategy in `client.py`; neither credential nor
   token ⇒ `DiscogsAuthError` at construction.
4. **Settings** (R2, R3, R7). Token becomes optional; `users_dir` added;
   `main()` gates the token with today's message.
5. **Tenancy package** (R1, R7–R10). Ids and containment; effective settings
   built at one point from `PER_USER_FIELDS`; `UserContext` with activation
   and a once-built app; `ContextRegistry` with lock, `local()`, `get()`,
   `dispose()`, lazy LLM client, LLM handle factory, and no production user
   directory.
6. **`serve` through the local context** (R6, R8). Same gates, same messages,
   same order, same banner; every Discogs client of the runtime — main,
   sync, folder-move proposal, plan execution — comes from the context and
   shares the budget.
7. **Two-user suite** (spec FR-023). Two contexts over distinct fake
   accounts in one process: interleaved full cycles, cross-user add and
   plan attempts, held-open turn / scan / sync, rejected credential, missing
   folder.
8. **Guards** (R11) and the local byte-equality regression (R12).
9. **Contracts and docs.** The three contract documents above; a short
   "user contexts" section in the component README; CLAUDE.md state updated
   in the same PR (single-PR convention).

## Risks

| Risk | Mitigation |
|---|---|
| A subtle change in local pacing or console output | Budget shared, notices per client (R5); characterization tests; owner replay of one scan / chat / sync session |
| `model_copy(update=…)` skips validation | Effective settings are built at one site from typed values; unit test asserts field types and that non-implicit views contain no credential |
| A future call site reads a per-user field from the deployment settings | Per-user-field guard pins the set of reading files |
| Hidden reliance on the pydantic error for a missing token | Verified none in tests; characterization test pins message and exit code |
| Thread-safety bugs in the budget | Dedicated concurrency tests with many threads, injected sleep and clock |

## Complexity Tracking

*No constitution violations — table intentionally empty.*
