"""Node: query_understanding.

Builds the analytical plan via the chosen LLM tier. Carry-over
(US4) reads the last few user-query texts from this thread and
injects them into the prompt — only into this node, by design
(R-04). Routing and code generation stay stateless beyond the
plan.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from discogs_agent.config import settings
from discogs_agent.graph.nodes._carryover import (
    PriorTurn,
    build_carryover_preamble,
)
from discogs_agent.graph.state import AgentState
from discogs_agent.llm.client import get_chat_client
from discogs_agent.llm.parse import parse_json_response
from discogs_agent.observability import logging as obslog
from discogs_agent.observability.tracing import now_ms, use_node
from discogs_agent.persistence.db import current_session
from discogs_agent.persistence.repositories import RunRepo
from discogs_agent.tools.cost_logger import CostInput, cost_logger

logger = obslog.get_logger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "query_understanding.md"

_CARRYOVER_STATUSES = ("succeeded", "failed_clarification_needed")


def _load_carryover(state: AgentState) -> tuple[str | None, int]:
    """Pull prior runs for this thread and build the preamble.

    Reads from the request-scoped session set by the API. If no
    session is bound (e.g., a unit test invoking the node in
    isolation), returns ``(None, 0)`` — carry-over is a soft
    enrichment, never load-bearing.
    """
    session = current_session()
    if session is None:
        return (None, 0)
    try:
        thread_uuid = UUID(state["thread_id"])
    except (KeyError, ValueError):
        return (None, 0)

    rows = RunRepo(session).fetch_recent_for_thread(
        thread_id=thread_uuid,
        limit=int(settings.THREAD_CARRYOVER_TURNS),
        statuses=_CARRYOVER_STATUSES,
    )
    # Drop the current run if it's already been row-created — the
    # current user_query is already in the user message, no point
    # echoing it.
    current_run_id = state.get("run_id")
    if current_run_id:
        rows = [r for r in rows if str(r.run_id) != current_run_id]
    if not rows:
        return (None, 0)

    prior_turns = [PriorTurn(user_query=r.user_query) for r in rows]
    return build_carryover_preamble(
        prior_turns,
        token_budget=int(settings.THREAD_CARRYOVER_TOKEN_BUDGET),
    )


def query_understanding_node(state: AgentState) -> AgentState:
    schema_context = state["schema_context"]
    route = state.get("route") or {}
    selected_model = route.get("selected_model") or settings.CHEAP_MODEL

    carryover_preamble, turn_count = _load_carryover(state)

    template = PROMPT_PATH.read_text(encoding="utf-8")
    system_body = template.format(
        schema_context_block=schema_context.get("rendered_block") or "",
        carryover_block=(carryover_preamble or ""),
        user_query="(see user message below)",
    )
    messages = [
        {"role": "system", "content": system_body},
        {"role": "user", "content": state["user_query"]},
    ]

    with use_node("query_understanding"):
        client = get_chat_client(selected_model)
        start = now_ms()
        response = client.invoke(messages)
        latency = int(now_ms() - start)

        cost_logger(
            CostInput(
                node_name="query_understanding",
                model_name=selected_model,
                prompt_tokens=int(response.usage.get("prompt_tokens", 0)),
                completion_tokens=int(response.usage.get("completion_tokens", 0)),
                latency_ms=latency,
            )
        )

    try:
        plan = parse_json_response(response.content)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("query_plan_parse_failed", error=str(exc))
        plan = {"_parse_error": str(exc), "raw": response.content}

    state["query_plan"] = plan
    state["carryover_preamble"] = carryover_preamble
    state["carryover_turn_count"] = turn_count
    return state
