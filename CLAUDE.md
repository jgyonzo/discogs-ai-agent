<!-- SPECKIT START -->
Active feature: **004-agent-v1** — the V1 of Component B
(Constitution Principle VI), the conversational analytics agent
that consumes the published DuckDB produced by the ETL. This
is the **first feature for the `agent/` top-level directory**;
all prior specs (001/002/003) belong to the `etl/` component.
Read this feature's plan and its phase-1 artifacts:

- Plan: `specs/004-agent-v1/plan.md`
- Spec: `specs/004-agent-v1/spec.md`
- Research (technical decisions: sandbox shape, LangGraph
  checkpointer, test database strategy, etc.):
  `specs/004-agent-v1/research.md`
- Data model (entities + Postgres schema + LangGraph state):
  `specs/004-agent-v1/data-model.md`
- Contracts: `specs/004-agent-v1/contracts/`
  - `api.md` — FastAPI endpoint shapes
  - `graph.md` — LangGraph nodes + edges + retry semantics
  - `tools.md` — tool I/O + node-tool allowlist
  - `sql-safety.md` — allowed/forbidden SQL + two-pass check
  - `code-generation.md` — generated-code shape + sandbox
  - `postgres-schema.md` — DDL for the six `agent_*` tables
- Quickstart: `specs/004-agent-v1/quickstart.md`

The published DuckDB contract — produced by the ETL component
— remains authoritative for everything the agent reads:
- `specs/001-discogs-etl/contracts/duckdb-schema.md` — release
  side (`release_fact`, `release_unique_view`, `release_artist_bridge`,
  `release_label_bridge`).
- `specs/003-masters-artists/contracts/duckdb-schema.md` —
  optional `master_fact`.

The agent does NOT import code from `etl/` and does NOT read
non-published artifacts (no `stg_*`, no `clean_*`, no raw XML,
no Parquet at query time). This is enforced statically by
`agent/tests/unit/test_no_etl_imports.py` and physically by
mounting only the published DuckDB into the agent container.

Two scope decisions resolved during /speckit-specify:
- **LLM provider = OpenAI** (`gpt-4o-mini` cheap,
  `gpt-4o` strong). Provider-agnostic abstraction is future
  work.
- **Multi-turn = light contextual carry-over** — only prior
  user-query *text* (capped at 4 turns / 512 tokens) flows into
  `query_understanding`. No prior SQL/code carry-over.

Constitution: `.specify/memory/constitution.md` (v1.1.0).
Constitution v1.1.0 already defers the agent's framework, model
choice, and sandboxing strategy to "the agent's own initial
spec" (Technical Constraints / Components & runtime targets) —
which is exactly this spec. **No constitution amendment
required.**

The constitution prevails on any conflict.
<!-- SPECKIT END -->
