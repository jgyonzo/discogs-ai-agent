<!-- SPECKIT START -->
Active feature: **002-etl-scaleup** (Fase 2+3 — real-data robustness
+ laptop-scale execution). For the active scope, technical context,
contracts deltas, and verification walkthrough, read this feature's
plan and its phase 1 artifacts:

- Plan: `specs/002-etl-scaleup/plan.md`
- Spec: `specs/002-etl-scaleup/spec.md`
- Research (technology choices for Fase 2+3): `specs/002-etl-scaleup/research.md`
- Data model (manifest extension + DQ-path dispatch): `specs/002-etl-scaleup/data-model.md`
- Contracts: `specs/002-etl-scaleup/contracts/`
  (`cli.md`, `manifest.md` — both are deltas vs Fase 1)
- Quickstart: `specs/002-etl-scaleup/quickstart.md`

Fase 1 artifacts (still authoritative for everything not diffed by
this spec) live at `specs/001-discogs-etl/` — in particular the
DuckDB-schema contract at `specs/001-discogs-etl/contracts/duckdb-schema.md`,
which 002 deliberately does not republish (no schema changes).

Constitution: `.specify/memory/constitution.md` (v1.1.0).
The constitution prevails on any conflict.
<!-- SPECKIT END -->
