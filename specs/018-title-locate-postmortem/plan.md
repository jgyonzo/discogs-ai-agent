# Implementation Plan: Title-Aware Record Location (Postmortem)

**Branch**: `018-title-locate-postmortem` | **Date**: 2026-07-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/018-title-locate-postmortem/spec.md`

## Summary

Two compounding gaps made the collection agent falsely deny owning records
it has synced: (1) `title` is not a filterable attribute in the declarative
registry, so "locate Artist – Title" degenerates into an artist-only
listing; (2) for locate-one-record questions the LLM passes `limit=1`, so
the listing truncates to the first record in snapshot order and the target
title is never seen. Fix: **(a)** add a `title` text-kind `AttributeSpec`
to `build_registry()` — the registry's own extension rule (agent-tools
contract §3, SC-003a) means `filter_records`, `aggregate_by`, and the
system-prompt attribute block pick it up with zero tool-code changes;
**(b)** add locate-a-specific-record guidance to the system prompt
(`prompts/system.md`): filter artist + title substring, strip format noise,
never shrink the limit on presence checks, artist-only retry before
declaring absence. Plus unit tests and a contract amendment recording the
new launch-set member.

**Component(s) touched**: `collection-agent` only (plan gate requirement).

## Technical Context

**Language/Version**: Python ≥3.12 (existing `collection-agent/pyproject.toml`)
**Primary Dependencies**: pydantic v2, pydantic-settings, openai ≥1.40 (all existing; no new dependencies)
**Storage**: local JSON snapshot at `collection-agent/data/snapshot.json` (unchanged; `CollectionRecord.title` already exists and is populated by sync)
**Testing**: pytest (`cd collection-agent && pytest`), ~106 existing tests, no live API calls
**Target Platform**: developer terminal (macOS/Linux), same as 017
**Project Type**: single component in monorepo — CLI conversational agent
**Performance Goals**: conversational-speed filtering over 300–1k records (folded substring scan is O(n) over ≤1k records — negligible)
**Constraints**: SC-003a extension rule — no edits to `tools/browse.py`, `tools/analytics.py`; attribute docs must stay registry-rendered (Constitution VII(b) analog)
**Scale/Scope**: 1 registry entry, 1 prompt section, ~2 test modules touched; no schema, sync, or API changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Layered, contract-first data architecture | N/A | No ETL layer or published DuckDB touched. |
| II. Streaming, bounded memory | N/A | No XML/pipeline code touched. |
| III. Reproducible runs | N/A | No pipeline execution changes. |
| IV. Data quality gates | N/A | No layer outputs change. |
| V. Agent-friendly analytics surface | N/A | Catalog surface untouched (this is the collection agent, not the catalog agent). |
| VI. Components & Contracts | **PASS** | `collection-agent` only; no cross-component imports; live Discogs API + component-local snapshot remain its only surfaces. The amended contract is 017's own `contracts/agent-tools.md` §3 launch set — amended via this feature's `contracts/amendment-017-agent-tools.md`, following the 008→004 amendment pattern. |
| VII(a). Configuration sources | **PASS** | No new config values. The "standard cap" in the prompt guidance is behavioral prose, not a literal — the actual cap stays `settings.filter_result_limit`. |
| VII(b). Prompt-authoring discipline (analog) | **PASS** | The `title` attribute enters the prompt exclusively through the registry-rendered `{attribute_block}`. The new system.md section is *procedural* guidance (how to run a presence check), not attribute/schema prose — the same category as the existing "Answer style" rules. It names no attribute inventory. |
| VII(c). Read-only runtime mechanics | N/A | No runtime mounts touched. |
| Spec-driven flow / plan gate | **PASS** | This plan; phases committed separately. |

**Post-Phase-1 re-check**: PASS — design artifacts introduce no new
violations; no Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/018-title-locate-postmortem/
├── spec.md              # /speckit-specify output (committed)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── amendment-017-agent-tools.md   # §3 launch-set + prompt-guidance amendment
├── checklists/
│   └── requirements.md  # spec quality checklist (committed)
└── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── registry.py                  # MODIFIED: + title AttributeSpec in build_registry()
│   └── prompts/
│       └── system.md                # MODIFIED: + "Locating a specific record" guidance
└── tests/
    ├── unit/
    │   ├── test_registry.py         # MODIFIED: + title spec/matching tests
    │   └── test_filters.py          # MODIFIED: + artist+title AND filter test
    └── integration/
        └── test_agent_loop.py       # MODIFIED (if prompt-render test lives here): guidance-presence assertion
```

**Structure Decision**: existing 017 layout; two source files modified, two
to three test files extended. No new modules, no new tools, no new
dependencies. `tools/browse.py` / `tools/analytics.py` are deliberately
untouched (SC-003 measures exactly this).

## Phase 0: Research → [research.md](research.md)

All unknowns resolved; no NEEDS CLARIFICATION markers existed. Key
decisions: text-kind registry entry (R1), `extract` returns `None` for
empty titles (R2), procedural prompt guidance rather than a new tool or a
truncation-behavior change (R3), no fuzzy matching (R4).

## Phase 1: Design & Contracts

- **[data-model.md](data-model.md)** — the `title` `AttributeSpec` entry
  (fields, folding semantics, unknown-label) and the prompt-guidance
  content model.
- **[contracts/amendment-017-agent-tools.md](contracts/amendment-017-agent-tools.md)**
  — amends 017's `contracts/agent-tools.md` §3: launch set gains `title`;
  records the locate-a-record prompt guidance as normative agent behavior.
- **[quickstart.md](quickstart.md)** — replay recipe for the four incident
  queries + test commands.
- **Agent context** — `CLAUDE.md` updated to point at this plan as the
  in-flight feature.

## Complexity Tracking

No constitution violations — table intentionally empty.
