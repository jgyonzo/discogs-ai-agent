# Amendment: 017 `contracts/agent-tools.md` — title attribute + locate guidance

**Feature**: 018-title-locate-postmortem | **Date**: 2026-07-05
**Amends**: `specs/017-discogs-collection-agent/contracts/agent-tools.md`

Follows the 008 → 004 amendment pattern: this file records the exact
normative deltas; the 017 contract file itself is not rewritten.

## Delta 1 — §3 launch set gains `title`

The **Launch set** list in §3 (Attribute registry) is amended to read:

> **Launch set**: `genre, style, year, decade, label, country, artist,
> format, folder, my_rating, community_rating, have, want, num_for_sale,
> lowest_price, scarcity, title` *(title added by 018)*.

`title` is the first attribute of kind `text` (ops `contains, eq` per the
existing **Ops by kind** table, which is unchanged). Declaration per
`specs/018-title-locate-postmortem/data-model.md` §1: aliases
`título/titulo/titles/títulos/titulos`, single-valued, extracted from the
record title with empty titles normalized to missing
(`unknown_label = "unknown title"`).

The **Extension rule (SC-003a)** is exercised, not modified: 018 adds the
attribute as one registry entry plus unit tests, with zero changes to
`filter_records`, `aggregate_by`, or hand-written prompt prose.

## Delta 2 — normative agent behavior: presence checks

New normative behavior (rendered as a procedural section of the system
prompt, `collection-agent/src/collection_agent/prompts/system.md`):

When the user asks whether a specific named record is in the collection
("locate X", "do I have X"), the agent MUST:

1. filter by `artist` AND a distinctive `title contains` substring;
2. strip format qualifiers (e.g. "2xLP", "2x12") from the queried title
   text before searching;
3. NOT request a `limit` below the standard cap for the presence check;
4. on zero matches, retry with the artist criterion only and inspect that
   listing before answering that the record is absent — "not among the
   rows shown" of a truncated listing is never grounds for "not in your
   collection".

This section is procedural only (Constitution VII(b) analog): attribute
inventory continues to enter the prompt exclusively via the
registry-rendered attribute block.

Post-replay hardening (spec FR-006 (e)–(f)): the guidance additionally
mandates substring matching (never `eq`) with a **short** distinctive
substring, and affirming near-matches (suffix/casing/accent/extra-word
differences) as the requested record rather than "related" items.

## Delta 3 — `filter_records` zero-match note is retry-aware (FR-009)

017's FR-013b behavior ("no records matched — say so explicitly; do not
invent results") is amended: that plain note now applies only when **no
text-kind criterion** was applied. When at least one applied criterion is
text-kind (e.g. `title contains …`), the zero-match note instead instructs
the agent to loosen the search — drop the text criterion or use a shorter
distinctive substring — before telling the user the record is absent,
while still forbidding invented results.

Rationale (replay postmortem, 2026-07-05): at the zero-match decision
point the LLM follows the in-result note over the standing prompt; the
note must therefore point toward the presence-check retry, not toward an
immediate "not found" answer. Payload shape is unchanged (`note` remains a
string; no new fields).

## Delta 4 — text criteria default to `contains` (FR-010)

`filter_records` criteria whose attribute is text-kind and whose `op` was
**omitted** by the caller default to `contains` instead of the schema-wide
`eq` default; an explicitly passed `op` (including `eq`) is honored, and
`criteria_applied` discloses the effective op. Replay evidence
(2026-07-05): the LLM frequently omits `op`, and a silent `eq` default on
title recreates the false-absence failure regardless of prompt guidance.

## Delta 5 — deterministic fallback listing on text-criterion zero-match (FR-011)

When `filter_records` matches zero records and the applied criteria
include at least one text-kind criterion **and** at least one non-text
criterion, the payload additionally carries `fallback_matches` (records
matching the non-text criteria only, same display shape, capped at the
effective limit) and `fallback_count`, with a note instructing the agent
to inspect the fallback for a near-miss title before reporting absence.
The session's last-listing refs point at the fallback records. Not
emitted for text-only or non-text-only zero-matches.

Rationale (second replay, 2026-07-05): the Delta-3 note improved but did
not guarantee the agent's self-retry in batch turns; per the 013→014
precedent the retry is promoted from steering to deterministic tool
behavior. Additive: two new optional payload fields; existing fields and
their semantics are unchanged.

## Compatibility

- Additive only: no existing attribute, op, tool signature, or payload
  field changes. Existing conversations/tests are unaffected.
- `unsupported_criteria` (FR-013a) behavior extends to `title`
  automatically (e.g. numeric ops on `title` are reported, not dropped).
