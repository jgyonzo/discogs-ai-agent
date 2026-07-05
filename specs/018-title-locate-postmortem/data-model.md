# Data Model: Title-Aware Record Location (Postmortem)

**Feature**: 018-title-locate-postmortem | **Date**: 2026-07-05

No storage, snapshot-schema, or API changes. Two design-time entities.

## 1. Registry entry: `title` (new `AttributeSpec`)

Extends the launch set of 017's data-model §4 / agent-tools contract §3.

| Field | Value | Notes |
|---|---|---|
| `name` | `title` | canonical attribute name |
| `aliases` | `título`, `titulo`, `titles`, `títulos`, `titulos` | en+es, matched via `fold()` (case/diacritic-insensitive), consistent with every existing attribute |
| `kind` | `text` | first user of the pre-existing text kind |
| `ops` | `contains`, `eq` | derived from `OPS_BY_KIND["text"]` — not declared per-entry |
| `extract` | record title, `None` when empty | `lambda r: r.title or None`; empty string normalizes to the standard missing-value path |
| `multi` | `False` | one title per collection instance |
| `unknown_label` | `unknown title` | bucket label in aggregations |
| `description` | one-liner: release title, substring search via `contains` | rendered into the prompt attribute block automatically |
| `normalize_value` | — (unset) | folding happens inside `matches()` for text kind |

### Matching semantics (all pre-existing `matches()` behavior, now exercised)

- `contains`: `fold(value) in fold(title)` — case- and diacritic-insensitive
  substring ("espaco" matches "Espaço E Tempo").
- `eq`: `fold(title) == fold(value)` — exact modulo folding.
- Missing/empty title → extracted `None` → matches nothing (no `missing`
  op exists for text kind); aggregates under `unknown title`.
- AND-combination with any other criterion via `filter_records` (e.g.
  `artist eq "Guido Schneider" AND title contains "focus on"`).
- Unsupported ops (e.g. `between`) → `unsupported_criteria` with the valid
  op list (FR-013a path, unchanged).

## 2. Prompt guidance: "Locating a specific record" (system.md)

A procedural subsection appended to the system prompt (under Answer
style / ground rules). Content model — the guidance MUST convey exactly
these four rules (FR-006):

1. Filter by `artist` AND a distinctive `title contains` substring.
2. Strip format qualifiers from the queried title before searching
   (e.g. "2xLP", "2x12", "EP" suffixes the user appended).
3. Never request a reduced `limit` when the question is whether a record
   is present; rely on the default cap and the reported `count`.
4. Zero matches with a title criterion ≠ absent: retry with artist only
   and inspect that listing before telling the user the record is not in
   the collection.

Constraint (Constitution VII(b) analog): this section is procedure only —
it must not enumerate attributes, ops, or collection facts; those enter
solely via the registry-rendered `{attribute_block}`.

## 3. Unchanged entities (for reviewer orientation)

- `CollectionRecord.title: str` — already synced and displayed in every
  listing; no snapshot/sync change.
- `FilterCriterion` / `filter_records` / `aggregate_by` — untouched
  (SC-003 measures this).
- `settings.filter_result_limit` (default 50) — unchanged; remains the
  "standard cap" the guidance refers to.
