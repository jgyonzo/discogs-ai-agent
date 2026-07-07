"""Photo -> ScanEvidence extraction (022 T015, research R2).

One vision call through the injected LLM client (the cli.py
_build_llm_client seam, so 021 LangSmith tracing wraps it when
configured). The reply is JSON-parsed and validated into ScanEvidence;
an unparseable reply gets exactly one retry, then a typed error the API
layer maps to 502 vision_unavailable. A valid-but-empty reply is a legal
empty ScanEvidence (routes to the honest no-match path, never an error).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from pydantic import ValidationError

from collection_agent.scan.models import ScanEvidence
from collection_agent.settings import Settings

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "scan_vision.md"

MAX_ATTEMPTS = 2  # one retry on an unparseable reply


class VisionExtractionError(Exception):
    """The vision call failed or never produced parseable evidence."""


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def extract_evidence(
    llm, settings: Settings, image_bytes: bytes, mime: str
) -> ScanEvidence:
    data_url = (
        f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _load_prompt()},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]

    last_error: Exception | None = None
    for _attempt in range(MAX_ATTEMPTS):
        try:
            response = llm.chat.completions.create(
                model=settings.collection_agent_vision_model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # provider/network failure — no retry here,
            # the SDK already retries transport errors internally
            raise VisionExtractionError(
                f"vision model call failed: {exc}"
            ) from exc

        content = response.choices[0].message.content or ""
        try:
            return ScanEvidence.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            continue

    raise VisionExtractionError(
        f"vision model reply was not valid evidence JSON after "
        f"{MAX_ATTEMPTS} attempts: {last_error}"
    )
