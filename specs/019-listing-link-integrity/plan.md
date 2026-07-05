# Implementation Plan: Listing Link Integrity

**Branch**: `019-listing-link-integrity` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/019-listing-link-integrity/spec.md`

## Summary

During the 018 replays the LLM fabricated Discogs links by pasting the
listing payload's `instance_id` into a release-page URL pattern
(`discogs.com/release/<instance_id>` — wrong id space), violating
system-prompt ground rule 1. Root cause: at the "give me the link" decision
point the only URL-shaped material in the payload is an internal id, so the
LLM improvises. Fix (013→014/018 precedent — deterministic enforcement over
prompt steering): **(a)** every per-record listing entry gains a genuine
`release_url` built by the tool from `CollectionRecord.release_id` (captured
in the sync instance pass, so present in every snapshot state) via a shared
helper in `tools/common.py`, with the web base URL sourced from settings
(Constitution VII(a)); **(b)** ground rule 1 in `prompts/system.md` is
extended to name `release_url` as the only source for a record's Discogs
page and to forbid constructing URLs from any identifier; **(c)** 017's
agent-tools contract §1/§5 is amended via this feature's
`contracts/amendment-017-agent-tools.md`. `instance_id` stays in the payload
unchanged — follow-up references (moves, "their links", ordinals) depend on
it; the improvisation pressure is removed by the real URL, not by obfuscating
the id (research R1).

**Component(s) touched**: `collection-agent` only (plan gate requirement).

## Technical Context

**Language/Version**: Python ≥3.12 (existing `collection-agent/pyproject.toml`)
**Primary Dependencies**: pydantic v2, pydantic-settings, openai ≥1.40 (all existing; no new dependencies)
**Storage**: local JSON snapshot at `collection-agent/data/snapshot.json` (unchanged; `CollectionRecord.release_id` already exists — instance pass, models.py — so old snapshots need no re-sync)
**Testing**: pytest (`cd collection-agent && pytest`), 131 existing tests, no live API calls
**Target Platform**: developer terminal (macOS/Linux), same as 017/018
**Project Type**: single component in monorepo — CLI conversational agent
**Performance Goals**: conversational-speed serving unchanged (URL construction is an f-string per shown record, ≤ result cap per call)
**Constraints**: VII(a) — web base URL from settings, not a hardcoded literal; VII(b) analog — prompt change is a link-sourcing ground rule, no attribute/schema prose; media-links answer shape (verbatim URIs, `none` flag) preserved (spec FR-005)
**Scale/Scope**: 1 settings field, 1 shared helper, 3 tool payload shapes (`filter_records` matches + fallback, `top_n`, `media_links`), 1 prompt rule, 1 contract amendment; no schema, sync, or API changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Layered, contract-first data architecture | N/A | No ETL layer or published DuckDB touched. |
| II. Streaming, bounded memory | N/A | No XML/pipeline code touched. |
| III. Reproducible runs | N/A | No pipeline execution changes. |
| IV. Data quality gates | N/A | No layer outputs change. |
| V. Agent-friendly analytics surface | N/A | Catalog surface untouched (collection agent, not catalog agent). |
| VI. Components & Contracts | **PASS** | `collection-agent` only; no cross-component imports. The amended contract is 017's own `contracts/agent-tools.md` (§1 listing shapes, §5 prompt obligations), amended via this feature's `contracts/amendment-017-agent-tools.md` — same pattern as 018's §3 amendment. `collection_matcher/export_batch.py` builds the same URL shape independently for the offline exporter; no shared code is introduced across the two packages (they stay import-free of each other). |
| VII(a). Configuration sources | **PASS** | New settings field `discogs_web_base_url` (alias `DISCOGS_WEB_BASE_URL`, default `https://www.discogs.com`), distinct from the existing API base `DISCOGS_BASE_URL`. No hardcoded URL literals in tool code. |
| VII(b). Prompt-authoring discipline (analog) | **PASS** | The prompt change extends ground rule 1 (link sourcing) — procedural guidance, not attribute/schema prose. Attribute docs remain registry-rendered via `{attribute_block}`. |
| VII(c). Read-only runtime mechanics | N/A | No runtime mounts touched. |
| Spec-driven flow / plan gate | **PASS** | This plan; phases committed separately. |

**Post-Phase-1 re-check**: PASS — design artifacts introduce no new
violations; no Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/019-listing-link-integrity/
├── spec.md              # /speckit-specify output (committed)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── amendment-017-agent-tools.md   # §1 listing-shape + §5 link-sourcing amendment
├── checklists/
│   └── requirements.md  # spec quality checklist (committed)
└── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── settings.py                   # MODIFIED: + discogs_web_base_url (DISCOGS_WEB_BASE_URL)
│   ├── tools/
│   │   ├── common.py                 # MODIFIED: + release_page_url(settings, record) helper
│   │   ├── browse.py                 # MODIFIED: _display gains release_url (matches + fallback_matches)
│   │   ├── analytics.py              # MODIFIED: _display gains release_url (top_n rankings)
│   │   └── media.py                  # MODIFIED: per_record gains release_url; note text distinguishes page vs media
│   └── prompts/
│       └── system.md                 # MODIFIED: ground rule 1 extended — release_url is the only page-link source
└── tests/
    ├── unit/
    │   ├── test_filters.py           # MODIFIED: release_url presence + id-space assertions (incl. fallback)
    │   ├── test_analytics.py         # MODIFIED: release_url in ranking entries
    │   └── test_media.py             # MODIFIED: release_url alongside verbatim links; shape preserved
    └── integration/
        └── test_agent_loop.py        # MODIFIED: prompt ground-rule assertion; listing-payload link invariant
```

**Structure Decision**: existing 017 layout; five source files and four test
files modified. No new modules beyond one helper function, no new tools, no
new dependencies. The 018 registry/prompt layers are untouched — this is a
payload + prompt change, deliberately on the deterministic-enforcement rung
of the 018 escalation ladder.

## Phase 0: Research → [research.md](research.md)

All unknowns resolved; no NEEDS CLARIFICATION markers existed. Key
decisions: real tool-provided URL instead of id obfuscation (R1), canonical
release-page URL shape from `release_id` with settings-sourced base (R2),
one shared URL helper + per-tool field addition (R3), ground-rule extension
rather than a new prompt section (R4), replay + id-space test strategy (R5).

## Phase 1: Design & Contracts

- **[data-model.md](data-model.md)** — the listing-entry display shape
  (+`release_url`), the settings field, and the invariant that all copies of
  a release share one URL while keeping distinct instance references.
- **[contracts/amendment-017-agent-tools.md](contracts/amendment-017-agent-tools.md)**
  — amends 017's `contracts/agent-tools.md`: §1 read-tool listing shapes
  carry `release_url`; §5 system-prompt obligations gain the link-sourcing
  rule (page links from `release_url`, media from `media_links`, URL
  construction from identifiers forbidden).
- **[quickstart.md](quickstart.md)** — replay recipe for the invented-URL
  incident prompts + test commands + one manual live-link spot check.
- **Agent context** — `CLAUDE.md` updated to point at this plan as the
  in-flight feature.

## Complexity Tracking

No constitution violations — table intentionally empty.
