# `etl/` — Discogs Offline ETL (Fase 1 + Fase 2+3 + Fase 4)

This component is the **ETL** half of the project: a local Python CLI
that parses Discogs XML dumps (`releases.xml` always, plus `masters.xml`
and `artists.xml` when present) in streaming mode, materializes a
layered set of Parquet contracts (staging → clean → analytics), and
publishes a DuckDB at a canonical path that the future analytics agent
component will query.

The component is governed by:

- the project constitution at `.specify/memory/constitution.md`
  (v1.1.0 — Two Components, One Contract),
- the Fase 1 feature spec at `specs/001-discogs-etl/spec.md`
  (sample vertical slice — DuckDB schema, CLI contract, manifest
  contract),
- the Fase 2+3 feature spec at `specs/002-etl-scaleup/spec.md`
  (real-data robustness + laptop-scale execution),
- the Fase 4 feature spec at `specs/003-masters-artists/spec.md`
  (master analytics + artists pipeline foundation),
- the design artifacts under each of the three spec directories.

When the constitution and any local convention disagree, the
constitution prevails.

## Quickstart

From the **repo root**:

```bash
# install editable
pip install -e 'etl/[test]'

# stage a sample input (the curated 7-release fixture is the smoke target)
mkdir -p data/raw/discogs/discogs-2026-04
cp etl/tests/fixtures/releases_sample.xml \
   data/raw/discogs/discogs-2026-04/releases.xml
# Optionally stage masters / artists too (Fase 4 — both are auto-detected):
cp etl/tests/fixtures/masters_sample.xml \
   data/raw/discogs/discogs-2026-04/masters.xml
cp etl/tests/fixtures/artists_sample.xml \
   data/raw/discogs/discogs-2026-04/artists.xml

# run the full pipeline
python -m discogs_etl.cli run --config etl/configs/base.yml

# inspect the publish target
duckdb data/published/duckdb/discogs.duckdb \
  -c 'SELECT COUNT(DISTINCT release_id) FROM release_fact;'
# With masters.xml staged, also:
duckdb data/published/duckdb/discogs.duckdb \
  -c 'SELECT title, release_count FROM master_fact ORDER BY release_count DESC LIMIT 5;'
```

For Fase 2 (real-data robustness on the in-repo 404-release truncated
sample) and Fase 3 (laptop-scale on the gitignored ~50k-release big
sample), see `specs/002-etl-scaleup/quickstart.md`. For Fase 4
(masters + artists, including the FR-022 failure-path coverage for
duplicate `master_id`), see `specs/003-masters-artists/quickstart.md`.

## CLI

The full CLI contract lives at `specs/001-discogs-etl/contracts/cli.md`
with deltas at `specs/002-etl-scaleup/contracts/cli.md` (gzip
auto-detection + new `limits.*` config keys) and
`specs/003-masters-artists/contracts/cli.md` (Fase 4 step-name
additions; **no flag changes**).

```bash
python -m discogs_etl.cli run  --config etl/configs/base.yml [OPTIONS]
python -m discogs_etl.cli step <step-name> --config etl/configs/base.yml [OPTIONS]
```

Options (no Fase 4 additions):

| Flag | Purpose |
|---|---|
| `--config PATH` | YAML config (required) |
| `--run-id ID` | Override the auto-generated run id |
| `--snapshot-id ID` | Override `snapshot_id` from config |
| `--limit-releases N` | Stop after N `<release>` elements |
| `--force` | Allow overwriting outputs at an existing run id |
| `--skip-existing` | Skip steps whose declared outputs already exist |

The pipeline accepts `releases.xml.gz`, `masters.xml.gz`,
`artists.xml.gz` at the conventional raw path automatically
(suffix-based detection — no flag needed). Missing `masters.xml(.gz)`
or `artists.xml(.gz)` is recorded as a manifest warning and the
corresponding parse / normalize / build steps return early.

New `step` subcommand names (Fase 4):
`parse-masters`, `parse-artists`,
`normalize-masters`, `normalize-artists`,
`build-master-fact`.

## Fase 4 features (delta over Fase 1+2+3)

- **`master_fact` analytics table** in the published DuckDB — one
  row per master_id in the union ``clean_masters ∪
  clean_releases.master_id``. Columns:
  `master_id`, `title`, `main_release_id`, `year`, `decade`,
  `release_count`, `earliest_year`, `latest_year`,
  `primary_genre`, `primary_style`, `run_id`. The
  `primary_genre` / `primary_style` derivations LEFT JOIN
  `release_fact` on `main_release_id` (style at `style_order = 1`).
- **`clean_masters` and `clean_artists`** Parquet outputs in
  `data/clean/{run_id}/`. The artists side is foundational; a
  future `artist_dim` spec will surface it in DuckDB (per Q1=B in
  the Fase 4 spec).
- **Auto-detect optional inputs**: `prepare_sources` checks for
  `masters.xml(.gz)` and `artists.xml(.gz)` in the snapshot dir.
  Absence is a manifest warning, not a failure. All five new
  conditional steps (`parse_masters` / `parse_artists` /
  `normalize_masters` / `normalize_artists` / `build_master_fact`)
  return early when their input is missing.
- **Cross-table consistency**: a critical DQ check enforces
  `SUM(master_fact.release_count) =
  COUNT(clean_releases WHERE master_id IS NOT NULL)`.
- **Existing tables unchanged**: `release_fact`,
  `release_artist_bridge`, `release_label_bridge`, and
  `release_unique_view` keep their Fase 1 shapes byte-for-byte
  (FR-018).

## Tests

```bash
# Unit + Fase 1/2+3/4 integration. Skips the gated Fase 3 big-fixture
# test unless DISCOGS_BIG_FIXTURE=1.
pytest etl/tests/

# Fase 3 big-fixture (gated):
DISCOGS_BIG_FIXTURE=1 pytest etl/tests/integration/test_big_sample_pipeline.py
```

The unit + always-on integration suite is **84 tests** (~0.8s):
- 70 from Fase 1+2+3 (unchanged)
- 3 from `test_master_parser.py`
- 5 from `test_artist_parser.py`
- 2 from `test_master_fact_builder.py`
- 1 new from `test_dq_check_parity.py` (sum-equals helper)
- 3 integration tests (curated, real-raw, release-only snapshot)

The Fase 3 big-fixture test takes ~7–8 seconds locally; no scale
regression introduced by Fase 4.

## Where things live

- `etl/src/discogs_etl/` — package source
  - `cli.py` — click-based CLI; entrypoint
  - `pipeline/` — runner, manifest, run context + logging,
    `runtime.py` (peak RSS helper), `progress.py` (cadence-aware
    reporter)
  - `steps/` — one file per pipeline step; each implements the
    `Step` protocol. New in Fase 4: `parse_masters.py`,
    `parse_artists.py`, `normalize_masters.py`,
    `normalize_artists.py`, `build_master_fact.py`.
  - `parsers/` — streaming `lxml.iterparse` siblings:
    `releases_parser.py` / `masters_parser.py` /
    `artists_parser.py`. Each exposes a `*Stream` class with
    `truncation_info` for graceful EOF recovery.
  - `transforms/` — pure functions (date, format, text
    normalization)
  - `io/` — Parquet writer, DuckDB publisher, schemas, file
    helpers, `input.py` (gzip-aware opener with
    `open_xml_input(snapshot_dir, basename)` plus per-input
    wrappers).
  - `quality/` — §12 data-quality checks, aggregation, the
    threshold-based dispatcher, and the cross-table sum-equals
    helper.
- `etl/configs/base.yml` — default config (with `peak_rss_cap_gib`
  and `dq_check_in_memory_threshold` knobs)
- `etl/tests/` — unit tests + integration tests + fixtures
  - `releases_sample.xml` — 7 curated releases (in-scope edges)
  - `releases_sample_bad.xml` — duplicate `release_id` for
    FR-022 test
  - `releases_sample_raw.xml` — 404-release real Discogs excerpt
    (truncated)
  - `releases_sample_big_raw.xml` — gitignored ~49,689-release
    real subset
  - `masters_sample.xml` — 5 curated masters (Fase 4)
  - `masters_sample_bad.xml` — duplicate `master_id`
    (Fase 4 FR-022)
  - `masters_sample_raw.xml` — 317-master real Discogs excerpt
    (truncated)
  - `artists_sample.xml` — 5 curated artists (Unicode, long
    profile, nested aliases ignored per Q1=B)
  - `artists_sample_raw.xml` — 4841-artist real Discogs excerpt
    (truncated)

## Out of scope (deferred to follow-up specs)

- `artist_dim` table in DuckDB. `clean_artists.parquet` is
  produced as the foundation; a future spec will add the DuckDB
  surface.
- `release_genre_bridge` (source spec §18.2).
- `company_bridge` (source spec §18.4).
- A `master_id` denorm column on `release_fact` — would require
  a constitution amendment.
- Auto-download from Discogs (Fase 5).
- AWS execution / agent component (separate `agent/` component,
  future spec).
