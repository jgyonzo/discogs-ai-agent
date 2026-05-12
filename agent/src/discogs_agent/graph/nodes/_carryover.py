"""Build the multi-turn carry-over preamble (US4 / R-04).

Given the most recent N runs of a thread (chronological, oldest
first), produce a "Recent conversation" preamble that fits inside
the configured token budget. Trim from the oldest end until the
preamble's tiktoken count is within budget.

Carries only the prior `user_query` text — never SQL, generated
code, or final responses. The "no SQL/code carry-over" boundary
is what the spec calls "light contextual carry-over."

015-classifier-carryover: `load_carryover_for_state` is the
public DB-fetching entry point used by both `router_node` (so the
classifier sees prior context when resolving short follow-ups)
and `query_understanding_node` (post-015, query_understanding
reads from state rather than calling the helper itself). See
`specs/015-classifier-carryover/contracts/carryover-as-router-input.md`
for the cross-node contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import tiktoken

from discogs_agent.config import settings
from discogs_agent.graph.state import AgentState
from discogs_agent.persistence.db import current_session
from discogs_agent.persistence.repositories import RunRepo

_ENCODING = tiktoken.get_encoding("cl100k_base")

# Statuses whose user_query gets carried forward. Failed-clarification
# runs are included because the user's intent on them was unambiguous
# enough to record (only the classifier's own classification failed);
# other failure modes (safety, validation, internal errors) are
# excluded — their intent wasn't necessarily resolvable.
_CARRYOVER_STATUSES = ("succeeded", "failed_clarification_needed")


@dataclass(frozen=True)
class PriorTurn:
    """Minimal shape of a prior run needed to build the preamble.

    The graph node converts ORM rows to this so the builder can be
    unit-tested without touching the database.
    """

    user_query: str


def _tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def _format_turn(idx: int, turn: PriorTurn) -> str:
    return f"  {idx}. {turn.user_query.strip()}"


def _format_preamble(turns: list[PriorTurn]) -> str:
    body = "\n".join(_format_turn(i + 1, t) for i, t in enumerate(turns))
    return f"Recent conversation (prior user questions in this thread, oldest first):\n{body}\n"


def build_carryover_preamble(
    prior_runs: list[PriorTurn],
    token_budget: int,
) -> tuple[str | None, int]:
    """Return (preamble, turn_count).

    `prior_runs` must be ordered oldest-first. The most recent N
    turns are kept; older turns are dropped until the preamble fits
    `token_budget` tokens (cl100k_base). A budget too small to fit
    even the single most recent turn yields ``(None, 0)`` rather
    than truncating mid-query.
    """
    if not prior_runs or token_budget <= 0:
        return (None, 0)

    # Walk newest → oldest. After each step, `kept` holds the
    # most-recent-N turns we've accepted, in chronological order
    # (oldest-first within the kept set). Stop the first time
    # adding the next-older turn would exceed budget — older turns
    # past that are dropped, not the newer ones already kept.
    kept: list[PriorTurn] = []
    for turn in reversed(prior_runs):
        candidate = [turn] + kept
        if _tokens(_format_preamble(candidate)) <= token_budget:
            kept = candidate
        else:
            break

    if not kept:
        return (None, 0)
    return (_format_preamble(kept), len(kept))


def load_carryover_for_state(state: AgentState) -> tuple[str | None, int]:
    """Pull prior runs for this thread and build the preamble.

    Reads from the request-scoped session set by the API. If no
    session is bound (e.g., a unit test invoking a node in
    isolation), returns ``(None, 0)`` — carry-over is a soft
    enrichment, never load-bearing.

    015-classifier-carryover: this helper was previously a
    private ``_load_carryover`` inside ``query_understanding.py``.
    Promoted to a public function of this module so the router
    node can call it BEFORE the classifier runs, ensuring the
    classifier sees the same multi-turn context the query-
    understanding node already had. See
    ``specs/015-classifier-carryover/contracts/carryover-as-router-input.md``
    for the cross-node contract.
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
