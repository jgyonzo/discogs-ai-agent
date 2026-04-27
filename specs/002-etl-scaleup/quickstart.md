# Quickstart: Discogs ETL — Fase 2+3

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Audience**: a developer on this branch who wants to verify both
Fase 2 (real-data robustness on the in-repo 404-release sample) and
Fase 3 (laptop-scale on the gitignored ~50k-release sample), plus
the new gzip path and the new manifest fields.

This walkthrough assumes the implementation tasks (produced by
`/speckit-tasks` in a follow-up step) are complete. It doubles as
the manual integration script.

---

## 0. Prerequisites

- Python 3.11+ (3.12 recommended).
- macOS or Linux. Windows still not validated.
- The Fase 1 install is sufficient: from the repo root,
  `pip install -e 'etl/[test]'` brings in everything (no new runtime
  deps in this spec).
- The small raw fixture (`etl/tests/fixtures/releases_sample_raw.xml`,
  404 real releases, truncated) is tracked in git — already on disk.
- The big fixture (`etl/tests/fixtures/releases_sample_big_raw.xml`,
  ~49,689 real releases, 191 MB, truncated) is **gitignored**. Drop
  it on disk locally if you want to run US2 / SC-011 / SC-013.

## 1. Smoke: Fase 1 still works (regression check)

The Fase 1 fixture and integration test must keep passing unchanged:

```bash
pytest etl/tests/integration/test_sample_pipeline.py -v
```

All Fase 1 acceptance scenarios should still pass (SC-003).

## 2. Fase 2 acceptance: run against the real raw sample

Stage the small raw fixture as input:

```bash
mkdir -p data/raw/discogs/discogs-2026-04
cp etl/tests/fixtures/releases_sample_raw.xml \
   data/raw/discogs/discogs-2026-04/releases.xml

python -m discogs_etl.cli run --config etl/configs/base.yml ; echo "exit=$?"
```

Expected:

- `exit=0`.
- The run completes; the log shows progress lines emitted on each
  per-release step (parse, normalize_*, build_*).
- The latest manifest at `data/manifests/{run_id}.json` reports:
  - `quality_checks.status = "passed_with_warnings"` (NOT
    `incomplete`).
  - `quality_checks.warnings` contains an entry named
    `"parse_releases.truncated_xml"` with the last successful
    `release_id` (~414).
  - `step_metrics.parse_releases.peak_rss_bytes` is non-zero.
  - `step_metrics.parse_releases.releases_per_sec` is non-null.

Validate the published DuckDB:

```bash
duckdb data/published/duckdb/discogs.duckdb <<'SQL'
SELECT COUNT(DISTINCT release_id) AS n FROM release_fact;
-- expected: 404 (the count of fully-formed <release> elements)
SELECT format_description_summary
FROM release_fact
WHERE format_description_summary LIKE '%⅓%'
LIMIT 5;
-- expected: at least one row containing '⅓ RPM' — verifies UTF-8 round-trip
SQL
```

## 3. Gzip equivalence (SC-010)

Create a gzipped sibling and re-run:

```bash
gzip -k data/raw/discogs/discogs-2026-04/releases.xml
# now both releases.xml and releases.xml.gz exist
python -m discogs_etl.cli run --config etl/configs/base.yml --run-id gz-equiv-test ; echo "exit=$?"
```

The `prepare_sources.gz_and_plain_present` warning will appear in
the manifest (because both files exist; uncompressed wins). To
exercise the gzip path, remove the uncompressed file and re-run:

```bash
rm data/raw/discogs/discogs-2026-04/releases.xml
python -m discogs_etl.cli run --config etl/configs/base.yml --run-id gz-only-test ; echo "exit=$?"
```

Expected: same release count (404), `prepare_sources.gz_input`
warning present, analytics Parquet byte-equivalent (modulo
`run_id`, `parsed_at`, `source_file`) to the uncompressed run.

## 4. Fase 3 acceptance: run against the big raw sample

This step requires the gitignored 191 MB fixture on disk.

```bash
mkdir -p data/raw/discogs/discogs-2026-04
cp etl/tests/fixtures/releases_sample_big_raw.xml \
   data/raw/discogs/discogs-2026-04/releases.xml

# Optional: track peak RSS externally too.
# macOS:  /usr/bin/time -l   python -m discogs_etl.cli ...
# Linux:  /usr/bin/time -v   python -m discogs_etl.cli ...
python -m discogs_etl.cli run --config etl/configs/base.yml --run-id big-raw-1 ; echo "exit=$?"
```

Expected (SC-011 / SC-013):

- Run completes in well under 10 minutes on a developer laptop
  (target: ~3 min).
- Peak RSS — recorded as
  `step_metrics.parse_releases.peak_rss_bytes` and at finalize —
  stays comfortably under `4 * 2^30` bytes (default cap), with
  observed values typically under 1 GiB for this 191 MB input.
- `quality_checks.status = "passed_with_warnings"` (truncation at
  EOF).
- `SELECT COUNT(DISTINCT release_id) FROM release_fact` returns
  `49689` (modulo any rows dropped for empty `id`, surfaced as
  warnings).
- ~5 progress log lines for the parse step (cadence = 10000 by
  default, ~50k releases → ~5 reports).

If `peak_rss_bytes` exceeds the cap, the manifest gains a
`runtime.peak_rss_exceeds_cap` warning (informational; the run
still passes).

## 5. Run the test suite

```bash
pytest etl/tests/                                # all unit + Fase 2 integration
DISCOGS_BIG_FIXTURE=1 pytest etl/tests/integration/test_big_sample_pipeline.py
```

Expected: every Fase 1 test still passes (SC-003), every Fase 2 test
passes, and — when the big fixture is on disk and the env var is
set — the Fase 3 integration test passes too. Without
`DISCOGS_BIG_FIXTURE=1` the big test is skipped silently.

## 6. SQL DQ-path parity check (SC-014)

The parity test forces the SQL DQ path on small inputs by lowering
the threshold to a tiny value (e.g., 1 or 100). Run it explicitly:

```bash
pytest etl/tests/unit/test_dq_check_parity.py -v
```

Expected: every check function's in-memory result and SQL result
have identical `(name, layer, table, severity, passed)` quintuples
on the same synthetic input.

## 7. What's NOT in this spec

If any of the below doesn't yet work, that is **by design** —
deferred to follow-up specs:

- Validation against the **full** ~60 GB Discogs dump (Q2=B chose
  the in-repo subset over the full dump). Architecture supports it;
  empirical full-dump validation is its own future spec if you
  decide it's worth the time.
- `masters.xml` / `artists.xml` parsing (Fase 4).
- Auto-download from Discogs (Fase 5).
- A wall-clock budget enforced as a gate (peak RSS cap is a
  warning, not a gate).
- DuckDB-engine tuning knobs.
- The agent component.

## 8. Cleanup between runs

Each run uses its own `run_id` directories under `data/{staging,
clean,analytics}/`, so re-running doesn't collide. To free disk
between iterations:

```bash
rm -rf data/staging data/clean data/analytics data/manifests data/logs
# leave data/published/duckdb/discogs.duckdb (the canonical publish)
# unless you want to verify the FR-022 byte-identical-on-failure
# behavior as in Fase 1.
```
