"""Declarative attribute registry (contracts/agent-tools.md §3; FR-013).

Single source of truth for every attribute the agent can aggregate on or
filter by. One `AttributeSpec` entry gives you, automatically:
- `aggregate_by(<name>)` support (tools/analytics.py)
- `filter_records` support with kind-appropriate ops (tools/browse.py)
- a line in the system prompt's dynamically-rendered attribute block
  (Constitution VII(b) analog: never hand-written prose)

Adding a filterable attribute == adding one entry here (+ its unit test).
Anything that requires editing tool code or prompt prose instead violates
the agent-tools contract (SC-003a).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from collection_agent.models import CollectionRecord
from collection_agent.settings import Settings

Kind = Literal["categorical", "numeric", "text"]

# ops offered per kind (rendered into the prompt; enforced by the filter tool)
OPS_BY_KIND: dict[Kind, tuple[str, ...]] = {
    "categorical": ("eq", "in"),
    "numeric": ("eq", "lt", "lte", "gt", "gte", "between", "missing"),
    "text": ("contains", "eq"),
}


@dataclass(frozen=True)
class AttributeSpec:
    name: str
    aliases: tuple[str, ...]  # en + es; matched case/diacritic-insensitively
    kind: Kind
    extract: Callable[[CollectionRecord], Any]  # value | list | None
    multi: bool = False  # multi-valued per record (genre, label, format…)
    unknown_label: str = "unknown"
    description: str = ""  # one-liner for the prompt's attribute block
    normalize_value: Callable[[str], str] | None = None  # user value → canonical

    @property
    def ops(self) -> tuple[str, ...]:
        return OPS_BY_KIND[self.kind]


def fold(s: str) -> str:
    """Case + diacritic folding for alias/value matching ("Género" → "genero")."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


class AttributeRegistry:
    def __init__(self, specs: list[AttributeSpec]):
        self._specs = {s.name: s for s in specs}
        self._by_alias: dict[str, AttributeSpec] = {}
        for spec in specs:
            for key in (spec.name, *spec.aliases):
                self._by_alias[fold(key)] = spec

    def resolve(self, name_or_alias: str) -> AttributeSpec | None:
        return self._by_alias.get(fold(name_or_alias))

    def supported_names(self) -> list[str]:
        return sorted(self._specs)

    def specs(self) -> list[AttributeSpec]:
        return list(self._specs.values())

    def __contains__(self, name: str) -> bool:
        return self.resolve(name) is not None


# --- filter matching (contracts/agent-tools.md §3; FR-011/012/013) -------------


class UnsupportedOp(ValueError):
    pass


def matches(spec: AttributeSpec, record: CollectionRecord, op: str, value: Any) -> bool:
    """Kind-appropriate match of one record against one criterion.
    Multi-valued attributes match if ANY value matches. Records with a
    missing attribute only match the numeric `missing` op."""
    if op not in spec.ops:
        raise UnsupportedOp(f"op {op!r} not valid for {spec.kind} attribute {spec.name!r}")

    extracted = spec.extract(record)
    if op == "missing":
        return extracted is None
    if extracted is None or extracted == []:
        return False
    values = extracted if isinstance(extracted, list) else [extracted]

    if spec.kind == "categorical":
        norm = spec.normalize_value or (lambda s: s)
        if op == "eq":
            target = fold(norm(str(value)))
            return any(fold(str(v)) == target for v in values)
        if op == "in":
            targets = {fold(norm(str(t))) for t in (value if isinstance(value, list) else [value])}
            return any(fold(str(v)) in targets for v in values)

    elif spec.kind == "numeric":
        try:
            if op == "between":
                lo, hi = (float(value[0]), float(value[1]))
                return any(lo <= float(v) <= hi for v in values)
            target = float(value)
        except (TypeError, ValueError, IndexError):
            raise UnsupportedOp(f"value {value!r} is not numeric for {spec.name!r}")
        cmp = {
            "eq": lambda v: v == target,
            "lt": lambda v: v < target,
            "lte": lambda v: v <= target,
            "gt": lambda v: v > target,
            "gte": lambda v: v >= target,
        }[op]
        return any(cmp(float(v)) for v in values)

    elif spec.kind == "text":
        if op == "contains":
            return any(fold(str(value)) in fold(str(v)) for v in values)
        if op == "eq":
            return any(fold(str(v)) == fold(str(value)) for v in values)

    raise UnsupportedOp(f"unhandled op {op!r} for kind {spec.kind!r}")


# --- derived extractors -------------------------------------------------------


def _normalize_decade_value(raw: str) -> str:
    """'90s' / 'the 90s' / 'los 90' / '1990' / '1990s' → '1990s'."""
    import re as _re

    m = _re.search(r"(\d{2,4})", raw)
    if not m:
        return raw
    n = int(m.group(1))
    if n < 100:  # two-digit decade: 20s–90s → 1920s–1990s; 00s/10s → 2000s/2010s
        n += 1900 if n >= 20 else 2000
    return f"{(n // 10) * 10}s"


def _decade(rec: CollectionRecord) -> str | None:
    if rec.year is None:
        return None
    return f"{(rec.year // 10) * 10}s"


def _make_scarcity(settings: Settings) -> Callable[[CollectionRecord], str | None]:
    """Composite scarcity bucket (research R9). Thresholds are settings-sourced
    so answers can state them and operators can tune without a re-sync.
    Returns None (→ excluded + counted as missing data) when community stats
    are absent — a record with no stats must never be reported as rare."""

    def scarcity(rec: CollectionRecord) -> str | None:
        if rec.community_have is None or rec.community_want is None:
            return None
        rare_sale = (
            rec.num_for_sale is not None
            and rec.num_for_sale <= settings.rarity_max_for_sale
        )
        rare_ratio = (
            rec.community_have >= settings.rarity_min_have
            and rec.community_want / max(rec.community_have, 1)
            >= settings.rarity_want_have_ratio
        )
        if rare_sale and rare_ratio:
            return "very rare"
        if rare_sale or rare_ratio:
            return "rare"
        return "common"

    return scarcity


# --- launch registry (contracts/agent-tools.md §3) ------------------------------


def build_registry(settings: Settings) -> AttributeRegistry:
    specs = [
        AttributeSpec(
            "genre", ("género", "genero", "genres", "géneros", "generos"),
            "categorical", lambda r: r.genres or None, multi=True,
            unknown_label="unknown genre", description="Discogs genre(s)",
        ),
        AttributeSpec(
            "style", ("estilo", "estilos", "styles"),
            "categorical", lambda r: r.styles or None, multi=True,
            unknown_label="unknown style", description="Discogs style(s), finer than genre",
        ),
        AttributeSpec(
            "year", ("año", "anio", "ano", "years"),
            "numeric", lambda r: r.year,
            unknown_label="unknown year", description="release year",
        ),
        AttributeSpec(
            "decade", ("década", "decada", "decades", "décadas", "decadas"),
            "categorical", _decade,
            unknown_label="unknown decade",
            description='release decade derived from year ("1990s"; accepts "90s", "los 90")',
            normalize_value=_normalize_decade_value,
        ),
        AttributeSpec(
            "label", ("sello", "sellos", "labels", "discográfica", "discografica"),
            "categorical", lambda r: [l.name for l in r.labels] or None, multi=True,
            unknown_label="unknown label", description="record label(s)",
        ),
        AttributeSpec(
            "country", ("país", "pais", "países", "paises", "countries"),
            "categorical", lambda r: r.country,
            unknown_label="unknown country", description="release country of origin",
        ),
        AttributeSpec(
            "artist", ("artista", "artistas", "artists"),
            "categorical", lambda r: r.artists or None, multi=True,
            unknown_label="unknown artist", description="credited artist(s)",
        ),
        AttributeSpec(
            "format", ("formato", "formatos", "formats"),
            "categorical", lambda r: r.formats or None, multi=True,
            unknown_label="unknown format", description='format descriptors ("Vinyl", "12\\"", "LP")',
        ),
        AttributeSpec(
            "folder", ("carpeta", "carpetas", "folders"),
            "categorical", lambda r: str(r.folder_id),
            unknown_label="no folder", description="collection folder (by id; names resolved by tools)",
        ),
        AttributeSpec(
            "my_rating", ("mi rating", "mi puntuación", "mi puntuacion", "my rating", "rating mío", "rating mio"),
            "numeric", lambda r: r.my_rating,
            unknown_label="unrated by me", description="the owner's own 1-5 rating",
        ),
        AttributeSpec(
            "community_rating", ("rating", "puntuación", "puntuacion", "community rating", "rating comunidad"),
            "numeric", lambda r: r.community_rating_avg,
            unknown_label="no community rating", description="Discogs community average rating (0-5)",
        ),
        AttributeSpec(
            "have", ("tienen", "haves"),
            "numeric", lambda r: r.community_have,
            unknown_label="no have data", description='community "have" count',
        ),
        AttributeSpec(
            "want", ("quieren", "wants", "buscado", "buscados"),
            "numeric", lambda r: r.community_want,
            unknown_label="no want data", description='community "want" count',
        ),
        AttributeSpec(
            "num_for_sale", ("en venta", "copias en venta", "for sale"),
            "numeric", lambda r: r.num_for_sale,
            unknown_label="no market data", description="copies currently for sale on Discogs",
        ),
        AttributeSpec(
            "lowest_price", ("precio", "precio mínimo", "precio minimo", "price"),
            "numeric", lambda r: r.lowest_price,
            unknown_label="no price data", description="cheapest copy currently listed (owner currency)",
        ),
        AttributeSpec(
            "scarcity", ("rareza", "raros", "rare", "rarity"),
            "categorical", _make_scarcity(settings),
            unknown_label="no scarcity data",
            description=(
                f"derived rarity bucket (thresholds: ≤{settings.rarity_max_for_sale} for sale, "
                f"want/have ≥{settings.rarity_want_have_ratio} with have ≥{settings.rarity_min_have})"
            ),
        ),
    ]
    return AttributeRegistry(specs)


def render_attribute_block(registry: AttributeRegistry) -> str:
    """The system prompt's attribute documentation — ALWAYS rendered from the
    registry, never hand-written (Constitution VII(b) analog)."""
    lines = []
    for spec in registry.specs():
        multi = ", multi-valued" if spec.multi else ""
        aliases = ", ".join(spec.aliases[:4])
        lines.append(
            f"- `{spec.name}` ({spec.kind}{multi}; ops: {', '.join(spec.ops)}; "
            f"aliases: {aliases}) — {spec.description}"
        )
    return "\n".join(lines)
