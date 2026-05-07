<!-- SPECKIT START -->
Active feature: **009-schema-context-join-graph** — silent
wrong-answer bugfix in the agent. A user query ("show the artist
with more masters by decade, exclude Various and Unknown
Artist") produced SQL that joined
`master_fact.master_id = release_artist_bridge.release_id` —
two distinct identifier namespaces, both BIGINT, so the join
completed and returned plausible-looking but wrong rows. The
003 contract has the correct guidance ("Use
`release_unique_view.master_id` for release-grain joins") but
that guidance lives in a spec file the LLM has never read.
Constitution VII.b explicitly forbids static schema prose in
prompts; the only place schema info reaches the LLM is the
dynamically-rendered `{schema_context_block}`.

009 closes the gap by extending the schema-context block
(`render_schema_block` in `agent/src/discogs_agent/duckdb_layer/schema.py`)
to deliver, for every catalog snapshot, the documented join graph
between allowlisted tables — including the master ↔ release
traversal and an explicit anti-pattern forbidding direct
master_id↔release_id joins. The change set is one rendering
function, one regression test, one amendment to
`005/contracts/schema-context.md`.

Read this feature's spec:

- Spec: `specs/009-schema-context-join-graph/spec.md`
- Checklist: `specs/009-schema-context-join-graph/checklists/requirements.md`
- Plan / research / contracts / tasks: pending (`/speckit-plan` next).

Reproducer: thread `fc1a3324-80da-465e-85ce-0359d5bd7633`,
question *"show the artist with more masters by decade, exclude
Various and Unknown Artist"*.

Prior 004-family work (still authoritative):

- `specs/004-agent-v1/` — V1 baseline (graph, API, sandbox, SQL
  safety, generated-code shape, persistence). Phase 4 (US2 — health
  + compose smoke + persistence durability) shipped.
- `specs/005-agent-schema-context/` — schema enrichment + sample
  values + glossary + the `succeeded_empty` zero-row guardrail.
  009 amends `005/contracts/schema-context.md`.
- `specs/006-bugfix-postmortem/` — three-bug postmortem and
  Constitution v1.2.0 amendment (Principle VII: Implementation
  Discipline). 009 is structurally another VII.b follow-through.
- `specs/007-sandbox-fsize-budget/` — sandbox `RLIMIT_FSIZE`
  raised to 2 GiB; `004/contracts/code-generation.md §3.1.1`
  amended.
- `specs/008-agent-frontend-v1/` — Demo Day frontend, currently
  on its own branch (`008-agent-frontend-v1`). Not yet merged.
  Independent of 009.

The published DuckDB contract — produced by the ETL component —
remains authoritative for everything the agent reads:

- `specs/001-discogs-etl/contracts/duckdb-schema.md` — release side
  (`release_fact`, `release_unique_view`, `release_artist_bridge`,
  `release_label_bridge`).
- `specs/003-masters-artists/contracts/duckdb-schema.md` — optional
  `master_fact`. The "Counting / joining rules" section of this
  contract is the source of truth for the join graph 009 will
  render.

The agent does NOT import code from `etl/` and does NOT read
non-published artifacts. Statically enforced by
`agent/tests/unit/test_no_etl_imports.py`.

Resolved scope decisions still in force:

- **LLM provider = OpenAI** (`gpt-4o-mini` cheap, `gpt-4o` strong).
- **Multi-turn = light contextual carry-over** — only prior
  user-query *text* (capped at 4 turns / 512 tokens) flows into
  `query_understanding`. No prior SQL/code carry-over.
- **Sandbox file-size budget = 2 GiB** (007 decision).

Constitution: `.specify/memory/constitution.md` (v1.2.0). 009
does **NOT** require a constitution amendment — Principle VII.b
(prompt-authoring discipline) already covers the discipline; the
contract amendment in `005/contracts/schema-context.md` and the
producer change to `render_schema_block` are the load-bearing
artifacts.

The constitution prevails on any conflict.
<!-- SPECKIT END -->
