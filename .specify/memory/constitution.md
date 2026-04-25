<!--
SYNC IMPACT REPORT
- Version change: 1.0.0 → 1.1.0
- Bump rationale: Added Principle VI ("Two Components, One Contract") to
  enshrine that this repo hosts both the local ETL and a future containerized
  analytics agent app. Expanded Technical Constraints with components &
  runtime targets, boundary artifact, secrets handling, and repository
  layout. Updated workflow/governance references from "Principles I–V" to
  "Principles I–VI". MINOR per the constitution's own policy (new principle
  + material expansion; no existing principle redefined or removed).
- Modified principles:
  * (none redefined; Principle V wording unchanged. Principle VI added.)
- Added sections:
  * Core Principles → VI. Two Components, One Contract
  * Technical Constraints → Components & runtime targets, Boundary artifact,
    Secrets, Repository layout (existing items retained, expanded)
- Removed sections: none
- Deferred to a later amendment (driven by the agent's own initial spec):
  * Specific AWS service for the agent (ECS/Fargate/App Runner/EC2 — TBD)
  * Agent framework, model choice, tool surface, and code-execution sandboxing
  * Concrete top-level directory names (etl/, agent/ — TBD at first specify)
- Templates requiring updates:
  * .specify/templates/plan-template.md          ✅ aligned (Constitution Check is
    a generic placeholder resolved per-feature against this file; no static edit
    required)
  * .specify/templates/spec-template.md          ✅ aligned (no principle-driven
    structural changes required)
  * .specify/templates/tasks-template.md         ✅ aligned (task categorization
    neutral; component-scoped tasks expressible under existing phases)
  * .specify/templates/checklist-template.md     ✅ aligned
  * CLAUDE.md                                    ✅ aligned (delegates to current
    plan; no principle references to update)
  * README.md                                    ⚠ pending (currently the GitLab
    boilerplate; should eventually summarize project + reference this
    constitution, but not blocking)
- Prior history: 1.0.0 (2026-04-25) — first ratified constitution; replaced
  template placeholders with concrete Principles I–V plus Technical
  Constraints, Development Workflow & Quality Gates, and Governance.
- Follow-up TODOs: none deferred beyond the explicit list above.
-->

# Discogs ETL & Analytics Agent Constitution

## Core Principles

### I. Layered, Contract-First Data Architecture

The pipeline MUST be organized as discrete layers — `raw` → `staging` → `clean` →
`analytics` → `published` (DuckDB) — and each layer MUST expose an explicit,
documented contract (table name, grain, columns, types, nullability, logical
keys). Downstream layers MUST consume only the documented outputs of upstream
layers; they MUST NOT reach across layers (e.g., `release_fact` MUST NOT join
directly against `clean_release_formats`; it MUST consume `release_format_summary`).
Breaking changes to a published contract MUST be treated as a MAJOR change and
documented before implementation.

**Rationale:** Layer separation is what makes the pipeline reasonable about,
re-runnable, and safe for an LLM agent to consume. Contracts prevent silent
schema drift from breaking generated SQL or downstream analyses.

### II. Streaming, Bounded-Memory Processing

XML inputs MUST be parsed in streaming mode (e.g., iterparse-style), never
loaded whole into memory. Stage writers MUST flush to Parquet in batches.
Transformations MUST be expressible against bounded memory, even when the
source dump is at full Discogs scale (~60 GB releases XML). Any code path
that materializes the full XML, or a full layer, into a single in-process
collection is a violation.

**Rationale:** The release dump is too large for in-memory processing; the
pipeline is designed to run on a developer laptop. Bounded memory is the
load-bearing assumption that makes the project tractable end-to-end.

### III. Reproducible Runs with Manifest & Logs (NON-NEGOTIABLE)

Every pipeline execution MUST be identified by a `run_id` and MUST produce
(a) a manifest at `data/manifests/{run_id}.json` recording inputs (paths,
sizes, checksums), outputs (paths, row counts), per-step durations, status,
and warnings; and (b) a log at `data/logs/{run_id}.log`. Re-running the
pipeline against the same `snapshot_id` and configuration MUST yield logically
equivalent outputs. Steps MUST be individually re-runnable via the CLI; flags
such as `--run-id`, `--snapshot-id`, `--limit-releases`, `--force`, and
`--skip-existing` MUST be supported to enable iteration without re-processing
everything. Ad-hoc, undocumented manual steps as part of producing a published
output are forbidden.

**Rationale:** Without reproducibility, the agent's analytics layer becomes a
black box: there is no way to audit a number, recover from a partial failure,
or distinguish a code bug from a data issue. The manifest is the audit trail.

### IV. Data Quality Gates

Each output layer MUST run the data quality checks defined for it (e.g., uniqueness
of `release_id` in `clean_releases`; `released_date_precision` in the allowed
enum; `format_group` in the allowed enum; at most one `is_primary_*` per release).
Critical failures (uniqueness violations, schema mismatches, contract
violations) MUST fail the run with a non-zero exit code. Non-critical issues
MUST be recorded as warnings in the manifest. New columns or new derivations
MUST be accompanied by new or updated checks in the same change.

**Rationale:** The agent layer trusts upstream invariants — if those invariants
are not actually enforced, the LLM will produce confident but wrong answers.
DQ checks are the contract enforcement mechanism, not nice-to-haves.

### V. Agent-Friendly Analytics Surface

The analytics layer exposed to the agent MUST be intentionally small and
stable: in v1, `release_fact`, `release_artist_bridge`, `release_label_bridge`,
and the `release_unique_view` view in DuckDB. Naming conventions are
load-bearing and MUST be preserved: `is_*_format` flags exist at the
release-x-format grain (`clean_release_formats`); `has_*` flags exist at the
release grain (`release_format_summary`, `release_fact`). Counts of unique
releases MUST be expressible via `COUNT(DISTINCT release_id)` or
`release_unique_view`; new columns or tables MUST NOT introduce row
multiplication that would silently break naive `COUNT(*)` queries. Adding a
new analytics table is a deliberate decision and MUST be justified against
the alternative of a view or an extension to an existing fact.

**Rationale:** The agent generates Python+SQL from natural language; every
extra table, every inconsistent name, every implicit grain change is a place
where the LLM hallucinates or miscounts. Surface minimalism is a correctness
property, not a stylistic one.

### VI. Two Components, One Contract

This repository hosts two independently deployable components:

- **`etl`** — a local-first batch tool that produces the published DuckDB
  artifact from Discogs XML dumps. Runs on a developer laptop.
- **`agent`** — a containerized analytics agent service that answers
  natural-language questions over the published DuckDB. Targets AWS for
  deployment.

The two components are coupled **only** through the published DuckDB artifact
and the table contracts described in Principle V. Specifically:

- The agent MUST consume DuckDB tables/views. It MUST NOT read raw XML,
  staging Parquet, or clean Parquet directly.
- The agent MUST NOT import code from the ETL package, and the ETL MUST NOT
  import code from the agent package. Each component MUST run end-to-end
  without the other component's process.
- Each component MUST live under its own top-level directory with its own
  dependency manifest (e.g., its own `pyproject.toml` / `requirements.txt`).
  Shared utilities, if introduced later, MUST be justified rather than
  assumed and MUST live in a clearly named shared package — not smuggled
  through cross-component imports.
- A change that alters the DuckDB schema is a cross-component change and
  MUST follow Principle I (contract-first): update the contract, the
  producer (ETL), the consumer (agent), and the relevant DQ checks within
  the same change set.

**Rationale:** The two components have fundamentally different runtime
shapes — slow batch on a laptop vs. an online container on AWS. Conflating
them would force one runtime's constraints onto the other and would couple
deploy cycles that have no reason to be coupled. Treating the published
DuckDB as the only contact surface keeps both components free to evolve
within their own envelope.

## Technical Constraints

### Components & runtime targets

- **ETL:** Python, runs locally on a developer laptop (macOS/Linux). Project
  ships with `.venv/`. There is no cloud runtime for the ETL in v1.
- **Agent:** Containerized service deployed to AWS. The exact AWS service
  (e.g., ECS/Fargate, App Runner, EC2, Lambda), the agent framework, the
  model provider, and the code-execution sandboxing strategy are deliberately
  **not** decided here — they will be settled in the agent's own initial
  spec and a subsequent amendment to this constitution.

### Data layer

- **Stack:** Parquet for canonical intermediate and final outputs; DuckDB as
  the embedded analytical engine consumed by the agent. The choice of
  Parquet + DuckDB is fixed for v1.
- **Inputs:** Local Discogs XML dumps under `data/raw/discogs/{snapshot_id}/`.
  Automated download from Discogs is an explicit non-goal for v1.
- **Outputs:** Outputs MUST follow the directory layout in the initial ETL
  spec (`data/staging/{run_id}/`, `data/clean/{run_id}/`,
  `data/analytics/{run_id}/`, `data/published/duckdb/discogs.duckdb`).

### Boundary artifact

- The agent reads `data/published/duckdb/discogs.duckdb` (or an equivalent
  artifact location once the agent's deployment is specified — e.g., a
  bundled-into-image copy, an S3-fetched copy, or a mounted volume; chosen
  in the agent spec). It MUST NOT read raw XML, staging Parquet, or clean
  Parquet at query time.
- The published DuckDB is the only contract surface between the components
  (Principle VI).

### Secrets

- API keys (LLM provider, AWS credentials), tokens, and personal config
  files MUST NOT be committed. `.env` is gitignored at the repo root and
  MUST stay so. Local development reads secrets from `.env`; deployed
  agent runtimes MUST read secrets from the deploy target's secret store
  (e.g., AWS Secrets Manager, SSM Parameter Store) — confirmed in the
  agent's deployment plan.
- A committed file containing live credentials is a critical violation
  and MUST be remediated by rotation, not just deletion.

### Repository layout

- The repo is a monorepo. Each component lives under its own top-level
  directory (working names `etl/` and `agent/`; final names confirmed at
  the first `/speckit-specify` for each component). Each directory owns
  its dependency manifest, its tests, and its packaging.
- `data/` (raw, staging, clean, analytics, published, manifests, logs) is
  shared between components but is gitignored except for any small
  fixtures explicitly added under e.g. `tests/fixtures/`.
- `docs/` and `specs/` (Spec Kit feature specs) sit at the repo root.

### Scope guardrails

- **ETL v1:** `release_fact` and its bridges only. `master_fact`,
  `artist_dim`, `release_genre_bridge`, `company_bridge`, dashboards, UI,
  RAG, and AWS execution of the ETL are explicit non-goals for v1 and
  MUST NOT be smuggled into v1 features without an amendment to this
  constitution or an explicit scope decision recorded in the relevant
  feature spec.
- **Agent v1:** intentionally undefined here. Scope is deferred to the
  agent's own initial spec. Until that spec exists, plans MUST NOT make
  binding decisions about the agent beyond the Principle VI/Boundary
  artifact constraints.

## Development Workflow & Quality Gates

- **Spec-driven flow:** Non-trivial changes follow the Spec Kit cycle —
  `/speckit-specify` → (optional `/speckit-clarify`) → `/speckit-plan` →
  `/speckit-tasks` → `/speckit-implement`. Each phase produces artifacts
  under `specs/<feature>/` and is committed before the next phase.
- **Plan gate:** Every plan MUST include a Constitution Check section that
  evaluates the proposed work against Principles I–VI and the constraints
  above. Plans MUST also state which component(s) the work touches —
  ETL, agent, or both — so reviewers can apply the right constraints.
  Violations MUST be either eliminated or recorded in the plan's
  Complexity Tracking with explicit justification before implementation begins.
- **Pipeline change gate:** Any change that touches a layer's output (column
  added/removed, type changed, grain changed, derivation logic changed) MUST
  update (a) the contract section in the relevant feature spec, (b) the data
  quality checks for that layer, and (c) any consumer that depends on the
  changed contract — within the same change set.
- **CLI as the source of truth:** Every pipeline operation that produces or
  modifies a layer MUST be reachable via the documented CLI
  (`python -m discogs_etl.cli ...`). Notebook-only or REPL-only data
  generation that ends up in a published output is forbidden.
- **Sample-first iteration:** New ETL logic MUST be validated against a
  sample run (`--limit-releases`) before being run against the full dump.
  This is a workflow norm, not a code change — the CLI flag enables it.

## Governance

This constitution supersedes ad-hoc conventions. When this document and an
existing practice disagree, this document wins, and the practice is updated
or the constitution is formally amended.

**Amendments:** Proposed changes MUST be made via a pull request (or merge
request) that (a) updates this file, (b) updates the version line below
according to the semantic-versioning policy, (c) updates the Sync Impact
Report at the top, and (d) updates any dependent template or doc the change
affects. Amendments take effect when merged into `main`.

**Versioning policy (this constitution):**
- **MAJOR** — backwards-incompatible governance change, principle removed,
  or principle redefined in a way that invalidates existing plans.
- **MINOR** — a new principle or section added, or material expansion of
  existing guidance.
- **PATCH** — clarifications, wording, typo fixes, non-semantic refinements.

**Compliance review:** Plans and PRs that introduce or modify pipeline or
agent behavior MUST cite the principles they engage with. Reviewers MUST
reject changes that violate Principles I–VI without an accepted amendment
or a recorded, justified exception in Complexity Tracking. Recurring
exceptions in the same area are a signal the principle should be amended,
not bypassed.

**Runtime guidance:** Day-to-day implementation guidance for AI assistants
lives in `CLAUDE.md` and the active feature plan under `specs/<feature>/`.
Those documents MUST be consistent with this constitution; on conflict, this
constitution prevails.

**Version**: 1.1.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-04-25
