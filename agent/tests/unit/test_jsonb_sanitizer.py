"""Unit tests for `sanitize_for_jsonb`.

Pinned by `specs/010-jsonb-nan-sanitization/`. Locks in the contract
described in `004/contracts/postgres-schema.md §7.4`:

- top-level NaN replaced with None;
- nested NaN (dict-in-dict) replaced;
- NaN inside a list replaced;
- positive AND negative Infinity replaced;
- idempotent on clean input;
- does not mutate input.
"""

from __future__ import annotations

import copy
import math

import pytest
from pydantic import BaseModel

from discogs_agent.persistence.sanitize import sanitize_for_jsonb


def test_top_level_nan_replaced_with_none() -> None:
    out = sanitize_for_jsonb({"x": float("nan")})
    assert out == {"x": None}


def test_nested_dict_nan_replaced() -> None:
    out = sanitize_for_jsonb({"outer": {"inner": {"deep": float("nan"), "fine": 1.5}}})
    assert out == {"outer": {"inner": {"deep": None, "fine": 1.5}}}


def test_nan_inside_list_replaced() -> None:
    out = sanitize_for_jsonb(
        {"rows": [{"country": "US", "n": 100}, {"country": float("nan"), "n": 50}]}
    )
    assert out == {
        "rows": [
            {"country": "US", "n": 100},
            {"country": None, "n": 50},
        ]
    }


def test_positive_and_negative_infinity_replaced() -> None:
    out = sanitize_for_jsonb({"a": float("inf"), "b": float("-inf"), "c": 0.0})
    assert out == {"a": None, "b": None, "c": 0.0}


def test_idempotent_on_clean_input() -> None:
    clean = {"x": 1, "y": "two", "z": [{"a": 3.14}], "w": None, "b": True}
    once = sanitize_for_jsonb(clean)
    twice = sanitize_for_jsonb(once)
    assert once == twice == clean


def test_idempotent_on_dirty_input() -> None:
    dirty = {"x": float("nan"), "y": [float("inf"), 1.0]}
    once = sanitize_for_jsonb(dirty)
    twice = sanitize_for_jsonb(once)
    assert once == twice == {"x": None, "y": [None, 1.0]}


def test_does_not_mutate_input() -> None:
    original = {"rows": [{"country": float("nan"), "n": 50}]}
    snapshot = copy.deepcopy(original)
    sanitize_for_jsonb(original)
    # Compare with NaN-aware equality: the original's nan must still be a nan.
    assert isinstance(original["rows"][0]["country"], float)
    assert math.isnan(original["rows"][0]["country"])
    # The non-NaN parts must be equal to the snapshot.
    assert original["rows"][0]["n"] == snapshot["rows"][0]["n"]


def test_preserves_clean_values() -> None:
    # Regular floats, ints, strings, booleans, None, empty containers.
    clean = {
        "int": 42,
        "float": 3.14,
        "negative_float": -2.5,
        "zero_float": 0.0,
        "string": "hello",
        "true": True,
        "false": False,
        "none": None,
        "empty_dict": {},
        "empty_list": [],
        "deep": [{"a": [{"b": 1}]}],
    }
    out = sanitize_for_jsonb(clean)
    assert out == clean


def test_tuples_become_lists() -> None:
    out = sanitize_for_jsonb({"t": (1, 2, float("nan"))})
    assert out == {"t": [1, 2, None]}


def test_handles_pydantic_model_dump_output() -> None:
    """Locks in the actual upstream data shape.

    Pydantic's `model_dump()` preserves NaN floats; the sanitizer must
    handle the dict shape Pydantic produces.
    """

    class ToolOutput(BaseModel):
        country: float | None
        releases: int

    model = ToolOutput(country=float("nan"), releases=100)
    dumped = model.model_dump()
    # Confirm the upstream shape: Pydantic preserves NaN.
    assert isinstance(dumped["country"], float)
    assert math.isnan(dumped["country"])

    # The sanitizer cleans it.
    sanitized = sanitize_for_jsonb(dumped)
    assert sanitized == {"country": None, "releases": 100}


def test_returns_new_container_objects() -> None:
    """Even on clean input, the sanitizer must construct new dicts/lists
    rather than aliasing — required to satisfy FR-005 strictly.
    """
    inner = [1, 2, 3]
    outer = {"x": inner}
    out = sanitize_for_jsonb(outer)
    assert out == outer
    assert out is not outer
    assert out["x"] is not inner


def test_passes_through_unsupported_types_unchanged() -> None:
    """Non-JSON-native types fall through; downstream serialization
    will reject them. This surfaces unexpected types rather than
    silently corrupting them.
    """

    class Custom:
        pass

    instance = Custom()
    out = sanitize_for_jsonb({"x": instance})
    assert out["x"] is instance


@pytest.mark.parametrize(
    "value,expected",
    [
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (1.0, 1.0),
        (-0.0, -0.0),
        (1e300, 1e300),  # very large finite — not Infinity, not touched
    ],
)
def test_scalar_floats(value: float, expected: float | None) -> None:
    assert sanitize_for_jsonb(value) == expected
