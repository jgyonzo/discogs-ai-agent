"""Sanitize Python values for JSONB persistence.

Pinned by `specs/004-agent-v1/contracts/postgres-schema.md §7`,
amended by `specs/010-jsonb-nan-sanitization/`.

Postgres `JSONB` columns enforce RFC-8259, which forbids `NaN`,
`Infinity`, and `-Infinity`. Python's `json.dumps` is `allow_nan=True`
by default and emits these tokens; psycopg's default JSON adapter
uses `json.dumps`. Pandas dataframes routinely produce `float('nan')`
for NULL cells; Pydantic `model_dump()` preserves them. So every
dict written to a JSONB column must be sanitized at the boundary.

This module is the sanitizer. It is applied at exactly one chokepoint:
the `_SanitizedJSON` `TypeDecorator` in `models.py`. Per-call-site
sanitization in `Repo.create()` methods is forbidden as the primary
enforcement mechanism (would turn the invariant into discipline).
"""

from __future__ import annotations

import math
from typing import Any


def sanitize_for_jsonb(value: Any) -> Any:
    """Replace NaN/Infinity floats with None recursively.

    Returns a new value; does NOT mutate the input. Idempotent on
    clean inputs. Recurses through `dict`, `list`, and `tuple`
    (tuples become lists, matching `json.dumps`'s default behavior).
    Sets, bytes, and other non-JSON-native types fall through
    unchanged — downstream serialization will reject them, surfacing
    rather than hiding unexpected types.

    Cost: O(n) where n is the number of leaf values. Negligible for
    the dict sizes typical at the persistence boundary (tens of KB).
    """
    if isinstance(value, bool):
        # `bool` is a subclass of `int` but distinct from float;
        # the explicit guard documents the intent.
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: sanitize_for_jsonb(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_jsonb(item) for item in value]
    return value
