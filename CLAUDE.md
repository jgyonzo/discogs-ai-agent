<!-- SPECKIT START -->
Active feature: **008-agent-frontend-v1** — Demo Day frontend. A
React + Vite + TypeScript single-page app that turns the existing
agent into a demoable product: type or click a question, see a
chart inline, plus collapsible SQL, a small data preview, and
routing badges. The frontend ships as a **third** component in
this monorepo (alongside `etl/` and `agent/`), runs as a service
in the existing local docker-compose stack, and depends only on
the agent's already-shipped HTTP API plus a single CORS allowance
added to the agent. The frontend never touches DuckDB, Postgres,
ETL files, or local artifacts directly, and never executes
agent-generated Python or SQL. The chart artifact is rendered as
opaque HTML inside a sandboxed `<iframe>` (`sandbox="allow-scripts"`,
no `allow-same-origin`).

Read this feature's plan and its phase-1 artifacts:

- Plan: `specs/008-agent-frontend-v1/plan.md`
- Spec: `specs/008-agent-frontend-v1/spec.md`
- Research: `specs/008-agent-frontend-v1/research.md` (packaging,
  CORS, iframe sandbox, error mapping, state management)
- Data model: `specs/008-agent-frontend-v1/data-model.md`
  (frontend domain types + reducer state + localStorage shape)
- Contracts: `specs/008-agent-frontend-v1/contracts/`
  - `api-consumption.md` — which agent `/query` fields the frontend
    reads, ignores, or maps
  - `amendment-004-api-cors.md` — exact prose for a new §8
    "Cross-origin policy" in `004/contracts/api.md`
  - `curated-questions.md` — the V1 set of 7 demo questions and
    their spread coverage requirement
- Quickstart: `specs/008-agent-frontend-v1/quickstart.md`

Prior 004-family work (still authoritative):

- `specs/004-agent-v1/` — V1 baseline (graph, API, sandbox, SQL
  safety, generated-code shape, persistence). The frontend's
  consumption shape is anchored against `004/contracts/api.md`.
- `specs/005-agent-schema-context/` — schema enrichment + sample
  values + glossary + the `succeeded_empty` zero-row guardrail.
- `specs/006-bugfix-postmortem/` — three-bug postmortem and
  Constitution v1.2.0 amendment (Principle VII: Implementation
  Discipline).
- `specs/007-sandbox-fsize-budget/` — sandbox `RLIMIT_FSIZE`
  raised to 2 GiB; `004/contracts/code-generation.md §3.1.1`
  amended.

The published DuckDB contract — produced by the ETL component —
remains authoritative for everything the agent reads:

- `specs/001-discogs-etl/contracts/duckdb-schema.md` — release side
  (`release_fact`, `release_unique_view`, `release_artist_bridge`,
  `release_label_bridge`).
- `specs/003-masters-artists/contracts/duckdb-schema.md` — optional
  `master_fact`.

The agent does NOT import code from `etl/` and does NOT read
non-published artifacts. The frontend does NOT import code from
either `etl/` or `agent/`, and physically cannot read `data/`
because it never has the volume mounted.

Resolved scope decisions still in force:

- **LLM provider = OpenAI** (`gpt-4o-mini` cheap, `gpt-4o` strong).
- **Multi-turn = light contextual carry-over** — only prior
  user-query *text* (capped at 4 turns / 512 tokens) flows into
  `query_understanding`. No prior SQL/code carry-over.
- **Sandbox file-size budget = 2 GiB** (007 decision).
- **Frontend stack = React 18 + Vite + TypeScript + Tailwind**
  (008 decision; matches the source brief at
  `docs/discogs_frontend_initial_spec.md`).
- **Frontend packaging = Vite dev-server in container** for V1
  (008 decision; nginx-served static build deferred to V1.1).
- **CORS allowlist** = settings-sourced env var
  `CORS_ALLOWED_ORIGINS`, defaulting to
  `["http://localhost:5173", "http://localhost:3000"]`,
  `allow_credentials = False`.

Constitution: `.specify/memory/constitution.md` (v1.2.0). 008 does
**NOT** require a constitution amendment to begin. The plan does
recommend a follow-up **PATCH** amendment (Principle VI's prose
"two independently deployable components" → "two or more") to be
landed after 008 merges; the operational rules of Principle VI
already accommodate a third component. See plan §"Constitution
amendment recommendation".

The constitution prevails on any conflict.
<!-- SPECKIT END -->
