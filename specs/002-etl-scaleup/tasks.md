---

description: "Task list for Discogs ETL — Fase 2+3 (real-data robustness + laptop-scale)"
---

# Tasks: Discogs ETL — Fase 2+3 (Real-data robustness + laptop-scale)

**Input**: Design documents from `specs/002-etl-scaleup/`
**Prerequisites**: `plan.md` (✅), `spec.md` (✅), `research.md` (✅),
`data-model.md` (✅), `contracts/cli.md` (✅),
`contracts/manifest.md` (✅), `quickstart.md` (✅).
**Builds on**: `specs/001-discogs-etl/` (Fase 1 — merged into `main`).

**Tests**: Recommended (not strictly TDD-gated). Per the spec's
Testing strategy and `research.md` R-06 (big-fixture gating) and
R-09 / R-10 (parity), test tasks are included throughout — they're
part of the intended deliverable.

**Organization**: Two user stories — **US1** (Fase 2: real-data
robustness) and **US2** (Fase 3: laptop-scale execution). US1 is the
MVP increment.

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on
  incomplete tasks).
- **[Story]**: User-story label (`[US1]` or `[US2]`). Required for
  Phase 3+ tasks; absent for Setup, Foundational, and Polish.

## Path Conventions

- Component code: `etl/src/discogs_etl/...`
- Component tests: `etl/tests/{unit,integration,fixtures}/...`
- Component config: `etl/configs/...`
- Spec docs: `specs/002-etl-scaleup/...`
- Runtime data (gitignored): `data/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Wire the two new optional config keys into the
`etl/configs/base.yml` schema and the `LimitConfig` dataclass so
every later task can rely on them being present.

- [X] T001 [P] Update `etl/configs/base.yml`: add
  `limits.peak_rss_cap_gib: 4` and
  `limits.dq_check_in_memory_threshold: 10000000` to the existing
  `limits:` block. Preserve the existing keys
  (`parser_batch_size`, `log_progress_every`).
- [X] T002 [P] Extend the `LimitConfig` dataclass in
  `etl/src/discogs_etl/pipeline/context.py` with two new fields:
  `peak_rss_cap_gib: int = 4` and
  `dq_check_in_memory_threshold: int = 10_000_000`. Update
  `RunConfig.load()` to read both keys with their dataclass
  defaults if absent (i.e., a Fase 1 `base.yml` without these keys
  must continue to work — FR-022 backward compatibility).

**Checkpoint**: After Phase 1, `RunConfig.load("etl/configs/base.yml")`
returns a `LimitConfig` with both new fields populated, and the
54 Fase 1 tests still pass unchanged.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the cross-cutting plumbing that BOTH user stories
depend on — peak RSS measurement helper, progress reporter helper,
manifest extension, runner integration, and the gzip-aware input
opener.

**⚠️ CRITICAL**: User stories cannot begin until this phase is
complete.

- [X] T003 [P] Add `etl/src/discogs_etl/pipeline/runtime.py` with
  `peak_rss_bytes() -> int`. Implementation: call
  `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` and
  normalize to bytes — on macOS (`sys.platform == "darwin"`) the
  value is already bytes; on Linux it is kilobytes (multiply by
  1024). Per `research.md` R-03.
- [X] T004 [P] Add `etl/src/discogs_etl/pipeline/progress.py` with
  `class ProgressReporter`. Constructor:
  `__init__(self, logger, step_name: str, cadence: int)`. Methods:
  `report_iteration(self, n_done: int) -> None` (logs at the
  cadence with elapsed seconds since `__init__` and instantaneous
  releases/sec computed from delta since last report);
  `final(self) -> dict` (returns `{"releases_per_sec": float,
  "elapsed_seconds": float}` for the manifest, and emits a final
  summary log line). Per `research.md` R-04.
- [X] T005 Update `etl/src/discogs_etl/pipeline/manifest.py`:
  (a) initialize `step_metrics: dict = {}` at the top level inside
  `Manifest.create()`; (b) add a method
  `record_step_metrics(self, step_name: str, **metrics: Any) ->
  None` that writes into `self._data["step_metrics"][step_name]`,
  merging if a partial entry already exists. Shape per
  `contracts/manifest.md` (this spec) and `data-model.md`.
- [X] T006 Update `etl/src/discogs_etl/pipeline/runner.py`: at the
  end of every step (in both the success path and the
  exception-handler path), call `runtime.peak_rss_bytes()` and
  `manifest.record_step_metrics(step.name,
  peak_rss_bytes=<value>)`. After recording, if
  `<value> > config.limits.peak_rss_cap_gib * (1 << 30)`, append a
  `runtime.peak_rss_exceeds_cap` warning to the manifest with
  details `f"step={step.name} peak={value} cap={cap_bytes}"`.
  Depends on T003 + T005.
- [X] T007 [P] Add `etl/src/discogs_etl/io/input.py` with
  `open_releases_input(snapshot_dir: Path) -> ReleasesInput` (a
  small dataclass with `file_obj: BinaryIO`, `source_path: Path`,
  `is_gzipped: bool`, `gz_and_plain_present: bool`). Detection:
  prefer `releases.xml` if present, else `releases.xml.gz` opened
  via `gzip.GzipFile(path, "rb")`. If both exist, pick uncompressed
  and set `gz_and_plain_present = True`. Raise `FileNotFoundError`
  with a clear message if neither exists. Per `research.md` R-02.

**Checkpoint**: After Phase 2:
`python -c "from discogs_etl.pipeline import runtime, progress, manifest, runner; from discogs_etl.io import input as _; print('ok')"`
imports cleanly. Re-running the Fase 1 integration test
(`pytest etl/tests/integration/test_sample_pipeline.py`) still
passes — including the new `step_metrics` block in the manifest is
populated for every step.

---

## Phase 3: User Story 1 — Real-data robustness on the 404-release sample (Priority: P1) 🎯 MVP

**Goal**: The pipeline runs end-to-end against
`etl/tests/fixtures/releases_sample_raw.xml` (404 real Discogs
releases, truncated mid-element at line 10000) without crashes.
Truncation surfaces as a manifest warning; status is
`passed_with_warnings`; exit is 0.

**Independent Test**:

```bash
mkdir -p data/raw/discogs/discogs-2026-04
cp etl/tests/fixtures/releases_sample_raw.xml data/raw/discogs/discogs-2026-04/releases.xml
python -m discogs_etl.cli run --config etl/configs/base.yml ; echo "exit=$?"
# expect exit=0 and quality_checks.status="passed_with_warnings"
duckdb data/published/duckdb/discogs.duckdb -c \
  'SELECT COUNT(DISTINCT release_id) FROM release_fact;'
# expect 404
```

### Tests for User Story 1 (recommended)

- [X] T008 [P] [US1] Add
  `etl/tests/unit/test_truncation_warning.py`: feed a small
  inline-truncated XML to the parser, assert iteration completes
  cleanly (no exception escapes), and the parser exposes a
  `truncation_info` (or equivalent) attribute populated with the
  last successfully-emitted `release_id` and the underlying
  `XMLSyntaxError` message.
- [X] T009 [P] [US1] Add
  `etl/tests/integration/test_real_sample_pipeline.py`: invoke
  the `run` CLI subcommand against
  `etl/tests/fixtures/releases_sample_raw.xml`. Assertions:
  exit code 0; manifest `quality_checks.status ==
  "passed_with_warnings"`; warnings include
  `"parse_releases.truncated_xml"` with last release id near 414;
  DuckDB `COUNT(DISTINCT release_id) FROM release_fact == 404`;
  at least one `release_fact.format_description_summary` value
  contains the non-ASCII `'⅓'` character (UTF-8 round-trip,
  FR-003 / SC-002); manifest contains a non-empty
  `step_metrics.parse_releases.peak_rss_bytes`.

### Implementation for User Story 1

- [X] T010 [US1] Update
  `etl/src/discogs_etl/parsers/releases_parser.py`: convert
  `iter_releases(path, *, limit=None)` from a free function into
  a stateful object (e.g., `class ReleaseStream`) so the caller
  can read post-iteration state. Wrap the existing
  `lxml.etree.iterparse(...)` loop in
  `try / except etree.XMLSyntaxError as e`. On exception: stop
  yielding, set `self.truncation_info = TruncationInfo(last_release_id=<id>, error_message=str(e)[:200])`,
  return cleanly. The existing memory-cleanup pattern
  (`elem.clear()` + walk-back-siblings) MUST stay intact. Per
  `research.md` R-01.
- [X] T011 [US1] Update
  `etl/src/discogs_etl/steps/parse_releases.py` to use the new
  `ReleaseStream` API. After iteration ends, check
  `stream.truncation_info`; if non-None, call
  `manifest.warn("parse_releases.truncated_xml",
  details=f"last_release_id={info.last_release_id};
  error={info.error_message}")`. The existing dropped-no-id
  warning behavior (FR-005) is preserved unchanged.
- [X] T012 [US1] Update
  `etl/src/discogs_etl/steps/prepare_sources.py` to call
  `io.input.open_releases_input(ctx.raw_snapshot_dir)` instead of
  hard-coding `releases.xml`. Use the returned `ReleasesInput`
  dataclass: record size + checksum of `source_path`; if
  `is_gzipped`, emit a `prepare_sources.gz_input` warning; if
  `gz_and_plain_present`, additionally emit
  `prepare_sources.gz_and_plain_present`. Close the file_obj
  after checksum (the parser will reopen via the same helper —
  see T016).

**Checkpoint**: US1 complete when T009 passes locally
(`pytest etl/tests/integration/test_real_sample_pipeline.py -v`).
Fase 1 tests still pass unchanged.

---

## Phase 4: User Story 2 — Laptop-scale execution (Priority: P2)

**Goal**: The pipeline accepts gzipped input transparently, emits
progress logs at the configured cadence with elapsed time and
rate, records peak RSS per step in the manifest, and runs the
~49,689-release big fixture under the 4 GiB cap. The DQ checks
have SQL alternatives that engage above the configured threshold,
returning identical `CheckResult` shapes as the in-memory paths.

**Independent Test**:

```bash
# Gzip parity (no big fixture required):
gzip -k data/raw/discogs/discogs-2026-04/releases.xml
rm data/raw/discogs/discogs-2026-04/releases.xml
python -m discogs_etl.cli run --config etl/configs/base.yml --run-id gz-only ; echo "exit=$?"
# expect exit=0; manifest warns prepare_sources.gz_input; published DB matches uncompressed parity

# Big fixture (only if file is on disk locally):
DISCOGS_BIG_FIXTURE=1 pytest etl/tests/integration/test_big_sample_pipeline.py -v
```

### Tests for User Story 2 (recommended)

- [X] T013 [P] [US2] Add `etl/tests/unit/test_gzip_input.py`:
  given a tiny in-memory XML, write both an uncompressed and a
  gzipped copy to a tmp dir, call
  `io.input.open_releases_input` for each, assert: (a) the
  uncompressed copy is preferred when both exist with
  `gz_and_plain_present=True`; (b) only-`.gz` returns
  `is_gzipped=True`; (c) bytes read from the file_obj match the
  uncompressed source byte-for-byte in both cases; (d)
  `FileNotFoundError` when neither exists.
- [X] T014 [P] [US2] Add
  `etl/tests/unit/test_dq_check_parity.py`: for each of the
  dispatch-aware checks
  (`unique`, `unique_pair`, `at_most_one_primary`,
  `distinct_count`), construct a synthetic `pyarrow.Table` with
  ~50 rows, write it to a tmp Parquet, then run the in-memory
  function and the SQL function (override threshold to 1 to
  force the SQL path). Assert that
  `(name, layer, table, severity, passed)` are identical. Run
  both pass and fail cases per check.
- [X] T015 [P] [US2] Add
  `etl/tests/integration/test_big_sample_pipeline.py`: gated by
  `os.environ.get("DISCOGS_BIG_FIXTURE") == "1"` AND the file
  existing (skip otherwise per `research.md` R-06). Stage
  `etl/tests/fixtures/releases_sample_big_raw.xml` to the raw
  path, invoke the CLI run, then assert: exit 0; status
  `passed_with_warnings`; truncation warning present; DuckDB
  `COUNT(DISTINCT release_id) = 49689` (allow ±5 for any dropped
  empty-id rows surfaced as warnings);
  `step_metrics.parse_releases.peak_rss_bytes < 4 * (1<<30)`;
  ≥3 progress log lines emitted by the parse step (cadence=10000,
  ~5 reports expected).

### Implementation for User Story 2

- [X] T016 [US2] Update
  `etl/src/discogs_etl/parsers/releases_parser.py` so it opens
  its own file via `io.input.open_releases_input(path.parent)`
  (or accepts a `Path` and dispatches internally). Pass the
  resulting binary file object to
  `lxml.etree.iterparse(file_obj, events=("end",), tag="release")`.
  The truncation handling from T010 is preserved unchanged.
  Compatible with the path-only API used by Fase 1 tests.
- [X] T017 [US2] Update
  `etl/src/discogs_etl/steps/parse_releases.py` to instantiate a
  `ProgressReporter(ctx.logger, "parse_releases",
  ctx.config.limits.log_progress_every)`. Call
  `reporter.report_iteration(n_emitted)` inside the loop after
  each successful release write. Replace the existing
  end-of-step `log.info(...)` summary with
  `metrics = reporter.final()` and call
  `manifest.record_step_metrics("parse_releases",
  releases_per_sec=metrics["releases_per_sec"])`.
- [X] T018 [P] [US2] Update
  `etl/src/discogs_etl/steps/normalize_releases.py` to integrate
  `ProgressReporter` over the per-release loop (same pattern as
  T017). Record `releases_per_sec` via
  `manifest.record_step_metrics`.
- [X] T019 [P] [US2] Update
  `etl/src/discogs_etl/steps/normalize_release_entities.py` to
  integrate `ProgressReporter` over the largest sub-loop (the
  format normalization is typically the largest; the helper can
  be applied to any of the inner loops). Record
  `releases_per_sec` via `manifest.record_step_metrics`.
- [X] T020 [P] [US2] Update
  `etl/src/discogs_etl/steps/build_release_format_summary.py` to
  integrate `ProgressReporter` over the per-release output loop.
- [X] T021 [P] [US2] Update
  `etl/src/discogs_etl/steps/build_release_fact.py` to integrate
  `ProgressReporter` over the per-row release_fact write loop.
- [X] T022 [US2] Add `etl/src/discogs_etl/quality/dispatch.py`:
  `def run_check(parquet_path: Path, in_memory_fn: Callable,
  sql_fn: Callable, threshold: int, **kwargs) -> CheckResult`.
  Read row count via
  `pyarrow.parquet.read_metadata(parquet_path).num_rows`; if
  `num_rows <= threshold`, call
  `in_memory_fn(pq.read_table(parquet_path), **kwargs)`; else
  call `sql_fn(parquet_path, **kwargs)`. Per `research.md` R-05.
- [X] T023 [US2] Update
  `etl/src/discogs_etl/quality/checks.py` to add SQL siblings:
  `_check_unique_sql(parquet_path, col, *, name, layer, table_name)`,
  `_check_unique_pair_sql(parquet_path, c1, c2, ...)`,
  `_check_at_most_one_primary_sql(parquet_path, group_col, flag_col, ...)`,
  `_check_distinct_count_sql(parquet_path, col, expected_count, ...)`.
  Each opens `duckdb.connect(":memory:")`, runs the
  corresponding bounded-memory query, returns a `CheckResult`
  with the SAME `(name, layer, table, severity, passed)`
  semantics as its in-memory sibling. Refactor
  `run_staging_checks`, `run_clean_checks`,
  `run_analytics_checks` so each dispatch-eligible call goes
  through `dispatch.run_check(...)` with the threshold from
  `ctx.config.limits.dq_check_in_memory_threshold`. Non-eligible
  checks (`_check_no_null`, `_check_in_set`, `_check_min_value`)
  remain unchanged. Per `research.md` R-05 + `data-model.md`
  DQ-dispatch table.

**Checkpoint**: US2 complete when T013, T014 pass locally
(`pytest etl/tests/unit/test_gzip_input.py
etl/tests/unit/test_dq_check_parity.py -v`) AND, with the big
fixture on disk and `DISCOGS_BIG_FIXTURE=1` set, T015 passes
(`pytest etl/tests/integration/test_big_sample_pipeline.py -v`).

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validate the whole spec end-to-end and refresh
component docs.

- [X] T024 Run the full test suite from the repo root:
  `pytest etl/tests/`. Expected: all 54 Fase 1 tests still pass
  (SC-003) plus the new Fase 2/3 tests pass. Record total wall
  clock — typical target is ~1 second on a developer laptop for
  the unit + Fase 2 integration set (the Fase 3 integration test
  is gated and skipped here).
- [X] T025 If the big fixture
  (`etl/tests/fixtures/releases_sample_big_raw.xml`) is on disk
  locally, run
  `DISCOGS_BIG_FIXTURE=1 pytest etl/tests/integration/test_big_sample_pipeline.py -v`
  and capture metrics from the resulting manifest:
  `step_metrics.parse_releases.peak_rss_bytes`,
  `step_metrics.parse_releases.releases_per_sec`,
  total wall clock. Compare against SC-011 (peak RSS < 4 GiB)
  and target wall clock (~3 minutes). Record findings in the
  PR / merge-request description.
- [X] T026 [P] Update `etl/README.md` to mention the Fase 2+3
  features (gzipped input via `releases.xml.gz`, progress logs
  with elapsed + rate, peak-RSS-per-step in the manifest, the
  `DISCOGS_BIG_FIXTURE` env-var-gated big-fixture integration
  test). Cross-reference `specs/002-etl-scaleup/quickstart.md`
  for the full walkthrough.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no prerequisites; T001 and T002 are
  independent and can run in parallel.
- **Phase 2 (Foundational)**: depends on Phase 1. Within Phase 2:
  T003, T004, T007 are [P] with each other; T005 (manifest) is
  also independent — [P] with the other three; T006 (runner)
  depends on T003 + T005.
- **Phase 3 (US1)**: depends on Phase 2 complete. Within US1:
  T008 (parser unit test) is [P] with T010 (parser implementation)
  if pursuing TDD; otherwise T010 → T011 → T012 are sequential
  through `parse_releases` step coupling.
- **Phase 4 (US2)**: depends on Phase 2 complete; T015 / T017 also
  depend on T010+T011 (US1's parser refactor). The fully-parallel
  cuts within US2 (T018–T021 across separate step files) become
  available once T004 (ProgressReporter) is in.
- **Phase 5 (Polish)**: depends on US1 + US2. T024 is the
  convergence test; T025 is optional / local-only; T026 is [P].

### User Story Dependencies

- **US1 (P1)**: depends only on Phase 2 (foundational).
  Independent test = SC-001 + SC-002. Can ship without US2.
- **US2 (P2)**: shares the foundational layer with US1; touches
  the parser via T016 after US1's T010, but otherwise independent
  of US1. Independent test = SC-010 + SC-011 + SC-013 + SC-014.

### Parallel Opportunities

- **Phase 1**: T001 / T002 [P].
- **Phase 2**: T003 / T004 / T005 / T007 all [P]; then T006.
- **Phase 3 (US1)**: T008 / T009 [P] (different test files); T010
  must happen before T011; T012 [P] with T010.
- **Phase 4 (US2)**:
  - T013 / T014 / T015 [P] (different test files; T015 gated by
    env var so it doesn't actually run in fast iteration).
  - T018 / T019 / T020 / T021 [P] (different step files; depend
    on T004).
  - T016 + T017 sequence through `parse_releases.py`; not [P]
    with each other.
  - T022 must precede T023 (dispatch is the contract).
- **Phase 5**: T026 [P]; T024 / T025 sequential (T024 before T025
  to confirm no Fase 1 regression).

---

## Parallel Example: User Story 2 progress reporters

```bash
# After T004 (ProgressReporter) and Phase 2 land, four step files
# can be modified independently:
Task: "Update steps/normalize_releases.py with ProgressReporter (T018)"
Task: "Update steps/normalize_release_entities.py with ProgressReporter (T019)"
Task: "Update steps/build_release_format_summary.py with ProgressReporter (T020)"
Task: "Update steps/build_release_fact.py with ProgressReporter (T021)"
```

## Parallel Example: tests across both stories

```bash
# After Phase 2 lands, all five test files can be drafted in
# parallel before — or alongside — the implementation tasks they
# verify:
Task: "Add tests/unit/test_truncation_warning.py (T008)"
Task: "Add tests/integration/test_real_sample_pipeline.py (T009)"
Task: "Add tests/unit/test_gzip_input.py (T013)"
Task: "Add tests/unit/test_dq_check_parity.py (T014)"
Task: "Add tests/integration/test_big_sample_pipeline.py (T015)"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 (Setup): T001 + T002.
2. Phase 2 (Foundational): T003–T007 (T006 last).
3. Phase 3 (US1): T008–T012 (TDD-friendly: write T008 + T009
   first, watch them fail; then T010 → T011 → T012).
4. **STOP and VALIDATE**: SC-001 + SC-002 met locally. Fase 1
   tests still pass.
5. (Optional) ship US1 alone if scaleup is deprioritized.

### Incremental Delivery

US1 ships an immediate increment ("the pipeline survives real
Discogs data without crashing") that is independently valuable.
US2 builds on top without changing US1's behavior (no schema
changes, no contract changes).

### Parallel Team Strategy

- Two developers: split Phase 2 (T003+T004+T007 vs T005+T006),
  then tackle US1 + US2 in parallel after Phase 2 lands.
- More than two: marginal returns; the integration surface is a
  single CLI tying ten steps together.

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete
  tasks.
- `[US1]` / `[US2]` labels map every Phase 3 / Phase 4 task to the
  user story it serves. Setup, Foundational, and Polish phases
  carry no story label.
- Tests are recommended, not gated. T008 / T009 / T013 / T014 /
  T015 can be skipped without blocking SC acceptance, but are
  strongly encouraged given Fase 1's precedent.
- The big-fixture integration test (T015) is gated by
  `DISCOGS_BIG_FIXTURE=1` AND file presence — both must hold for
  the test to run (per `research.md` R-06). CI without the fixture
  silently skips it.
- No published-DuckDB schema changes anywhere in this spec
  (FR-021). Every change is either backwards-compatible or
  additive.
- Commit after each task or logical group; smaller commits help
  bisects on observability or scale regressions.
- Avoid: vague tasks, same-file conflicts inside a `[P]` set,
  cross-step dependencies that break the runner's ability to
  invoke a single step in isolation.
