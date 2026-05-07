"""Integration regression test for the schema-context join graph.

Pinned by `specs/009-schema-context-join-graph/`. Locks in the exact wording
of the rendered block (via a golden snapshot) so any drift in the
join-graph section, the table list, or the sample-values format surfaces
in CI rather than silently in the LLM's prompt.

Failure mode this prevents: a future ETL change (or an unintentional
refactor of `render_schema_block`) silently changes what the LLM sees,
re-opening the silent wrong-join failure mode that 009 closed.

To intentionally update the golden snapshot:

    UPDATE_GOLDEN=1 pytest tests/integration/test_schema_context_join_graph.py

Then commit the regenerated `golden/schema_context_block.txt` with a PR
description explaining what changed and why.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from discogs_agent.duckdb_layer import schema as schema_module
from discogs_agent.duckdb_layer.schema import read_schema_context

GOLDEN_PATH = Path(__file__).parent / "golden" / "schema_context_block.txt"


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    schema_module.reset_schema_cache()


def _read_golden() -> str:
    if not GOLDEN_PATH.exists():
        pytest.fail(
            f"Golden snapshot missing at {GOLDEN_PATH}. "
            "Run `UPDATE_GOLDEN=1 pytest tests/integration/test_schema_context_join_graph.py` "
            "to generate it, then commit the file."
        )
    return GOLDEN_PATH.read_text()


def test_rendered_block_matches_golden(seed_duckdb: Path) -> None:
    """The full rendered schema-context block matches the committed
    golden snapshot. Drift in tables, samples, or the join graph
    fails this test."""
    ctx = read_schema_context(str(seed_duckdb))
    actual = ctx["rendered_block"]

    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(actual)
        pytest.skip(
            f"Wrote new golden snapshot to {GOLDEN_PATH}. "
            "Re-run tests without UPDATE_GOLDEN to verify."
        )

    expected = _read_golden()
    if actual != expected:
        # Custom diff message that points the reviewer at the quickstart's
        # revert-and-rerun sanity check (SC-003).
        pytest.fail(
            "Rendered schema-context block has drifted from the golden "
            f"snapshot at {GOLDEN_PATH}.\n\n"
            "If this drift is intentional (you added a new edge, a new "
            "glossary entry, etc.), regenerate the snapshot:\n"
            "  UPDATE_GOLDEN=1 pytest tests/integration/test_schema_context_join_graph.py\n\n"
            "If this drift is unintentional, see "
            "specs/009-schema-context-join-graph/quickstart.md §3 for the "
            "revert-and-rerun sanity check.\n\n"
            f"--- expected (golden, {len(expected)} chars) ---\n"
            f"{expected}\n"
            f"--- actual ({len(actual)} chars) ---\n"
            f"{actual}\n"
        )


def test_join_graph_subsection_present_on_seed(seed_duckdb: Path) -> None:
    """Defensive: even if the golden file is missing, the join-graph
    section's most load-bearing line MUST be present."""
    ctx = read_schema_context(str(seed_duckdb))
    block = ctx["rendered_block"]

    # The single most load-bearing line: the namespaces hint.
    assert (
        "DIFFERENT identifier namespaces" in block
        or "different identifier namespaces" in block.lower()
    ), "Join graph's namespaces hint is missing — the bug 009 fixed could recur."

    # The canonical forbidden-join line.
    assert "master_fact.master_id  =  release_artist_bridge.release_id" in block, (
        "Forbidden-join anti-pattern is missing from the rendered block. "
        "Without it, the LLM may silently re-introduce the cross-grain "
        "join bug that 009 fixed."
    )


def test_join_graph_section_omitted_master_when_no_master_fact(
    seed_duckdb_no_master: Path,
) -> None:
    """On a release-only catalog (no master_fact), the join graph
    renders without master-side content."""
    ctx = read_schema_context(str(seed_duckdb_no_master))
    block = ctx["rendered_block"]

    assert "Join graph" in block, "Join graph section should render even without master_fact."

    # No master_fact references in the join-graph section. We scope the check
    # to the join-graph slice because release_fact / release_unique_view
    # legitimately have a master_id column listed in the table block.
    join_start = block.index("Join graph")
    join_end = block.index("Domain glossary") if "Domain glossary" in block else len(block)
    join_section = block[join_start:join_end]
    assert "master_fact" not in join_section, (
        "Join graph section must omit master_fact references when "
        "the catalog has no master_fact table."
    )
    assert "Forbidden joins" not in join_section, (
        "Forbidden-joins sub-block should be omitted when there is no "
        "master_fact (no master-side joins to forbid)."
    )


def test_rendered_block_within_token_budget(seed_duckdb: Path) -> None:
    """Post-009 the rendered block adds ~220 tokens for the join-graph
    section. Verify total stays comfortably under the 1200-token budget."""
    ctx = read_schema_context(str(seed_duckdb))
    assert ctx["rendered_token_count"] <= 1200, (
        f"Rendered block exceeds 1200-token budget: "
        f"{ctx['rendered_token_count']} tokens. "
        "Either tighten the join-graph wording or expand the budget."
    )
