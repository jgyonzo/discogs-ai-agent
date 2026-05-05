<!-- SPECKIT START -->
Active feature: **007-sandbox-fsize-budget** — production-data
bugfix for the V1 agent. The sandbox set `RLIMIT_FSIZE = 64 MiB`,
which was sized for the chart HTML alone but caps **every** file
the subprocess writes — including DuckDB's `/tmp/duckdb/duckdb_temp_storage_*.tmp`
spill file. Any aggregation against the full published catalog hit
`IO Error: File too large` and fell through to the controlled-failure
path. 007 raises the cap to 2 GiB (sized against the full-catalog
GROUP BY spill estimate), amends `004/contracts/code-generation.md
§3.1` to make the chart-vs-spill conflation explicit, and adds a
regression test.

Read this feature's plan and its phase-1 artifacts:

- Plan: `specs/007-sandbox-fsize-budget/plan.md`
- Spec: `specs/007-sandbox-fsize-budget/spec.md`
- Research: `specs/007-sandbox-fsize-budget/research.md` (sizing decision + alternatives)
- Contracts: `specs/007-sandbox-fsize-budget/contracts/`
  - `amendment-004-code-generation.md` — exact prose for the §3.1.1 insertion in 004's contract
- Quickstart: `specs/007-sandbox-fsize-budget/quickstart.md`

Prior 004-family work (still authoritative):

- `specs/004-agent-v1/` — V1 baseline (graph, API, sandbox, SQL
  safety, generated-code shape, persistence). Phase 4 (US2 — health
  + compose smoke + persistence durability) shipped on branch
  `004-agent-v1-us2`; Phases 5/6/7 (US3, US4, Polish) still
  unscheduled.
- `specs/005-agent-schema-context/` — schema enrichment + sample
  values + glossary + the `succeeded_empty` zero-row guardrail.
- `specs/006-bugfix-postmortem/` — three-bug postmortem and
  Constitution v1.2.0 amendment (Principle VII: Implementation
  Discipline). 007 is structurally a follow-on to 006: same
  read-only-runtime-mechanics family of issues.

The published DuckDB contract — produced by the ETL component —
remains authoritative for everything the agent reads:

- `specs/001-discogs-etl/contracts/duckdb-schema.md` — release side
  (`release_fact`, `release_unique_view`, `release_artist_bridge`,
  `release_label_bridge`).
- `specs/003-masters-artists/contracts/duckdb-schema.md` — optional
  `master_fact`.

The agent does NOT import code from `etl/` and does NOT read
non-published artifacts (no `stg_*`, no `clean_*`, no raw XML, no
Parquet at query time). Statically enforced by
`agent/tests/unit/test_no_etl_imports.py` and physically by mounting
only the published DuckDB into the agent container.

Resolved scope decisions still in force:

- **LLM provider = OpenAI** (`gpt-4o-mini` cheap, `gpt-4o` strong).
  Provider-agnostic abstraction is future work.
- **Multi-turn = light contextual carry-over** — only prior
  user-query *text* (capped at 4 turns / 512 tokens) flows into
  `query_understanding`. No prior SQL/code carry-over.
- **Sandbox file-size budget = 2 GiB** (007 decision). Process-wide
  on Linux; shared between chart HTML and DuckDB spill. Cwd jail
  remains the primary write-confinement control.

Constitution: `.specify/memory/constitution.md` (v1.2.0). 007 does
**NOT** require a constitution amendment — Principle VII.c
(read-only runtime mechanics) already covers the discipline; the
contract amendment in `004/contracts/code-generation.md §3.1.1` is
the load-bearing artifact.

The constitution prevails on any conflict.
<!-- SPECKIT END -->
