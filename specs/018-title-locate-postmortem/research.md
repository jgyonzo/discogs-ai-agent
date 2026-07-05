# Research: Title-Aware Record Location (Postmortem)

**Feature**: 018-title-locate-postmortem | **Date**: 2026-07-05

No NEEDS CLARIFICATION markers existed in the spec (scope was pinned by the
incident transcript). Research consisted of verifying the incident against
the live snapshot and choosing between implementation shapes.

## R1 — Where does title filtering live?

**Decision**: A `title` text-kind `AttributeSpec` in `build_registry()`
(`collection-agent/src/collection_agent/registry.py`).

**Rationale**: The registry is the declared extension point: one entry
gives `filter_records` support, `aggregate_by` support, and a line in the
registry-rendered prompt attribute block automatically (agent-tools
contract §3, SC-003a). The `text` kind already exists in `OPS_BY_KIND`
(`contains`, `eq`) and `matches()` already implements fold()-based
(case + diacritic-insensitive) text comparison — **no registry-framework
code changes are needed**, only the declaration. `fold("Espaço")` →
`"espaco"` was verified interactively, so the incident's diacritic case is
covered for free.

**Alternatives considered**:
- *A dedicated `locate_record` tool* — rejected: violates SC-003a's spirit
  (new tool code for what the registry already expresses), grows the tool
  surface the LLM must route between, and duplicates `filter_records`.
- *Reusing `media_links._resolve` fuzzy matching in browse* — rejected:
  spec places `media_links` out of scope; `_resolve` concatenates
  artist+title, which is exactly the ambiguity the registry attribute
  avoids (title criterion must read the title field only — spec edge case).

## R2 — Empty/missing titles

**Decision**: `extract=lambda r: r.title or None` — a record with an empty
title contributes `None`, which the existing `matches()` machinery treats
as "does not match any non-`missing` op" (registry.py: `extracted is None
→ False`). Text kind has no `missing` op, so empty-title records simply
never match a title criterion (spec FR-007) and appear under
`unknown_label="unknown title"` in aggregations.

**Rationale**: `CollectionRecord.title` is `str` (required, may be `""` if
Discogs ever returns an empty basic-information title); `or None`
normalizes that edge into the registry's standard missing-value path.

**Alternatives considered**: `lambda r: r.title` bare — rejected: `""`
would then be a matchable value (`contains ""` matches everything) and
would surface as an empty-string bucket in `aggregate_by(title)`.

## R3 — How to stop the limit=1 truncation failure

**Decision**: Procedural guidance in `prompts/system.md` (a short
"Locating a specific record" subsection): filter by artist AND a
distinctive title substring with format noise ("2xLP", "2x12") stripped;
never pass a small `limit` when the question is presence; on zero title
matches, retry artist-only and inspect the listing before declaring the
record absent.

**Rationale**: The tool behaved correctly in the incident — it returned
`count`, `truncated`, and a truncation note; the *LLM* chose `limit=1` and
misread "not among rows shown" as "absent". That is a prompting problem.
Guidance is the same mechanism 012/013 used (glossary/prompt steering)
when tool output was correct but LLM strategy was wrong.

**Alternatives considered**:
- *Reject small limits in `filter_records`* — rejected: `limit` is
  legitimate for "show me a few" listings; the tool cannot know the
  question is a presence check.
- *Force minimum limit for single-criterion artist filters* — rejected:
  same problem, plus it silently overrides an explicit argument
  (violates "never silently drop/alter criteria" ethos of FR-013a).
- *Constitution VII(b) concern* — the guidance describes **procedure**,
  not attribute inventory; attribute facts still enter only via
  `{attribute_block}`. Verified wording contains no attribute list.

## R4 — Fuzzy / typo-tolerant matching

**Decision**: Out of scope (per spec). "gone astral" vs "Gone Astray" is
handled by the artist-only-retry guidance, not edit-distance matching.

**Rationale**: At 300–1k records, an artist-scoped listing is small enough
for the LLM to eyeball near-miss titles reliably; edit-distance thresholds
would add tuning surface and new failure modes (false positives across
volumes/series) for marginal gain.

**Alternatives considered**: rapidfuzz/difflib scoring in `matches()` —
rejected as above; also would be the only non-deterministic-feeling
operator in an otherwise exact, explainable filter surface.

## Incident verification (2026-07-05, live snapshot)

- Snapshot contains: `Guido Schneider – Focus On Guido Schneider`
  (instance 1081571663), `Troy Pierce – Gone Astray EP` (1082795291),
  `DJ Minx – A Walk In The Park EP` (1082794856), `Click Box – Espaço E
  Tempo` (1082793881).
- Snapshot ordering places `Styleways` before `Focus On Guido Schneider`
  and `25 Bitches Vol. II` before `Gone Astray EP` — consistent with the
  observed "shown 1 of N" answers under `limit=1`.
- `settings.filter_result_limit` defaults to 50 → the observed 1-row
  listings could only come from an explicit `limit=1` tool argument.
