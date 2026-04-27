"""Threshold-based dispatch between in-memory and DuckDB-SQL DQ checks.

Per spec ``002-etl-scaleup`` FR-014 / ``research.md`` R-05: when a
Parquet's row count exceeds ``limits.dq_check_in_memory_threshold``,
the dispatcher routes the check through a DuckDB-SQL implementation
that does not materialize whole columns into Python collections.
Otherwise, the in-memory path is used (matching Fase 1 behavior).

Both implementations MUST return a CheckResult whose
``(name, layer, table, severity, passed)`` quintuple is identical
for the same input — the parity test enforces this.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pyarrow.parquet as pq

from ..pipeline.manifest import CheckResult


def run_check(
    parquet_path: str | Path,
    in_memory_fn: Callable[..., CheckResult],
    sql_fn: Callable[..., CheckResult],
    *positional: Any,
    threshold: int,
    **kwargs: Any,
) -> CheckResult:
    """Choose ``in_memory_fn`` or ``sql_fn`` based on parquet row count.

    - ``in_memory_fn(table, *positional, **kwargs)`` receives a loaded
      ``pyarrow.Table``.
    - ``sql_fn(path, *positional, **kwargs)`` receives the parquet path
      and is responsible for opening / closing its own DuckDB connection.
    """
    p = Path(parquet_path)
    num_rows = int(pq.read_metadata(p).num_rows)
    if num_rows <= threshold:
        return in_memory_fn(pq.read_table(p), *positional, **kwargs)
    return sql_fn(p, *positional, **kwargs)
