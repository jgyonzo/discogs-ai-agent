"""Node: router.

Calls the query_classifier tool, then logs the cost via cost_logger.

015-classifier-carryover: the router now builds the multi-turn
carryover preamble BEFORE invoking the classifier, so short
follow-up questions ("and the next one?", "and the top 5?") can
be resolved against prior turns instead of being rejected as
clarification_needed. The preamble is also written into
AgentState so downstream nodes (query_understanding) can read it
without a second DB fetch, AND so the post-graph metadata write
captures it even on clarification_needed short-circuits. See
`specs/015-classifier-carryover/contracts/carryover-as-router-input.md`.
"""

from __future__ import annotations

from discogs_agent.config import settings
from discogs_agent.graph.nodes._carryover import load_carryover_for_state
from discogs_agent.graph.state import AgentState
from discogs_agent.observability.tracing import now_ms, use_node
from discogs_agent.tools.cost_logger import CostInput, cost_logger
from discogs_agent.tools.query_classifier import ClassifierInput, query_classifier


def router_node(state: AgentState) -> AgentState:
    # 015: load carryover BEFORE the classifier so it can see prior
    # turns when resolving short follow-ups. State is populated
    # here so downstream nodes (query_understanding) read from
    # state rather than fetching again, AND so the post-graph
    # metadata write at api_query.py:240-245 captures the preamble
    # even on `failed_clarification_needed` short-circuits (US2
    # side-effect).
    carryover_preamble, turn_count = load_carryover_for_state(state)
    state["carryover_preamble"] = carryover_preamble
    state["carryover_turn_count"] = turn_count

    with use_node("router"):
        start = now_ms()
        result = query_classifier(
            ClassifierInput(
                user_query=state["user_query"],
                schema_context=state["schema_context"],
                carryover_preamble=carryover_preamble,
            )
        )
        latency = int(now_ms() - start)
        cost_logger(
            CostInput(
                node_name="router",
                model_name=settings.CHEAP_MODEL,
                prompt_tokens=0,  # actual usage flows in via the model_usage trace
                completion_tokens=0,
                latency_ms=latency,
            )
        )

    state["route"] = result.model_dump()
    return state


def router_edge(state: AgentState) -> str:
    """Returns the next node name. Either query_understanding or
    response_synthesizer (terminal for unsupported / clarification)."""
    route = state.get("route") or {}
    complexity = route.get("complexity")
    if complexity in ("unsupported", "clarification_needed"):
        return "response_synthesizer"
    return "query_understanding"
