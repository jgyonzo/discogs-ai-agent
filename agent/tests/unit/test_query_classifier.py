"""Tests for the query_classifier tool against the LLM stub."""

from __future__ import annotations

from pathlib import Path

import pytest

from discogs_agent.duckdb_layer import schema as schema_module
from discogs_agent.observability.tracing import use_node
from discogs_agent.tools.dataset_schema_reader import (
    SchemaReaderInput,
    dataset_schema_reader,
)
from discogs_agent.tools.query_classifier import ClassifierInput, query_classifier


@pytest.fixture
def schema(seed_duckdb: Path, llm_stub: None) -> dict:
    schema_module.reset_schema_cache()
    with use_node("load_schema"):
        out = dataset_schema_reader(SchemaReaderInput(duckdb_path=str(seed_duckdb)))
    return out.model_dump()


def test_simple_query_routes_to_simple(schema: dict) -> None:
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(user_query="Show releases by decade.", schema_context=schema)
        )
    assert out.complexity == "simple"
    assert out.selected_model is not None


def test_complex_query_routes_to_complex(schema: dict) -> None:
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="Which labels have the most stylistic diversity?",
                schema_context=schema,
            )
        )
    assert out.complexity == "complex"
    assert out.selected_model is not None


def test_price_query_is_unsupported(schema: dict) -> None:
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="What is the average price of Techno releases?",
                schema_context=schema,
            )
        )
    assert out.complexity == "unsupported"
    assert out.selected_model is None


def test_ambiguous_query_needs_clarification(schema: dict) -> None:
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="Show me the best labels.",
                schema_context=schema,
            )
        )
    assert out.complexity == "clarification_needed"
    assert out.selected_model is None


def test_techno_query_routes_to_simple_not_unsupported(schema: dict) -> None:
    """005-agent-schema-context regression: 'Techno' is a valid `style`
    value surfaced in the enriched schema_context's sample block. The
    router MUST classify it as simple/complex, NOT unsupported."""
    assert "rendered_block" in schema
    assert "Techno" in schema["rendered_block"]
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="Show the evolution of Techno releases over time",
                schema_context=schema,
            )
        )
    assert out.complexity in ("simple", "complex"), (
        f"Techno query routed to {out.complexity!r}; should be simple/complex "
        "since 'Techno' appears in the style sample of the schema context."
    )
    assert out.selected_model is not None


# ─── 015-classifier-carryover: multi-turn follow-up resolution ──


def test_follow_up_with_carryover_routes_to_simple_or_complex(schema: dict) -> None:
    """The 015 trigger case (thread 9214f7fb-...).

    A short anaphoric follow-up question ("and what is the second
    one?") preceded by an explicit ranked-by-metric question has its
    referent resolved against the prior turn. The classifier MUST
    NOT return clarification_needed when carryover is present.
    """
    carryover = (
        "Recent conversation (prior user questions in this thread, oldest first):\n"
        "  1. which is the label with most Electronic releases?\n"
    )
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="and what is the second one?",
                schema_context=schema,
                carryover_preamble=carryover,
            )
        )
    assert out.complexity != "clarification_needed", (
        f"Follow-up with non-empty carryover should resolve to simple/complex; "
        f"got {out.complexity!r} with rationale {out.rationale!r}"
    )
    assert out.complexity in ("simple", "complex")
    assert out.selected_model is not None


def test_follow_up_without_carryover_still_needs_clarification(schema: dict) -> None:
    """Regression guard for first-turn behavior.

    The same anaphoric follow-up question, sent as the first message
    in a thread (carryover_preamble=None), MUST still return
    clarification_needed — the question is genuinely ambiguous in
    isolation. 015 narrows clarification_needed's behavior; it does
    NOT disable it.
    """
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="and what is the second one?",
                schema_context=schema,
                carryover_preamble=None,
            )
        )
    assert out.complexity == "clarification_needed", (
        f"Follow-up with EMPTY carryover should still need clarification; "
        f"got {out.complexity!r}"
    )


def test_isolation_ambiguous_with_carryover_still_needs_clarification(
    schema: dict,
) -> None:
    """Regression guard for the canonical isolation-ambiguous case.

    The classic "best labels" / "most important genres" examples are
    missing a METRIC, not a referent. Even with rich carryover
    establishing prior context, they MUST still return
    clarification_needed. 015's prompt instructions explicitly
    preserve this case.
    """
    rich_carryover = (
        "Recent conversation (prior user questions in this thread, oldest first):\n"
        "  1. Show releases by decade.\n"
        "  2. Distribution of primary formats.\n"
    )
    with use_node("router"):
        out = query_classifier(
            ClassifierInput(
                user_query="What are the best labels?",
                schema_context=schema,
                carryover_preamble=rich_carryover,
            )
        )
    assert out.complexity == "clarification_needed", (
        f"'best labels' is isolation-ambiguous independently of carryover; "
        f"got {out.complexity!r} with carryover present"
    )
