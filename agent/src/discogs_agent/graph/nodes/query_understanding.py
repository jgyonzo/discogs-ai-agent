"""Node: query_understanding.

Builds the analytical plan via the chosen LLM tier. Carry-over
(US4) reads the last few user-query texts from this thread and
injects them into the prompt.

015-classifier-carryover: carry-over is now loaded by the router
node BEFORE the classifier runs (so short follow-up questions
can be resolved against prior turns instead of being rejected as
clarification_needed). This node reads the preamble from state
rather than calling the DB-fetch helper itself. See
`specs/015-classifier-carryover/contracts/carryover-as-router-input.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from discogs_agent.config import settings
from discogs_agent.graph.state import AgentState
from discogs_agent.llm.client import get_chat_client
from discogs_agent.llm.parse import parse_json_response
from discogs_agent.observability import logging as obslog
from discogs_agent.observability.tracing import now_ms, use_node
from discogs_agent.tools.cost_logger import CostInput, cost_logger

logger = obslog.get_logger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "query_understanding.md"


def query_understanding_node(state: AgentState) -> AgentState:
    schema_context = state["schema_context"]
    route = state.get("route") or {}
    selected_model = route.get("selected_model") or settings.CHEAP_MODEL

    # 015-classifier-carryover: read carryover from state. The
    # router node populates these fields BEFORE invoking the
    # classifier, so by the time this node runs the values are
    # guaranteed-set (or (None, 0) on first turn).
    carryover_preamble = state.get("carryover_preamble")

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
    return state
