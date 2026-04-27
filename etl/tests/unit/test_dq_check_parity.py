"""Parity tests for in-memory vs DuckDB-SQL DQ check implementations.

For every dispatch-aware check, the in-memory function (taking a
pyarrow Table) and the SQL function (taking a parquet path) MUST agree
on ``(name, layer, table, severity, passed)`` for the same input.

The ``run_check`` dispatcher chooses between them by row count vs the
configured threshold; here we exercise BOTH paths directly to validate
parity. Threshold-based dispatch is also exercised at the end.
"""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from discogs_etl.quality.checks import (
    _check_at_most_one_primary,
    _check_at_most_one_primary_sql,
    _check_distinct_count_equals,
    _check_distinct_count_equals_sql,
    _check_unique,
    _check_unique_pair,
    _check_unique_pair_sql,
    _check_unique_sql,
)
from discogs_etl.quality.dispatch import run_check


def _write(tmp_path: Path, name: str, schema: pa.Schema, rows: list[dict]) -> Path:
    p = tmp_path / f"{name}.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), p)
    return p


def _identical(a, b) -> bool:
    return (
        a.name == b.name
        and a.layer == b.layer
        and a.table == b.table
        and a.severity == b.severity
        and a.passed == b.passed
    )


def test_unique_parity_pass_and_fail(tmp_path: Path):
    schema = pa.schema([pa.field("rid", pa.int64())])
    common = dict(name="t.rid_unique", layer="x", table_name="t")

    # Passing case: all distinct.
    pass_path = _write(tmp_path, "pass", schema, [{"rid": i} for i in range(5)])
    a = _check_unique(pq.read_table(pass_path), "rid", **common)
    b = _check_unique_sql(pass_path, "rid", **common)
    assert _identical(a, b) and a.passed is True

    # Failing case: a duplicate.
    fail_path = _write(tmp_path, "fail", schema, [{"rid": 1}, {"rid": 2}, {"rid": 1}])
    a = _check_unique(pq.read_table(fail_path), "rid", **common)
    b = _check_unique_sql(fail_path, "rid", **common)
    assert _identical(a, b) and a.passed is False


def test_unique_pair_parity_pass_and_fail(tmp_path: Path):
    schema = pa.schema([
        pa.field("rid", pa.int64()),
        pa.field("ord", pa.int32()),
    ])
    common = dict(name="t.pair_unique", layer="x", table_name="t")

    pass_path = _write(tmp_path, "pp", schema,
                       [{"rid": 1, "ord": 1}, {"rid": 1, "ord": 2}, {"rid": 2, "ord": 1}])
    a = _check_unique_pair(pq.read_table(pass_path), "rid", "ord", **common)
    b = _check_unique_pair_sql(pass_path, "rid", "ord", **common)
    assert _identical(a, b) and a.passed is True

    fail_path = _write(tmp_path, "pf", schema,
                       [{"rid": 1, "ord": 1}, {"rid": 1, "ord": 1}])
    a = _check_unique_pair(pq.read_table(fail_path), "rid", "ord", **common)
    b = _check_unique_pair_sql(fail_path, "rid", "ord", **common)
    assert _identical(a, b) and a.passed is False


def test_at_most_one_primary_parity_pass_and_fail(tmp_path: Path):
    schema = pa.schema([
        pa.field("rid", pa.int64()),
        pa.field("primary", pa.bool_()),
    ])
    common = dict(name="t.at_most_one_primary", layer="x", table_name="t")

    pass_path = _write(tmp_path, "amop_pass", schema,
                       [{"rid": 1, "primary": True}, {"rid": 1, "primary": False},
                        {"rid": 2, "primary": True}])
    a = _check_at_most_one_primary(pq.read_table(pass_path), "rid", "primary", **common)
    b = _check_at_most_one_primary_sql(pass_path, "rid", "primary", **common)
    assert _identical(a, b) and a.passed is True

    fail_path = _write(tmp_path, "amop_fail", schema,
                       [{"rid": 1, "primary": True}, {"rid": 1, "primary": True}])
    a = _check_at_most_one_primary(pq.read_table(fail_path), "rid", "primary", **common)
    b = _check_at_most_one_primary_sql(fail_path, "rid", "primary", **common)
    assert _identical(a, b) and a.passed is False


def test_distinct_count_equals_parity_pass_and_fail(tmp_path: Path):
    schema = pa.schema([pa.field("rid", pa.int64())])
    # 3 distinct values across 5 rows.
    path = _write(tmp_path, "dce", schema,
                  [{"rid": 1}, {"rid": 1}, {"rid": 2}, {"rid": 2}, {"rid": 3}])
    common = dict(name="t.distinct_eq", layer="x", table_name="t")

    a = _check_distinct_count_equals(pq.read_table(path), "rid",
                                       expected_count=3, **common)
    b = _check_distinct_count_equals_sql(path, "rid", expected_count=3, **common)
    assert _identical(a, b) and a.passed is True

    a = _check_distinct_count_equals(pq.read_table(path), "rid",
                                       expected_count=99, **common)
    b = _check_distinct_count_equals_sql(path, "rid", expected_count=99, **common)
    assert _identical(a, b) and a.passed is False


def test_run_check_dispatch_uses_in_memory_below_threshold(tmp_path: Path):
    """High threshold → in-memory path (number of rows = 3 < threshold)."""
    schema = pa.schema([pa.field("rid", pa.int64())])
    path = _write(tmp_path, "disp_lo", schema,
                  [{"rid": 1}, {"rid": 2}, {"rid": 3}])
    common = dict(name="t.unique", layer="x", table_name="t")
    r = run_check(path, _check_unique, _check_unique_sql, "rid",
                  threshold=10_000_000, **common)
    assert r.passed is True


def test_run_check_dispatch_uses_sql_above_threshold(tmp_path: Path):
    """Threshold lowered to 0 → SQL path. Same input must yield identical verdict."""
    schema = pa.schema([pa.field("rid", pa.int64())])
    path = _write(tmp_path, "disp_hi", schema,
                  [{"rid": 1}, {"rid": 1}])
    common = dict(name="t.unique", layer="x", table_name="t")
    in_mem = _check_unique(pq.read_table(path), "rid", **common)
    via_sql = run_check(path, _check_unique, _check_unique_sql, "rid",
                        threshold=0, **common)
    assert _identical(in_mem, via_sql) and via_sql.passed is False
