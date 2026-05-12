"""Unit tests for the hot-patch failed_safety classification branch
in response_synthesizer._build_result_block.

Added 2026-05-11 alongside 015-classifier-carryover as a hot-patch
addressing the misleading "data contract" wording that pre-patch
applied to every failed_safety run regardless of the actual rule
class. Run `4b781b03-...` (2026-05-11) failed with `sql_invalid` (a
DuckDB binder error about an ambiguous column reference) but the
user-facing message said "referenced something not allowed by the
data contract" — wrong class.

The patch surfaces the violation rule class (`contract` /
`sql_quality` / `code_shape` / `other`) into the result_block so the
synthesizer LLM can pick accurate wording. These tests lock the
classification logic at the unit level.
"""

from __future__ import annotations

from discogs_agent.graph.nodes.response_synthesizer import _build_result_block


def _state_with_violations(rules: list[str]) -> dict:
    """Build a minimal AgentState-shaped dict that simulates a
    failed_safety run with the given violation rules."""
    return {
        "terminal_status": "failed_safety",
        "generated_sql": "SELECT 1",  # something to keep _build_result_block happy
        "safety_result": {
            "allowed": False,
            "violations": [{"rule": r, "detail": "stub"} for r in rules],
        },
    }


def test_sql_invalid_classifies_as_sql_quality() -> None:
    """The trigger case from run 4b781b03-...: DuckDB binder error
    on an ambiguous column should classify as `sql_quality`, NOT
    `contract` (which would mislead the user about what failed)."""
    block = _build_result_block(_state_with_violations(["sql_invalid"]))
    assert "Failed-safety rules: sql_invalid (class: sql_quality)" in block


def test_read_only_required_classifies_as_code_shape() -> None:
    """Missing `read_only=True` (or missing duckdb.connect entirely)
    is a code-shape issue, not a contract violation."""
    block = _build_result_block(_state_with_violations(["read_only_required"]))
    assert "Failed-safety rules: read_only_required (class: code_shape)" in block


def test_forbidden_table_classifies_as_contract() -> None:
    """Non-allowlisted table reference is a contract violation —
    the pre-patch wording was accurate for this case."""
    block = _build_result_block(_state_with_violations(["forbidden_table"]))
    assert "class: contract" in block


def test_forbidden_join_classifies_as_contract() -> None:
    """014's forbidden_join rule is contract-class."""
    block = _build_result_block(_state_with_violations(["forbidden_join"]))
    assert "class: contract" in block


def test_ddl_dml_classifies_as_contract() -> None:
    """DDL/DML keyword in generated SQL is a contract violation."""
    block = _build_result_block(_state_with_violations(["ddl_dml"]))
    assert "class: contract" in block


def test_mixed_violations_sql_quality_wins() -> None:
    """When multiple rules fire across attempts, sql_quality takes
    precedence (it's the most actionable for the user — they can
    rephrase to get past it). Contract-class is the fallback for
    operator-side issues; sql_quality is the user-facing hint."""
    block = _build_result_block(
        _state_with_violations(["forbidden_table", "sql_invalid"])
    )
    assert "class: sql_quality" in block


def test_no_violations_no_class_line() -> None:
    """If terminal_status is failed_safety but safety_result is
    empty (shouldn't happen in practice — a failed_safety run by
    definition has at least one violation — but the function must
    not crash on the degenerate state)."""
    state = {
        "terminal_status": "failed_safety",
        "generated_sql": "SELECT 1",
        "safety_result": {"allowed": False, "violations": []},
    }
    block = _build_result_block(state)
    # No class-label line is appended; the synthesizer falls through
    # to the contract-class wording per the prompt's "or no class
    # line" fallback.
    assert "Failed-safety rules:" not in block


def test_non_failed_safety_state_unaffected() -> None:
    """The failed_safety branch must not fire when the terminal
    status is succeeded / failed_validation / etc. Regression
    guard for the existing branches (empty / OOM / valid)."""
    state = {
        "terminal_status": "succeeded",
        "generated_sql": "SELECT 1",
        "validation_result": {"valid": True},
    }
    block = _build_result_block(state)
    assert "Failed-safety rules:" not in block
