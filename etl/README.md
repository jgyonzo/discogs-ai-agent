# `etl/` — Discogs Offline ETL (Fase 1 + Fase 2+3)

This component is the **ETL** half of the project: a local Python CLI that
parses a Discogs `releases.xml` (or `releases.xml.gz`) in streaming mode,
materializes a layered set of Parquet contracts (staging → clean →
analytics), and publishes a DuckDB at a canonical path that the future
analytics agent component will query.

The component is governed by:

- the project constitution at `.specify/memory/constitution.md`
  (v1.1.0 — Two Components, One Contract),
- the Fase 1 feature spec at `specs/001-discogs-etl/spec.md` (sample
  vertical slice — DuckDB schema, CLI contract, manifest contract),
- the Fase 2+3 feature spec at `specs/002-etl-scaleup/spec.md`
  (real-data robustness + laptop-scale execution),
- the design artifacts under both `specs/001-discogs-etl/` and
  `specs/002-etl-scaleup/`.

When the constitution and any local convention disagree, the constitution
prevails.

## Quickstart

From the **repo root**:

```bash
# install editable
pip install -e 'etl/[test]'

# stage a sample input (the curated 7-release fixture is the smoke target)
mkdir -p data/raw/discogs/discogs-2026-04
cp etl/tests/fixtures/releases_sample.xml data/raw/discogs/discogs-2026-04/releases.xml

# run the full pipeline
python -m discogs_etl.cli run --config etl/configs/base.yml

# inspect the publish target
duckdb data/published/duckdb/discogs.duckdb \
  -c 'SELECT COUNT(DISTINCT release_id) FROM release_fact;'
```

For Fase 2 (real-data robustness on the in-repo 404-release truncated
sample) and Fase 3 (laptop-scale on the gitignored ~50k-release big
sample), see `specs/002-etl-scaleup/quickstart.md`. For the FR-022 /
SC-006 failure-path walkthrough (critical DQ failure must leave the
canonical published DuckDB byte-identical), see
`specs/001-discogs-etl/quickstart.md`.

## CLI

The full CLI contract lives at `specs/001-discogs-etl/contracts/cli.md`
with the Fase 2+3 delta at `specs/002-etl-scaleup/contracts/cli.md`.
**No new flags or subcommands** in Fase 2+3 — the surface is
backward-compatible.

```bash
python -m discogs_etl.cli run  --config etl/configs/base.yml [OPTIONS]
python -m discogs_etl.cli step <step-name> --config etl/configs/base.yml [OPTIONS]
```

Options:

| Flag | Purpose |
|---|---|
| `--config PATH` | YAML config (required) |
| `--run-id ID` | Override the auto-generated run id |
| `--snapshot-id ID` | Override `snapshot_id` from config |
| `--limit-releases N` | Stop after N `<release>` elements |
| `--force` | Allow overwriting outputs at an existing run id |
| `--skip-existing` | Skip steps whose declared outputs already exist |

The pipeline now accepts `releases.xml.gz` at the conventional raw
path automatically (suffix-based detection — no flag needed). Both
files present? The uncompressed wins and a manifest warning notes
the choice.

## Fase 2+3 features

- **Real-data robustness (FR-001/FR-002):** truncated XML inputs no
  longer abort the run. The parser stops after the last fully-formed
  `<release>` and surfaces the truncation as a manifest warning
  (`parse_releases.truncated_xml`), yielding
  `quality_checks.status = "passed_with_warnings"`. Exit code 0.
- **Gzip input (FR-010):** `releases.xml.gz` is decompressed
  streaming via stdlib `gzip` — no full-file extract to disk. The
  parser opens the right file via the gzip-aware
  `io.input.open_releases_input(snapshot_dir)` helper.
- **Per-step peak RSS (FR-011/FR-013):** the runner records
  `step_metrics.{step_name}.peak_rss_bytes` after every step. If a
  step's peak exceeds `limits.peak_rss_cap_gib * 2^30` (default
  4 GiB), the manifest gains a `runtime.peak_rss_exceeds_cap`
  warning — informational, not a failure.
- **Progress logging (FR-012):** per-release steps (parse,
  normalize_releases, normalize_release_entities,
  build_release_format_summary, build_release_fact) emit progress
  lines every `limits.log_progress_every` releases (default 10000)
  with elapsed time and instantaneous releases/sec. Each step also
  records its `releases_per_sec` in `step_metrics`.
- **SQL-based DQ at scale (FR-014):** the four uniqueness /
  distinct-count / at-most-one-primary checks gain DuckDB-SQL
  siblings. `quality.dispatch.run_check` routes between the
  in-memory and SQL implementations based on
  `pyarrow.parquet.read_metadata(path).num_rows` vs
  `limits.dq_check_in_memory_threshold` (default 10M). Both paths
  return the same `CheckResult` shape — the parity test enforces it.

## Tests

```bash
# Unit + Fase 2 integration (always runs in CI; ~1s on a laptop).
pytest etl/tests/

# Fase 3 integration against the gitignored 191 MB / ~49k-release
# fixture; gated by env var + presence check.
DISCOGS_BIG_FIXTURE=1 pytest etl/tests/integration/test_big_sample_pipeline.py
```

The unit + Fase 2 integration suite is **70 tests** (~1s wall clock):
the Fase 1 set (54), the truncation-handling set, the gzip-opener
set, the DQ-check parity set, and the real-sample integration.

The Fase 3 big-fixture test takes ~7–8 seconds locally and asserts:
peak RSS < 4 GiB, DuckDB `COUNT(DISTINCT release_id)` ≈ 49,689 (±5),
≥ 3 progress lines from the parse step, and
`quality_checks.status = "passed_with_warnings"`.

## Where things live

- `etl/src/discogs_etl/` — package source
  - `cli.py` — click-based CLI; entrypoint
  - `pipeline/` — runner, manifest, run context + logging,
    `runtime.py` (peak RSS helper), `progress.py` (cadence-aware
    reporter)
  - `steps/` — one file per pipeline step; each implements the
    `Step` protocol
  - `parsers/releases_parser.py` — streaming `lxml.iterparse` with
    truncation-graceful `ReleaseStream`
  - `transforms/` — pure functions (date, format, text
    normalization)
  - `io/` — Parquet writer, DuckDB publisher, schemas, file
    helpers, `input.py` (gzip-aware opener)
  - `quality/` — §12 data-quality checks, aggregation, and the
    threshold-based dispatcher
- `etl/configs/base.yml` — default config (with `peak_rss_cap_gib`
  and `dq_check_in_memory_threshold` knobs)
- `etl/tests/` — unit tests + integration tests + fixtures
  - `releases_sample.xml` — 7 curated releases (in-scope Fase 1 edges)
  - `releases_sample_bad.xml` — duplicate `release_id` for FR-022 test
  - `releases_sample_raw.xml` — 404-release real Discogs excerpt
    (truncated; primary Fase 2 acceptance fixture)
  - `releases_sample_big_raw.xml` — gitignored ~49,689-release real
    subset (191 MB; Fase 3 acceptance fixture; download / build
    locally per the spec's Assumptions)

## Out of scope (deferred to follow-up specs)

- Masters / artists XML, `master_fact`, `artist_dim` (Fase 4).
- Auto-download from Discogs (Fase 5).
- Validation against the **full** ~60 GB Discogs dump on a laptop
  (architecturally supported; empirical full-dump validation is its
  own future spec).
- AWS execution / agent component (separate `agent/` component,
  future spec).
