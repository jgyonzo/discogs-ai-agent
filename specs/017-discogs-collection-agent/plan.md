# Implementation Plan: Discogs Collection Agent

**Branch**: `017-discogs-collection-agent` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/017-discogs-collection-agent/spec.md`

## Summary

A **terminal/CLI conversational agent** over the owner's **live Discogs
collection**: sync the collection into a local snapshot (minutes-scale,
progress shown, rate-limit aware), then answer analytics (genres, labels,
countries, top-rated, rarity, value, most-expensive), attribute-driven
filtered listings, and media-link lookups **instantly from the snapshot** —
plus **live, confirmation-gated write actions** (move records to existing or
new folders).

Technical approach: this feature **grows the existing `collection-agent/`
experiment into a proper packaged component** (same domain — the owner's
personal collection; its README already defers "the write side" to later
work). The agent is an **OpenAI tool-calling loop over deterministic tools**
(no code generation, no sandbox — unlike `agent/`): a thin httpx Discogs
client with header-driven rate limiting, a JSON snapshot store, a
**declarative attribute registry** that makes both aggregations and filters
extensible by declaration (FR-013), and a **runtime-enforced two-phase
confirmation** for all Discogs writes (FR-019). Components touched:
**`collection-agent/` only** (plus docs/CLAUDE.md).

## Technical Context

**Language/Version**: Python 3.12 (matches `agent/`; `requires-python >= 3.12`)
**Primary Dependencies**: `openai` (tool-calling loop; provider fixed by the
repo-wide "LLM provider = OpenAI" decision), `httpx` (Discogs client),
`pydantic` + `pydantic-settings` (models, env-driven settings per
Constitution VII(a)), `rich` (REPL rendering, sync progress, tables).
Deliberately **no** LangGraph, no sandbox, no DuckDB.
**Storage**: local JSON snapshot at `collection-agent/data/snapshot.json`
(gitignored; personal data). No Postgres, no DuckDB — the published DuckDB
artifact is explicitly out of scope for this feature.
**Testing**: pytest; unit tests over the attribute registry/aggregations/
filters with fixture snapshots; integration tests with a fake Discogs client
(recorded JSON fixtures); no live-API calls in CI.
**Target Platform**: developer laptop (macOS/Linux), local-first like `etl/`.
Not containerized; no docker-compose service in v1.
**Project Type**: CLI conversational agent (REPL) + supporting subcommands.
**Performance Goals**: full sync for ~300–1,000 records completes in minutes
(≲20 min worst case at 1,000 records under the ~60 req/min authenticated
limit, SC-006); snapshot-served answers at conversational speed (tool
execution < 1 s; end-to-end turn bounded by one LLM round-trip).
**Constraints**: Discogs rate limits (60/min authenticated, header-tracked);
unique User-Agent required; personal access token auth (single owner);
secrets via `.env` (never committed); writes always live + confirmed;
snapshot never presented as complete when partial/stale.
**Scale/Scope**: one account, ~300–1,000 collection instances (design
target; larger degrades gracefully), 4 user stories, ~30 functional
requirements.

## Constitution Check

*GATE: evaluated against Constitution v1.2.0 before Phase 0; re-checked after Phase 1.*

**Components touched**: `collection-agent/` only. No changes to `etl/`,
`agent/`, `frontend/`, the published DuckDB contract, or docker-compose.

- **I. Layered, contract-first data architecture** — Not engaged: no ETL
  layer is touched. The snapshot is a **private component-local cache**, not
  a published cross-component contract; its schema is still documented
  (`contracts/snapshot-schema.md`) in the contract-first spirit.
- **II. Streaming, bounded-memory** — Not engaged (no XML). The sync writes
  progressively and the snapshot (≤ ~1k records, single-digit MB) is
  trivially in-memory.
- **III. Reproducible runs, manifest & logs** — Engaged by analogy, not by
  letter (the principle governs pipeline executions producing published
  outputs). Adopted anyway in lightweight form: every sync records
  `synced_at`, durations, request counts, warnings, and completeness state
  in the snapshot's `meta` block, and the CLI can print it (`status`).
- **IV. Data quality gates** — Not engaged (no ETL layer outputs). The
  snapshot's `completeness` state (complete/partial/stale) is the analogous
  guard: a partial snapshot is never served as complete (FR-003c).
- **V. Agent-friendly analytics surface** — Not engaged: this feature does
  not read the DuckDB surface at all. Its own analytics surface is the
  deterministic tool set + attribute registry (`contracts/agent-tools.md`).
- **VI. Two components, one contract** — **Engaged.** This feature turns the
  existing experimental `collection-agent/` directory into a proper
  component: own directory (already exists), own dependency manifest (new
  `pyproject.toml`), own tests, no imports from `etl/` or `agent/` (enforced
  by a `test_no_cross_imports.py` mirroring `agent/`'s pattern), runs
  end-to-end without any other component's process. It consumes the **live
  Discogs API**, not the published DuckDB — so it does not join the
  DuckDB contract surface at all. The constitution's *prose* still says "two
  components" while the repo already hosts four (008 added `frontend/` under
  the same reading that Principle VI's operational rules accommodate more);
  the PATCH amendment recommended by 008's plan ("two or more") has not
  landed yet — this plan **re-recommends** it and widens it to cover
  `collection-agent/`. Recorded in Complexity Tracking.
- **VII. Implementation Discipline** —
  - **(a) Configuration sources**: model ids (`CHEAP_MODEL`-style), Discogs
    token, User-Agent string, snapshot path, rate-limit safety margin,
    staleness threshold — all from `pydantic-settings` (env/.env). No
    hardcoded literals.
  - **(b) Prompt-authoring discipline** (applied by analogy): the system
    prompt MUST NOT statically enumerate filterable attributes, tool
    behaviors, or snapshot fields in prose; the available attributes are
    rendered dynamically from the **attribute registry** (single source of
    truth), exactly as `{schema_context_block}` works in `agent/`. Static
    claims about "what the collection data contains" are forbidden in
    prompt files.
  - **(c) Read-only/runtime mechanics**: the write-path mechanics are
    documented in `contracts/agent-tools.md` — writes are live-only,
    two-phase, runtime-confirmed (never LLM-trusted), validate current state
    at execution time, and mark the snapshot stale afterward. Rate-limit
    mechanics (header tracking, backoff, 429 handling) are documented in
    `contracts/discogs-consumption.md`.
- **Secrets** — `DISCOGS_USER_TOKEN` (and optional `DISCOGS_USERNAME`
  override) live in `.env` (gitignored). Never logged, echoed, or committed.
  A committed token is a critical violation remediated by rotation.
- **Repository layout** — component keeps its own top-level directory with
  its own manifest and tests. Personal data stays in
  `collection-agent/data/` (gitignored entries), following that directory's
  existing precedent (`pending_discogs.csv`).
- **Scope guardrails** — ETL v1 guardrails untouched. This is not the
  `agent/` component, so "Agent v1 scope" constraints don't apply; Principle
  VI/boundary constraints are honored as above.

**Gate result: PASS** — one item recorded in Complexity Tracking (Principle
VI prose vs. component count), same posture 008 took.

**Post-Phase-1 re-check (2026-07-05)**: design artifacts introduce no new
violations — snapshot stays component-local, tools are deterministic, prompt
renders the registry dynamically, writes are runtime-gated. Still PASS.

## Project Structure

### Documentation (this feature)

```text
specs/017-discogs-collection-agent/
├── spec.md                          # Feature spec (clarified 2026-07-05)
├── plan.md                          # This file
├── research.md                      # Phase 0: decisions & rationale
├── data-model.md                    # Phase 1: snapshot, registry, session entities
├── quickstart.md                    # Phase 1: setup + first conversation
├── contracts/
│   ├── discogs-consumption.md       # Endpoints/fields read & written, rate-limit policy
│   ├── snapshot-schema.md           # Snapshot JSON schema + lifecycle states
│   └── agent-tools.md               # Tool surface, attribute registry, confirmation protocol
├── checklists/requirements.md       # Spec quality checklist (passing)
└── tasks.md                         # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
collection-agent/
├── pyproject.toml                   # NEW — component manifest (requires-python >=3.12)
├── README.md                        # UPDATED — matcher experiment + conversational agent
├── notebooks/                       # EXISTING — import path updated to collection_matcher
├── data/                            # EXISTING — gitignored personal data
│   └── snapshot.json                # NEW — collection snapshot (gitignored)
├── src/
│   ├── collection_matcher/          # MOVED — existing offline matcher, mechanical git mv
│   │   ├── __init__.py
│   │   ├── matcher.py               # was collection-agent/matcher.py (unchanged logic)
│   │   ├── review_batch.py          # was collection-agent/review_batch.py
│   │   └── export_batch.py          # was collection-agent/export_batch.py
│   └── collection_agent/
│       ├── __init__.py
│       ├── __main__.py              # python -m collection_agent
│       ├── cli.py                   # chat / sync / status subcommands (REPL loop)
│       ├── models.py                # pydantic entities (data-model.md)
│       ├── settings.py              # pydantic-settings (token, UA, models, paths)
│       ├── discogs/
│       │   ├── client.py            # thin httpx client + auth + User-Agent
│       │   └── ratelimit.py         # header-driven governor, backoff, 429 handling
│       ├── snapshot/
│       │   ├── store.py             # load/save/atomic-write, meta, staleness
│       │   └── sync.py              # two-phase sync (pages → per-release enrich), resumable
│       ├── registry.py              # declarative attribute registry (FR-013)
│       ├── tools/
│       │   ├── common.py            # snapshot serving guard (no/partial/stale/empty)
│       │   ├── analytics.py         # aggregate_by, collection_value, top_n
│       │   ├── browse.py            # filter_records (registry-driven)
│       │   ├── media.py             # media links per record / list
│       │   └── organize.py          # propose_moves / execute (runtime-gated)
│       ├── agent.py                 # OpenAI tool-calling loop, tool dispatch
│       └── prompts/
│           └── system.md            # system prompt; attributes rendered from registry
└── tests/
    ├── unit/
    │   ├── test_registry.py
    │   ├── test_analytics.py
    │   ├── test_filters.py
    │   ├── test_snapshot_store.py
    │   ├── test_media.py
    │   └── test_no_cross_imports.py # no imports from etl/ or agent/ (mirrors agent/'s test)
    ├── integration/
    │   ├── test_sync.py             # fake Discogs client, resumability, partial states
    │   ├── test_organize_flow.py    # two-phase confirmation, live-validation, failures
    │   └── test_agent_loop.py       # tool dispatch with stubbed LLM
    └── fixtures/                    # recorded Discogs JSON shapes, sample snapshots
```

**Structure Decision**: single component `collection-agent/`, promoted from
script experiment to `src/`-layout with **two sibling packages**:

- `collection_matcher/` — the existing offline matcher, relocated in a
  **strictly mechanical move** (git mv + import/path fixes + README/notebook
  reference updates; zero behavior change) done as its **own commit before
  any 017 feature work**, so history stays traceable and bisects never
  conflate the refactor with new code. Entry points become
  `python -m collection_matcher.review_batch <batch>` (and `export_batch`).
  It keeps its one allowed dependency: the ETL-published DuckDB.
- `collection_agent/` — the new conversational agent (this feature).

The two packages do not import each other; they share only the component
directory, its `pyproject.toml`, and the gitignored `data/`. The
`test_no_cross_imports.py` guard covers both (no `etl`/`discogs_agent`
imports from either; no `collection_matcher` ↔ `collection_agent` imports).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Principle VI prose says "two independently deployable components"; this feature makes `collection-agent/` the fourth | The feature's runtime shape (local CLI over live Discogs API, personal data) fits neither `etl/` (batch XML→DuckDB), `agent/` (containerized DuckDB QA service), nor `frontend/` (browser UI for `agent/`) | Folding into `agent/` was rejected: different data source (live API vs published DuckDB), different lifecycle (laptop CLI vs AWS container), different secrets (Discogs token vs OpenAI-only) — coupling them violates VI's own rationale. Precedent: 008 added `frontend/` as the third component under VI's operational rules; the recommended "two or more" PATCH amendment is re-recommended here (post-merge follow-up, not a blocker) |
