"""Vision evidence extraction (022 T016): stubbed LLM only — happy path,
invalid-JSON retry then typed error, empty evidence, data-URL encoding,
model name sourced from settings."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from collection_agent.scan.vision import (
    MAX_ATTEMPTS,
    VisionExtractionError,
    extract_evidence,
)


class StubVisionLLM:
    """OpenAI-shaped stub replaying scripted reply contents (str) or
    exceptions. Records every request for assertions."""

    def __init__(self, script):
        self._script = list(script)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        msg = SimpleNamespace(content=item, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


IMAGE = b"\xff\xd8\xff\xe0 fake jpeg bytes"


def test_happy_extraction(settings):
    llm = StubVisionLLM([
        json.dumps({
            "artist": "Alex Smoke", "title": "Simple Things",
            "catno": "SOMA-1", "barcode": "5 060100 660017",
            "format_hints": ["2xLP"],
        })
    ])
    ev = extract_evidence(llm, settings, IMAGE, "image/jpeg")
    assert ev.artist == "Alex Smoke"
    assert ev.barcode == "5060100660017"  # normalized digits
    assert ev.format_hints == ["2xLP"]
    assert not ev.is_empty


def test_empty_object_is_legal_empty_evidence(settings):
    ev = extract_evidence(StubVisionLLM(["{}"]), settings, IMAGE, "image/jpeg")
    assert ev.is_empty
    assert ev.evidence_kinds == []


def test_invalid_json_retries_once_then_succeeds(settings):
    llm = StubVisionLLM(["not json at all", json.dumps({"artist": "A", "title": "T"})])
    ev = extract_evidence(llm, settings, IMAGE, "image/jpeg")
    assert ev.artist == "A"
    assert len(llm.requests) == 2


def test_unparseable_after_retry_raises_typed_error(settings):
    llm = StubVisionLLM(["nope"] * MAX_ATTEMPTS)
    with pytest.raises(VisionExtractionError):
        extract_evidence(llm, settings, IMAGE, "image/jpeg")
    assert len(llm.requests) == MAX_ATTEMPTS


def test_provider_failure_raises_typed_error(settings):
    llm = StubVisionLLM([RuntimeError("boom")])
    with pytest.raises(VisionExtractionError):
        extract_evidence(llm, settings, IMAGE, "image/jpeg")


def test_image_sent_as_data_url_and_model_from_settings(settings):
    llm = StubVisionLLM(["{}"])
    extract_evidence(llm, settings, IMAGE, "image/png")
    req = llm.requests[0]
    assert req["model"] == settings.collection_agent_vision_model
    assert req["response_format"] == {"type": "json_object"}
    image_part = req["messages"][0]["content"][1]
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == IMAGE


def test_vision_call_carries_settings_timeout(settings):
    """FR-023 (addendum 2): per-request hard cap from settings (VII(a))."""
    llm = StubVisionLLM(["{}"])
    extract_evidence(llm, settings, IMAGE, "image/jpeg")
    assert llm.requests[0]["timeout"] == settings.scan_vision_timeout_s
    assert settings.scan_vision_timeout_s == 45.0  # default
