# Implementation Plan: Discogs ETL — Fase 2+3 (Real-data robustness + laptop-scale)

**Branch**: `002-etl-scaleup` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/002-etl-scaleup/spec.md`
**Components touched**: `etl/` only (per Constitution Principle VI)
**Constitution version**: 1.1.0
**Builds on**: `specs/001-discogs-etl/` (Fase 1, merged into `main`)

## Summary

Take the Fase 1 pipeline and (a) make it survive a real Discogs releases
excerpt without crashing, with anomalies surfaced as warnings, and (b)
make it usable at laptop scale on real-data subsets — with gzip input
support, bounded RSS, observable progress, per-step memory metrics in
the manifest, and DuckDB-SQL alternatives for the DQ checks that
currently materialize whole columns into Python collections.

**No public contracts change.** The published DuckDB schema, the CLI
shape, and the manifest's existing fields stay byte-compatible with
Fase 1. New optional fields under `manifest.step_metrics` and new
optional `limits.*` config keys are additive only.

The deliverable is shaped so that a future "Fase 3 full-dump" run on
a real ~60 GB dump is a configuration / infrastructure exercise — no
new code paths required.

## Technical Context

**Language/Version**: Python 3.12 (unchanged from Fase 1; min 3.11).

**Primary Dependencies** (delta vs Fase 1):
- *(unchanged)* `lxml`, `pyarrow`, `duckdb`, `click`, `PyYAML`, `pytest`
- *No new runtime deps.* `gzip` and `resource` are stdlib. RSS sampling
  uses `resource.getrusage(RUSAGE_SELF).ru_maxrss` (cumulative process
  peak — sufficient for the per-step recording we need; portable
  across macOS/Linux with a small unit conversion). We do **not**
  introduce `psutil` for v1.

**Storage**: unchanged (Parquet per-run + canonical published DuckDB).

**Testing**: pytest. New cases:
- Unit: gzip parser behavior; in-memory vs SQL DQ check parity (the
  same input through both paths must yield equal `CheckResult`
  shapes); truncation warning emission.
- Integration:
  - `test_real_sample_pipeline.py` — full pipeline against
    `etl/tests/fixtures/releases_sample_raw.xml` (404 releases,
    truncated). Always runs in CI.
  - `test_big_sample_pipeline.py` — full pipeline against
    `etl/tests/fixtures/releases_sample_big_raw.xml` (~49,689
    releases, 191 MB). The fixture is gitignored (per the spec
    Assumption); the test is gated by an env var
    `DISCOGS_BIG_FIXTURE=1` and a presence check, so CI without
    the file simply skips.

**Target Platform**: macOS / Linux developer laptop. Same as Fase 1.

**Project Type**: Python CLI library — single component (`etl/`).
No deployment surface changes.

**Performance Goals** (Fase 2 + Fase 3):
- Big-raw run (49,689 releases, 191 MB uncompressed): under ~3 minutes
  wall-clock on a developer laptop, peak RSS comfortably under 1 GiB
  (well below the 4 GiB cap).
- Progress log lines arrive at the configured `log_progress_every`
  cadence with elapsed time and instantaneous releases/sec on every
  per-release step.
- Architecture supports the full ~30M-release dump within the 4 GiB
  cap; this spec validates the architectural claim via SC-014's
  synthetic stress test, not via a real full-dump run.

**Constraints**:
- Schema, CLI shape, manifest top-level fields all stable (FR-020,
  FR-021, FR-022).
- All 54 Fase 1 tests must keep passing unchanged (SC-003).
- Bounded memory: any code path that materializes a whole layer is a
  violation; SQL alternatives must be wired up at a configurable
  threshold (FR-014).

**Scale/Scope**: validated empirically against the in-repo big_raw
fixture (~50k releases). Architectural support for full-dump
(~30M releases) demonstrated via the synthetic stress test (SC-014).

## Constitution Check

*Gate: must pass before Phase 0; re-checked at end of Phase 1.*

**Components-touched declaration**: `etl/` only. No `agent/` work; no
imports from a hypothetical `agent/` package.

| # | Principle | Engaged? | How this plan complies |
|---|-----------|----------|------------------------|
| I | Layered, contract-first data architecture | Yes | All layer schemas unchanged. The manifest contract gains optional `step_metrics` fields (additive) and new optional `limits.*` config keys; updates to `contracts/manifest.md` ship in this same spec. No published-DuckDB schema change (FR-021). |
| II | Streaming, bounded-memory processing | Yes | Stronger than Fase 1: FR-011 makes bounded RSS a measurable invariant; FR-014 forces SQL-based DQ checks above a row-count threshold; FR-010 adds streaming gzip via `gzip.open` passed to `lxml.iterparse`. |
| III | Reproducible runs with manifest & logs (NON-NEGOTIABLE) | Yes | Manifest is additive only. New per-step `peak_rss_bytes` and `releases_per_sec` fields are documented in the updated `contracts/manifest.md`. Run reproducibility unchanged. |
| IV | Data quality gates | Yes | Critical/warning classification unchanged. SQL alternatives must return identical `CheckResult` shapes (test asserts this — SC-014). Truncation surfaces as a `parse_releases.truncated_xml` warning, not a critical failure (FR-001 / FR-002). |
| V | Agent-friendly analytics surface | Yes | DuckDB tables, view, and naming conventions all unchanged (FR-021). No counting-rule changes. |
| VI | Two components, one contract | Yes | All edits stay under `etl/`. No new top-level paths. |

**Plan gate verdict**: PASS — no Complexity Tracking entries. The
manifest extension is additive (covered by FR-022 + Constitution
allowance for additive contract evolution).

## Project Structure

### Documentation (this feature)

```text
specs/002-etl-scaleup/
├── spec.md                # Feature spec (committed)
├── plan.md                # This file
├── research.md            # Phase 0 — technology choices for Fase 2+3
├── data-model.md          # Phase 1 — manifest extension + DQ-path dispatch
├── contracts/
│   ├── cli.md             # CLI contract (delta vs Fase 1; backward-compatible)
│   └── manifest.md        # Manifest contract (delta vs Fase 1; additive only)
├── quickstart.md          # Phase 1 — developer walkthrough for both fixtures
├── checklists/
│   └── requirements.md    # Spec quality checklist (committed)
└── tasks.md               # Phase 2 output — produced by /speckit-tasks
```

The DuckDB schema contract from Fase 1 (`specs/001-discogs-etl/contracts/duckdb-schema.md`)
is unchanged; this spec deliberately does not republish it.

### Source Code (repository root — delta vs Fase 1)

Only files that change or are added:

```text
etl/
├── configs/
│   └── base.yml                                # +limits.peak_rss_cap_gib (4), +limits.dq_check_in_memory_threshold (10_000_000)
├── src/discogs_etl/
│   ├── pipeline/
│   │   ├── context.py                          # add new limits fields to LimitConfig
│   │   ├── manifest.py                         # add record_step_metrics(); update default schema
│   │   └── runner.py                           # capture peak RSS + releases/sec per step
│   ├── parsers/
│   │   └── releases_parser.py                  # accept gzipped path; recover from truncation; emit progress
│   ├── io/
│   │   └── input.py    [NEW]                   # open_releases_input(path) → (file_obj, source_path) handling .gz
│   ├── quality/
│   │   ├── checks.py                           # SQL alternatives for uniqueness / pair-uniqueness / distinct-count / at-most-one-primary
│   │   └── dispatch.py [NEW]                   # threshold-based dispatcher: in-memory vs DuckDB SQL
│   └── steps/
│       ├── parse_releases.py                   # call new input opener; emit progress lines
│       ├── normalize_releases.py               # progress log per N rows
│       ├── normalize_release_entities.py       # progress log per N rows
│       ├── build_release_format_summary.py     # progress log
│       └── build_release_fact.py               # progress log
└── tests/
    ├── unit/
    │   ├── test_dq_check_parity.py [NEW]       # in-memory vs SQL paths return identical CheckResult
    │   ├── test_gzip_input.py      [NEW]       # parser accepts .xml.gz; byte-equivalent outputs
    │   └── test_truncation_warning.py [NEW]    # parser emits warning on truncated XML; no exception
    └── integration/
        ├── test_real_sample_pipeline.py [NEW]  # full pipeline against releases_sample_raw.xml
        └── test_big_sample_pipeline.py  [NEW]  # full pipeline against releases_sample_big_raw.xml (gated)
```

**Structure decision**: surgical changes only. The Fase 1 layout is
preserved; new files appear next to their natural neighbors
(`io/input.py` for the gzip-aware opener, `quality/dispatch.py` for
the size-based DQ-check dispatcher). No new top-level component
surface.

## Complexity Tracking

> Filled only if Constitution Check has violations that must be
> justified. None for this plan.

*(no entries — all six principles are satisfied without exception)*

## Plan Status

- **Phase 0** — Research: see [research.md](./research.md).
- **Phase 1** — Design & contracts: see
  [data-model.md](./data-model.md), [contracts/](./contracts/), and
  [quickstart.md](./quickstart.md). Constitution Check re-evaluated
  post-design (no new violations).
- **Phase 2** — Tasks: produced by `/speckit-tasks` (not by this
  command).

## Post-design Constitution Re-check

After producing the Phase 1 artifacts:

- **I (Layered, contract-first)**: `data-model.md` documents the
  manifest extension precisely; `contracts/manifest.md` is updated
  to be the new authoritative shape. Layer schemas unchanged. ✅
- **II (Streaming, bounded memory)**: `research.md` commits to
  `gzip.open` streaming + `resource.getrusage` cumulative peak +
  threshold-based SQL dispatch; the in-memory paths and the SQL
  alternatives are wire-compatible (same `CheckResult` shape). ✅
- **III (Reproducible runs)**: `quickstart.md` walks through both the
  small and big fixtures end-to-end and shows the new manifest
  fields. ✅
- **IV (DQ gates)**: `quality/dispatch.py`'s threshold logic and the
  parity unit test (T-style; named in tasks.md by `/speckit-tasks`)
  guarantee the same critical/warning verdicts. ✅
- **V (Agent-friendly surface)**: published DuckDB schema unchanged.
  Agent component (future spec) consumes the exact same surface as
  in Fase 1. ✅
- **VI (Two components, one contract)**: all changes stay under
  `etl/`. ✅

**Final Constitution Check verdict**: PASS — no Complexity Tracking
entries needed.
