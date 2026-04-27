# Phase 0 Research: Discogs ETL — Fase 2+3

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Purpose**: Resolve approach choices for the Fase 2+3 implementation.
There are no remaining `[NEEDS CLARIFICATION]` markers from the spec
(both were resolved before plan started).

Each entry: **Decision** — **Rationale** — **Alternatives considered**.

---

## R-01: Truncated-XML recovery in the releases parser

**Decision**: Wrap the existing `lxml.iterparse(events=("end",), tag="release")`
loop in a `try / except etree.XMLSyntaxError`. On exception, stop
yielding releases, capture the last successful `release_id` (and the
exception message), and let the caller (the `parse_releases` step)
record a manifest warning. Do **not** switch to `recover=True`.

**Rationale**:
- We want to fail loud on malformed *individual* releases (so DQ
  catches them) and only swallow the *terminal* truncation. `recover=True`
  is more permissive — it would silently coerce malformed elements
  into best-effort parses, which can hide real bugs. Catching the
  exception only at the iterator boundary draws a clear line.
- The Fase 2 acceptance scenario (US1 #1) requires
  `quality_checks.status = "passed_with_warnings"` for the truncated
  small raw fixture. This pattern is exactly what produces that.

**Alternatives considered**:
- `lxml.etree.iterparse(..., recover=True)`: simpler one-liner but
  changes semantics for non-truncation malformations. Rejected.
- A custom byte-level scanner that reads up to the last `</release>`
  and then iterparses the truncated buffer: works but pulls
  XML-parsing concerns into Python; not worth the complexity.

---

## R-02: Gzip input streaming

**Decision**: A new module `etl/src/discogs_etl/io/input.py` with a
single function `open_releases_input(path: Path) -> tuple[BinaryIO, Path]`.
- If the path resolves to `releases.xml.gz`, return
  `(gzip.GzipFile(path, "rb"), path)`.
- If the path resolves to `releases.xml`, return
  `(open(path, "rb"), path)`.
- If both exist in the snapshot dir, the uncompressed file wins and
  the run records a manifest warning (`prepare_sources.gz_and_plain_present`).
- The parser receives the file-like object and passes it to
  `lxml.iterparse(file_obj, events=("end",), tag="release")`. lxml
  natively supports file-like inputs.

**Rationale**:
- Stdlib `gzip` is sufficient — no new dep. `GzipFile` reads in
  streaming chunks; combined with iterparse this keeps memory
  bounded regardless of compressed file size.
- Centralizing the open-logic in `io/input.py` (a) keeps the
  parser ignorant of compression, (b) makes the precedence rule
  testable in isolation, (c) gives a single mock point for tests.
- Detection by suffix is simple, fast, and matches Discogs'
  distribution conventions.

**Alternatives considered**:
- Magic-byte sniffing (`0x1f 0x8b`): adds robustness if a file is
  named `releases.xml` but actually gzipped. Out of scope here;
  Discogs always uses the right suffix.
- Pre-extract `.gz` to disk before parsing: violates Constitution
  II (bounded memory and bounded disk are sibling concerns; doubling
  the disk footprint is wasteful and slow).

---

## R-03: Per-step peak RSS measurement

**Decision**: Use stdlib `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`
to capture the **cumulative process peak RSS** at the *end* of each
step. Record it under `manifest.step_metrics.{step_name}.peak_rss_bytes`.

Platform unit normalization:
- macOS (Darwin): `ru_maxrss` is in **bytes**.
- Linux: `ru_maxrss` is in **kilobytes** (per POSIX). Multiply by 1024.
- A small helper `runtime.peak_rss_bytes()` does the platform check via
  `sys.platform` and returns bytes.

**Rationale**:
- The metric we actually care about (and that SC-011 validates) is
  the **run-level peak RSS** — i.e., the maximum across all steps,
  which is exactly the final `ru_maxrss`. A monotonically-increasing
  per-step series is what `getrusage` naturally gives us, and it's
  zero-cost to capture.
- Stdlib only — no `psutil` dependency.
- True "peak RSS during this step alone" would require sampling
  during the step (a thread or a periodic timer). Overkill for v1
  and harder to reason about; the cumulative-peak series is
  sufficient evidence for FR-013 / SC-011.

**Alternatives considered**:
- `psutil.Process().memory_info().rss` sampled in a background
  thread: gives true per-step peak, but adds a dependency and a
  sampling thread — too much for v1.
- `tracemalloc`: tracks Python-allocator memory only, not the
  whole process (lxml C-buffers wouldn't appear). Wrong signal.

---

## R-04: Progress logging at cadence with rate

**Decision**: A small helper class
`pipeline.runner.ProgressReporter(logger, step_name, cadence)` with:
- `report_iteration(n_done: int)` — checks `if n_done % cadence == 0`
  and emits a log line with elapsed seconds since `__init__` and
  instantaneous releases/sec (computed from delta since last
  report).
- `final()` — emits a final summary line at step end with total
  elapsed and average rate.

Used in `parse_releases`, `normalize_releases`,
`normalize_release_entities`, `build_release_format_summary`,
`build_release_fact`. The cadence comes from
`config.limits.log_progress_every`.

**Rationale**:
- Centralizes the cadence/rate math so each step is one or two extra
  lines.
- "Instantaneous rate since last report" is more useful than a
  cumulative average for spotting slowdowns.
- The final summary line is what tests grep for to validate
  SC-012.

**Alternatives considered**:
- A `tqdm` progress bar: nice for humans but doesn't write structured
  log entries. The spec asks for log lines.
- Plain `if n_done % cadence == 0: logger.info(...)` inline at every
  step: works, but the rate computation gets duplicated.

---

## R-05: SQL-based DQ checks above a row-count threshold

**Decision**: Refactor each "in-memory" DQ check function in
`quality/checks.py` to expose **two equivalent implementations**:

```python
def check_unique(table_or_path, col, *, name, layer, table_name) -> CheckResult: ...
def check_unique_sql(parquet_path, col, *, name, layer, table_name) -> CheckResult: ...
```

A new module `quality/dispatch.py` provides
`run_check(parquet_path, in_memory_fn, sql_fn, threshold) -> CheckResult`
that:
1. Reads the row count via `pyarrow.parquet.read_metadata(path).num_rows`
   (cheap, doesn't load data).
2. If `num_rows <= threshold`, calls `in_memory_fn(read_table(path), ...)`.
3. Otherwise, calls `sql_fn(path, ...)` which uses
   `duckdb.connect(":memory:").execute(...)` against
   `read_parquet('{path}')`.

Both paths MUST return a `CheckResult` with identical
`name`, `layer`, `table`, `severity`, `passed`, and equivalent
`details` (the exact text may differ; the parity test asserts
`passed` and `severity` equality).

The threshold is `config.limits.dq_check_in_memory_threshold`,
default `10_000_000`. Tests can lower it (e.g., 100) to exercise
the SQL paths against fixture-sized inputs.

**Rationale**:
- Unifies the dispatch logic in one place; each check function
  stays pure and testable.
- DuckDB SQL handles uniqueness, distinct counts, and at-most-one
  predicates natively without materializing columns. Memory bound
  is DuckDB's, not Python's.
- `pyarrow.parquet.read_metadata(...).num_rows` is the cheapest way
  to decide which path to take — no data load.
- A configurable threshold lets the test suite force the SQL path
  on small inputs (parity test), while the runtime default keeps
  the cheaper in-memory path for sample-sized data.

**Alternatives considered**:
- Always use SQL: simpler dispatch, but adds a DuckDB connection
  cost to every DQ check on small data (and to the existing 54
  Fase 1 unit tests, which would need refactoring).
- Always use in-memory with bounded streaming aggregations
  (e.g., a hand-rolled HyperLogLog for distinct counts): too much
  custom code for a course project; DuckDB is right there.

---

## R-06: Big-fixture integration test gating

**Decision**: `tests/integration/test_big_sample_pipeline.py` is
gated by:

```python
@pytest.mark.skipif(
    os.environ.get("DISCOGS_BIG_FIXTURE") != "1"
    or not BIG_FIXTURE.exists(),
    reason="big fixture not present or not opted in (set DISCOGS_BIG_FIXTURE=1)",
)
def test_big_sample_pipeline_passes_with_warnings(tmp_path):
    ...
```

**Rationale**:
- The 191 MB `releases_sample_big_raw.xml` is gitignored (per the
  spec Assumption); it lives only on developer laptops who chose
  to populate it.
- CI without the fixture and without the env var simply skips
  this test; CI with the fixture (or a developer running it
  locally) executes it.
- The two-condition gate (env var AND file presence) is
  belt-and-suspenders: explicit opt-in via env var prevents
  accidental long runs on a stranger's CI; the file check is the
  ultimate guard.

**Alternatives considered**:
- `pytest --runslow` flag: works but harder for a developer to
  remember; env var + file presence is more obvious.
- Skip silently if the file is missing: bad — easy to think the
  test ran when it didn't.

---

## R-07: UTF-8 round-trip

**Decision**: No change required. Python 3.12 reads file text as
UTF-8 by default; lxml emits Python strings (UTF-8 internally);
pyarrow stores `pa.string()` as UTF-8 bytes; DuckDB stores VARCHAR
as UTF-8. The Fase 1 codebase already handles non-ASCII (we have
`33 ⅓ RPM` and accented artist names in the raw sample) — there's
no encoding step to alter.

**Action**: Add an explicit unit test that round-trips a string with
non-ASCII characters through staging → clean → analytics → DuckDB
and asserts byte equality.

**Rationale**:
- FR-003 is mostly an attestation: "we don't break Unicode".
  Verifying it via a regression test is the cheapest way to keep
  that attestation honest.

---

## R-08: Truncation-warning placement in the manifest

**Decision**: Recorded as a free-standing warning (i.e., via
`manifest.warn(name, details)`) under
`quality_checks.warnings`, with name
`"parse_releases.truncated_xml"` and details containing the
last successful `release_id` and the exception message (truncated
to ~200 chars).

It is **not** a CheckResult — there's no `quality.checks.*`
function that fires it. It's emitted directly by the
`parse_releases` step when the parser stops early.

**Rationale**:
- Distinguishing parser-level events (truncation) from
  contract-violation checks (uniqueness, etc.) keeps the
  `quality_checks.results` list focused on §12 checks.
- The status derivation (`derive_status`) only looks at
  `results`, so a free-standing warning correctly surfaces
  `passed_with_warnings` without polluting check tallies.

**Alternatives considered**:
- Emit a synthetic `CheckResult` with `severity="warning"`,
  `passed=False`: would correctly classify but pollutes the
  results table. Rejected.

---

## R-09: Configuration additions to `base.yml`

**Decision**: Two new optional keys under `limits`, both with
defaults wired in `LimitConfig`:

```yaml
limits:
  parser_batch_size: 50000               # unchanged
  log_progress_every: 10000              # unchanged
  peak_rss_cap_gib: 4                    # NEW (FR-011)
  dq_check_in_memory_threshold: 10000000 # NEW (FR-014, R-05)
```

`LimitConfig` gains the two fields with the documented defaults so
existing `base.yml` files continue to work.

**Rationale**:
- Additive only — old configs keep working (FR-022).
- Defaults are the spec-stated values.
- Both knobs are needed to exercise the new behavior in tests
  (lowered threshold for parity tests; lowered cap for negative
  tests).

---

## R-10: Manifest schema additions

**Decision**: One new top-level key `step_metrics` (a mapping of
step name to a metrics dict). Initial fields per step:
- `peak_rss_bytes` (int, cumulative process peak at step end)
- `releases_per_sec` (float | null, populated only by per-release
  steps)

Plus one new well-known warning name:
- `runtime.peak_rss_exceeds_cap` — added when the per-step peak
  RSS exceeds `limits.peak_rss_cap_gib`.

`contracts/manifest.md` is updated in this change set.

**Rationale**:
- Top-level `step_metrics` cleanly separates "metrics" from
  "outputs" without colliding with existing fields.
- The exceeds-cap warning is informational per FR-013 (not a
  failure).

---

## Resolved spec clarifications (recap)

| Question | Answer | Encoded in |
|----------|--------|------------|
| Q1 — Phase scope | **B**: Fase 2 + Fase 3 only. | spec.md scope-at-a-glance + Assumptions; this plan's Summary |
| Q2 — Fase 3 acceptance evidence | **B**: real subset (`releases_sample_big_raw.xml`) + synthetic stress test. | spec.md US2 acceptance, SC-011/013/014; R-06 above |

## Outcome

All technology choices made. No `[NEEDS CLARIFICATION]` markers.
Constitution Check still PASS. Phase 1 (data-model.md, contracts/,
quickstart.md) can proceed.
