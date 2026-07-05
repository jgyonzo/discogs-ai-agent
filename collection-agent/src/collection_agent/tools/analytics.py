"""US1 analytics tools: aggregate_by, top_n, collection_value.

Deterministic aggregations over the snapshot (FR-004..FR-010). Counting unit
is the INSTANCE — every owned copy counts (FR-025) — so single-valued
distributions reconcile exactly with the collection size (SC-002).
Multi-valued attributes count per-record-per-value; the result says so
(FR-004). Missing values land in an explicit unknown bucket (FR-007).
Every ranking states its basis and how many records were excluded for
missing data (FR-006/008/010; system prompt relays it).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from collection_agent.agent import AgentSession, ToolDef
from collection_agent.models import CollectionRecord
from collection_agent.registry import AttributeRegistry, build_registry
from collection_agent.settings import Settings
from collection_agent.snapshot.store import SnapshotStore
from collection_agent.tools.common import load_for_serving, with_warnings


class AggregateArgs(BaseModel):
    attribute: str = Field(
        description="Attribute to aggregate by (canonical name or alias, es/en) — e.g. genre, label, country, decade."
    )


class TopNArgs(BaseModel):
    basis: Literal["community_rating", "most_expensive", "rarest"] = Field(
        description="Ranking basis: community_rating (top rated), most_expensive (price of cheapest listed copy), rarest (scarcity signals)."
    )
    n: int = Field(default=10, ge=1, le=50, description="How many records to return.")


class _NoArgs(BaseModel):
    pass


def _display(rec: CollectionRecord) -> dict[str, Any]:
    return {
        "instance_id": rec.instance_id,
        "artist": ", ".join(rec.artists) or "?",
        "title": rec.title,
        "year": rec.year,
    }


def make_analytics_tools(settings: Settings, store: SnapshotStore) -> list[ToolDef]:
    registry = build_registry(settings)

    # -- aggregate_by ----------------------------------------------------------

    def aggregate_by(_s: AgentSession, args: AggregateArgs) -> dict[str, Any]:
        ctx = load_for_serving(store)
        if ctx.blocked:
            return ctx.blocked
        spec = registry.resolve(args.attribute)
        if spec is None:
            return {
                "error": "unsupported_attribute",
                "attribute": args.attribute,
                "supported": registry.supported_names(),
            }

        records = ctx.snapshot.records
        total = len(records)
        counts: Counter[str] = Counter()
        unknown = 0
        for rec in records:
            value = spec.extract(rec)
            if value is None or value == []:
                unknown += 1
                continue
            values = value if isinstance(value, list) else [value]
            for v in values:
                counts[str(v)] += 1

        buckets = [
            {"value": v, "count": c, "pct": round(c / total * 100, 1)}
            for v, c in counts.most_common()
        ]
        note = (
            f"'{spec.name}' is multi-valued: records are counted once per value, "
            f"so bucket counts can sum to more than the {total} records; "
            "percentages are of records."
            if spec.multi
            else f"single-valued: bucket counts (plus the unknown bucket) sum to exactly {total} records."
        )
        return with_warnings(
            ctx,
            {
                "attribute": spec.name,
                "unit": "instances (every owned copy counts, duplicates included)",
                "total_records": total,
                "buckets": buckets,
                "unknown_bucket": {"label": spec.unknown_label, "count": unknown,
                                   "pct": round(unknown / total * 100, 1)},
                "counting_note": note,
            },
        )

    # -- top_n -------------------------------------------------------------------

    def top_n(_s: AgentSession, args: TopNArgs) -> dict[str, Any]:
        ctx = load_for_serving(store)
        if ctx.blocked:
            return ctx.blocked
        records = ctx.snapshot.records

        if args.basis == "community_rating":
            eligible = [r for r in records if r.community_rating_avg is not None]
            eligible.sort(
                key=lambda r: (r.community_rating_avg, r.community_rating_count or 0),
                reverse=True,
            )
            items = [
                {
                    **_display(r),
                    "community_rating_avg": r.community_rating_avg,
                    "votes": r.community_rating_count,
                }
                for r in eligible[: args.n]
            ]
            basis = (
                "Discogs community average rating (0–5); vote count shown — a "
                "high average on very few votes is weak evidence"
            )

        elif args.basis == "most_expensive":
            eligible = [r for r in records if r.lowest_price is not None]
            eligible.sort(key=lambda r: r.lowest_price, reverse=True)
            no_copies = sum(1 for r in records if r.num_for_sale == 0)
            items = [
                {
                    **_display(r),
                    "lowest_price": r.lowest_price,
                    "num_for_sale": r.num_for_sale,
                }
                for r in eligible[: args.n]
            ]
            basis = (
                "price of the cheapest copy currently listed on Discogs (owner "
                "currency) — an availability signal, not an appraisal; records "
                f"with no copies for sale ({no_copies}) have no price signal"
            )

        else:  # rarest
            scarcity = registry.resolve("scarcity")
            rank = {"very rare": 0, "rare": 1}
            eligible = []
            for r in records:
                bucket = scarcity.extract(r)
                if bucket in rank:
                    ratio = (
                        round(r.community_want / max(r.community_have, 1), 2)
                        if r.community_have is not None and r.community_want is not None
                        else None
                    )
                    eligible.append((rank[bucket], -(ratio or 0), r, bucket, ratio))
            eligible.sort(key=lambda t: (t[0], t[1]))
            items = [
                {
                    **_display(r),
                    "scarcity": bucket,
                    "have": r.community_have,
                    "want": r.community_want,
                    "want_have_ratio": ratio,
                    "num_for_sale": r.num_for_sale,
                }
                for _, _, r, bucket, ratio in eligible[: args.n]
            ]
            basis = (
                f"scarcity signals: ≤{settings.rarity_max_for_sale} copies for sale, "
                f"or want/have ≥ {settings.rarity_want_have_ratio} (with have ≥ "
                f"{settings.rarity_min_have} to avoid small-sample noise); both → 'very rare'"
            )

        excluded = len(records) - len(eligible)
        return with_warnings(
            ctx,
            {
                "basis": basis,
                "requested_n": args.n,
                "items": items,
                "excluded_missing_data": excluded,
                "excluded_note": (
                    f"{excluded} record(s) lacked the data for this ranking and "
                    "were excluded — they are NOT necessarily low-ranked"
                    if excluded
                    else None
                ),
            },
        )

    # -- collection_value ----------------------------------------------------------

    def collection_value(_s: AgentSession, _a: _NoArgs) -> dict[str, Any]:
        ctx = load_for_serving(store)
        if ctx.blocked:
            return ctx.blocked
        v = ctx.snapshot.meta.collection_value
        return with_warnings(
            ctx,
            {
                "basis": "Discogs' own collection-value estimate (as of last sync) — "
                "an estimate range, never an exact appraisal",
                "minimum": v.minimum,
                "median": v.median,
                "maximum": v.maximum,
                "as_of": ctx.snapshot.meta.synced_at,
            },
        )

    return [
        ToolDef(
            name="aggregate_by",
            description="Distribution of the collection by any supported attribute "
            "(genre, label, country, decade, format, …): counts + percentages with "
            "an explicit unknown bucket. Counting unit: instances.",
            params_model=AggregateArgs,
            fn=aggregate_by,
        ),
        ToolDef(
            name="top_n",
            description="Ranked records: top rated (community average + votes), "
            "most expensive (cheapest listed copy), or rarest (scarcity signals). "
            "Always returns the ranking basis to state in the answer.",
            params_model=TopNArgs,
            fn=top_n,
        ),
        ToolDef(
            name="collection_value",
            description="Discogs' estimated value of the whole collection "
            "(minimum / median / maximum, with currency).",
            params_model=_NoArgs,
            fn=collection_value,
        ),
    ]
