"""US2 browse tool: filter_records (contracts/agent-tools.md §1; FR-011/012/013).

Registry-driven: any registered attribute is filterable with its kind's ops;
criteria AND-combine. Unsupported attributes/ops are returned in
`unsupported_criteria` with the supported list — never silently dropped
(FR-013a). Empty results are explicit (FR-013b). Listings are capped
(settings FILTER_RESULT_LIMIT) with `truncated` disclosed, and the matched
instance ids are parked on the session for follow-ups ("their links",
"move those").
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from collection_agent.agent import AgentSession, ToolDef
from collection_agent.models import CollectionRecord, Snapshot
from collection_agent.registry import (
    AttributeRegistry,
    UnsupportedOp,
    build_registry,
    matches,
)
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.tools.common import (
    load_for_serving,
    release_page_url,
    with_warnings,
)


class FilterCriterion(BaseModel):
    attribute: str = Field(description="Attribute name or alias (es/en), e.g. genre, década, label, country.")
    op: str = Field(
        default="eq",
        description="Operator — categorical: eq,in · numeric: eq,lt,lte,gt,gte,between,missing · "
        "text: contains,eq (text attributes like title default to contains when omitted)",
    )
    value: Any = Field(default=None, description="Comparison value ('between' takes [lo, hi]; 'missing' takes none).")


class FilterArgs(BaseModel):
    criteria: list[FilterCriterion] = Field(
        description="Criteria to AND together, e.g. genre=House AND decade=1990s."
    )
    limit: int | None = Field(default=None, ge=1, le=200, description="Max records to list (default from settings).")


def _folder_names(snapshot: Snapshot) -> dict[int, str]:
    return {f.folder_id: f.name for f in snapshot.folders}


def _display(
    rec: CollectionRecord, folder_names: dict[int, str], settings: Settings
) -> dict[str, Any]:
    return {
        "instance_id": rec.instance_id,
        "artist": ", ".join(rec.artists) or "?",
        "title": rec.title,
        "year": rec.year,
        "format": ", ".join(rec.formats[:3]),
        "folder": folder_names.get(rec.folder_id, str(rec.folder_id)),
        "release_url": release_page_url(settings, rec),
    }


def make_browse_tools(
    settings: Settings,
    store: SnapshotStore,
    registry: AttributeRegistry | None = None,
) -> list[ToolDef]:
    registry = registry or build_registry(settings)

    def filter_records(session: AgentSession, args: FilterArgs) -> dict[str, Any]:
        ctx = load_for_serving(store)
        if ctx.blocked:
            return ctx.blocked

        applied: list[dict[str, Any]] = []
        unsupported: list[dict[str, Any]] = []
        resolved: list[tuple[Any, str, Any]] = []
        for crit in args.criteria:
            spec = registry.resolve(crit.attribute)
            if spec is None:
                unsupported.append(
                    {"attribute": crit.attribute, "reason": "unknown attribute",
                     "supported": registry.supported_names()}
                )
                continue
            # FR-010 (018): the LLM often omits op; for text attributes the
            # schema-wide eq default would recreate the false-absence failure.
            op = crit.op
            if spec.kind == "text" and "op" not in crit.model_fields_set:
                op = "contains"
            if op not in spec.ops:
                unsupported.append(
                    {"attribute": spec.name, "reason": f"op {op!r} not valid "
                     f"for {spec.kind}; valid ops: {list(spec.ops)}"}
                )
                continue
            resolved.append((spec, op, crit.value))
            applied.append({"attribute": spec.name, "op": op, "value": crit.value})

        if not resolved:
            return with_warnings(ctx, {
                "criteria_applied": [],
                "unsupported_criteria": unsupported,
                "matches": [],
                "count": 0,
                "truncated": False,
                "note": "no evaluable criteria — tell the user which parts were "
                "not applicable and what attributes exist" if unsupported else
                "no criteria given",
            })

        matched: list[CollectionRecord] = []
        for rec in ctx.snapshot.records:
            try:
                if all(matches(spec, rec, op, value) for spec, op, value in resolved):
                    matched.append(rec)
            except UnsupportedOp as exc:
                return with_warnings(ctx, {
                    "criteria_applied": applied,
                    "unsupported_criteria": unsupported + [{"reason": str(exc)}],
                    "matches": [], "count": 0, "truncated": False,
                })

        limit = args.limit or settings.filter_result_limit
        folder_names = _folder_names(ctx.snapshot)
        shown = matched[:limit]
        session.last_listing_instance_ids = [r.instance_id for r in shown]

        payload: dict[str, Any] = {
            "criteria_applied": applied,
            "unsupported_criteria": unsupported,
            "count": len(matched),
            "matches": [_display(r, folder_names, settings) for r in shown],
            "truncated": len(matched) > limit,
        }
        if len(matched) > limit:
            payload["truncation_note"] = f"showing {limit} of {len(matched)} matches"
        if not matched:
            # FR-009/FR-011 (018): at the zero-match decision point the LLM
            # follows this note over the standing prompt — with a text
            # criterion it must point toward the near-misses, not "not found".
            has_text = any(spec.kind == "text" for spec, _, _ in resolved)
            non_text = [(s, o, v) for s, o, v in resolved if s.kind != "text"]
            if has_text and non_text:
                fallback = [
                    rec for rec in ctx.snapshot.records
                    if all(matches(spec, rec, op, value) for spec, op, value in non_text)
                ]
                shown_fb = fallback[:limit]
                payload["fallback_matches"] = [
                    _display(r, folder_names, settings) for r in shown_fb
                ]
                payload["fallback_count"] = len(fallback)
                session.last_listing_instance_ids = [r.instance_id for r in shown_fb]
                payload["note"] = (
                    "no records matched the text criterion — fallback_matches "
                    "lists the records matching the remaining criteria; inspect "
                    "them for a near-miss title (typo, extra suffix, accents) "
                    "and affirm it if it clearly is the requested record; only "
                    "report absence if none fits; do not invent results"
                )
            elif has_text:
                payload["note"] = (
                    "no records matched — before telling the user a record is "
                    "absent, loosen the search: drop the text criterion (e.g. "
                    "title) or retry with a shorter distinctive substring; "
                    "do not invent results"
                )
            else:
                payload["note"] = (
                    "no records matched — say so explicitly; do not invent results"
                )
        return with_warnings(ctx, payload)

    return [
        ToolDef(
            name="filter_records",
            description="List the records matching AND-combined attribute criteria "
            "(genre, decade, label, country, artist, format, rating, scarcity, …). "
            "Returns identity (artist/title/year), count, truncation, and names any "
            "criteria it could not apply. Sets the session's 'last listing' for "
            "follow-ups.",
            params_model=FilterArgs,
            fn=filter_records,
        )
    ]
