"""End-to-end persistence test for the JSONB NaN sanitization fix.

Pinned by `specs/010-jsonb-nan-sanitization/`. Builds a `ToolCall`
row whose `output_json` contains NaN floats (the production failure
mode), writes it through `ToolCallRepo.create`, flushes to the
SQLite test stratum, expires the session, fetches the row back,
and asserts:

(a) the flush did NOT raise;
(b) the fetched JSON contains zero NaN floats;
(c) the positions where NaN was now contain `None`;
(d) regular non-NaN values are preserved bit-exact.

Uses the existing `db_session` fixture (SQLite). The user-facing
failure is Postgres-only — SQLite would silently accept NaN
without sanitization. The fact that read-back returns `None`
(not the original NaN) IS the proof that the sanitizer ran.
"""

from __future__ import annotations

import math

from sqlalchemy.orm import Session

from discogs_agent.persistence.models import Run, ToolCall
from discogs_agent.persistence.repositories import (
    RunRepo,
    ThreadRepo,
    ToolCallRepo,
)


def _make_thread_and_run(session: Session) -> Run:
    """Helper: create a Thread + Run so the FK constraint on ToolCall
    is satisfied."""
    thread = ThreadRepo(session).create(metadata={})
    session.flush()
    run = RunRepo(session).create(
        thread_id=thread.thread_id,
        user_query="test query",
    )
    session.flush()
    return run


def _has_any_nan(value: object) -> bool:
    """Recursive NaN-presence check."""
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    if isinstance(value, dict):
        return any(_has_any_nan(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_any_nan(v) for v in value)
    return False


def test_tool_call_with_nan_output_json_persists_and_reads_back_clean(
    db_session: Session,
) -> None:
    run = _make_thread_and_run(db_session)

    # Construct the production-shaped output_json — a dataframe-preview
    # with one cell legitimately NaN (NULL country).
    dirty_output = {
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "result": {
            "sql": "SELECT country, COUNT(*) FROM release_unique_view GROUP BY 1",
            "chart_path": "/app/artifacts/abc/chart.html",
            "dataframe_preview": [
                {"country": "US", "number_of_releases": 1234567},
                {"country": "UK", "number_of_releases": 789012},
                {"country": float("nan"), "number_of_releases": 649673},
            ],
            "row_count": 3,
            "chart_type": "bar",
        },
    }

    tc = ToolCallRepo(db_session).create(
        run_id=run.run_id,
        node_name="sandbox_executor",
        tool_name="sandbox_executor",
        input_json={"generated_code": "..."},
        output_json=dirty_output,
        status="succeeded",
        latency_ms=100,
        error_message=None,
    )
    db_session.flush()
    tc_id = tc.tool_call_id
    db_session.expire_all()

    # Read back.
    fetched = db_session.get(ToolCall, tc_id)
    assert fetched is not None
    out = fetched.output_json
    assert out is not None

    # Assertion (a): flush did not raise — already proven by reaching here.
    # Assertion (b): no NaN floats anywhere in the fetched JSON.
    assert not _has_any_nan(out), f"Found NaN in fetched output_json: {out}"
    # Assertion (c): the position where NaN was now contains None.
    assert out["result"]["dataframe_preview"][2]["country"] is None
    # Assertion (d): regular non-NaN values are bit-exact.
    assert out["result"]["dataframe_preview"][0]["country"] == "US"
    assert out["result"]["dataframe_preview"][0]["number_of_releases"] == 1234567
    assert out["result"]["dataframe_preview"][2]["number_of_releases"] == 649673


def test_tool_call_with_clean_output_json_unchanged(db_session: Session) -> None:
    """Idempotence at the boundary: clean dicts pass through bit-exact."""
    run = _make_thread_and_run(db_session)
    clean_output = {
        "rows": [{"country": "US", "n": 100}, {"country": "UK", "n": 50}],
        "score": 3.14,
    }

    tc = ToolCallRepo(db_session).create(
        run_id=run.run_id,
        node_name="sandbox_executor",
        tool_name="sandbox_executor",
        input_json={},
        output_json=clean_output,
        status="succeeded",
        latency_ms=10,
        error_message=None,
    )
    db_session.flush()
    tc_id = tc.tool_call_id
    db_session.expire_all()

    fetched = db_session.get(ToolCall, tc_id)
    assert fetched is not None
    assert fetched.output_json == clean_output


def test_run_metadata_json_with_nan_persists_clean(db_session: Session) -> None:
    """Coverage for the breadth of FR-006: any JSONB column is protected,
    not just `agent_tool_calls.output_json`. Test against `agent_runs.metadata_json`."""
    thread = ThreadRepo(db_session).create(metadata={})
    db_session.flush()

    dirty_meta = {"cost_summary": {"total_usd": float("inf"), "tokens": 1000}}
    run = RunRepo(db_session).create(
        thread_id=thread.thread_id,
        user_query="x",
    )
    db_session.flush()
    # Set the dirty metadata via update_metadata (the public API).
    RunRepo(db_session).update_metadata(run.run_id, cost_summary=dirty_meta["cost_summary"])
    db_session.flush()
    db_session.expire_all()

    fetched = db_session.get(Run, run.run_id)
    assert fetched is not None
    assert not _has_any_nan(fetched.metadata_json)
    assert fetched.metadata_json["cost_summary"]["total_usd"] is None
    assert fetched.metadata_json["cost_summary"]["tokens"] == 1000
