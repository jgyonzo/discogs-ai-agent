"""OpenAI tool-calling loop over deterministic tools (research R2).

Plain SDK — no LangGraph, no codegen, no sandbox. The LLM routes natural
language to registered tools; tools compute answers from the snapshot (or,
for `propose_moves`, build a WritePlan). The LLM narrates results.

Write-path guard (contracts/agent-tools.md §4): `execute_plan` is NOT a
registered tool. The only thing the model can do is `propose_moves`, which
parks a WritePlan on the session; the CLI runtime renders it and prompts
y/N itself. Unconfirmed writes are unreachable by construction.

The system prompt's attribute documentation is rendered from the attribute
registry at startup ({attribute_block}) — never hand-written (VII(b) analog).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from collection_agent.models import WritePlan
from collection_agent.registry import AttributeRegistry, render_attribute_block

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
MAX_TOOL_ROUNDS = 8


@dataclass
class AgentSession:
    """Per-conversation state (dies with the REPL; never persisted)."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    last_listing_instance_ids: list[int] = field(default_factory=list)
    pending_plan: WritePlan | None = None

    def expire_pending_plan(self) -> None:
        if self.pending_plan is not None:
            from collection_agent.models import PlanState

            self.pending_plan.state = PlanState.EXPIRED
            self.pending_plan = None


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    params_model: type[BaseModel]
    fn: Callable[[AgentSession, BaseModel], dict[str, Any]]

    def openai_schema(self) -> dict[str, Any]:
        schema = self.params_model.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }


def render_system_prompt(registry: AttributeRegistry) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{attribute_block}", render_attribute_block(registry))


class Agent:
    """Tool-calling loop. `llm_client` is an OpenAI-compatible client
    (injectable — tests pass a stub with the same .chat.completions.create)."""

    def __init__(
        self,
        registry: AttributeRegistry,
        model: str,
        llm_client: Any,
        session: AgentSession | None = None,
    ):
        self.registry = registry
        self.model = model
        self.llm = llm_client
        self.session = session or AgentSession()
        self._tools: dict[str, ToolDef] = {}
        self.session.messages.append(
            {"role": "system", "content": render_system_prompt(registry)}
        )

    # -- tool registration ----------------------------------------------------

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    # -- conversation ----------------------------------------------------------

    def run_turn(self, user_text: str) -> str:
        """One user turn: may involve several tool rounds; returns final text."""
        self.session.messages.append({"role": "user", "content": user_text})
        tool_schemas = [t.openai_schema() for t in self._tools.values()]

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.llm.chat.completions.create(
                model=self.model,
                messages=self.session.messages,
                tools=tool_schemas or None,
            )
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                text = msg.content or ""
                self.session.messages.append({"role": "assistant", "content": text})
                return text

            self.session.messages.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                result = self._dispatch(tc.function.name, tc.function.arguments)
                self.session.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # safety valve: too many rounds
        text = "I could not complete that request within the tool budget — please rephrase."
        self.session.messages.append({"role": "assistant", "content": text})
        return text

    # -- dispatch ---------------------------------------------------------------

    def _dispatch(self, name: str, raw_arguments: str) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"unknown tool {name!r}; available: {self.tool_names()}"}
        try:
            payload = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError as exc:
            return {"error": f"invalid JSON arguments: {exc}"}
        try:
            args = tool.params_model.model_validate(payload)
        except ValidationError as exc:
            return {"error": f"invalid arguments: {exc.errors()}"}
        try:
            return tool.fn(self.session, args)
        except Exception as exc:  # tool bug: surface, don't crash the REPL
            return {"error": f"tool {name} failed: {exc}"}
