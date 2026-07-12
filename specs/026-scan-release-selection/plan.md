# Implementation Plan: Scan Release & Master Selection

**Branch**: `026-scan-release-selection` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/026-scan-release-selection/spec.md`

## Summary

Reshape the scan page's results from a flat candidate list into a
**selected release** (the ladder's top-ranked candidate) with its **master**
surfaced, followed by the remaining candidates as **alternatives** — and give
every displayed release and master a genuine, server-built Discogs page link
that opens in a new tab. Add one **on-demand** capability: a "show other
pressings of this master" action that fetches the selected master's versions
from Discogs only when tapped, presents them as additional selectable
alternatives (same duplicate overlay, same write gate), and never runs
automatically.

Technical approach: `collection-agent` only, zero new dependencies. One new
read-only `DiscogsClient` method (`get_master_versions` →
`GET /masters/{id}/versions`, fourth amendment to 017's discogs-consumption
contract). The `Candidate` wire model gains two additive server-built link
fields (`release_page_url`, `master_page_url`) following 019's
tool-built-link discipline (third amendment to 022's scan-api contract). One
new endpoint `GET /api/master-versions` gated on the requesting cycle's own
candidates, registering fetched versions into the existing session allowlist
so `/api/add` works unchanged. The static phone page renders selected /
master / alternatives and the on-demand section; links are `target="_blank"`
anchors, visually and behaviorally distinct from add buttons. ONE new
`Settings` field (`COLLECTION_AGENT_SCAN_VERSIONS_MAX`). The identification
pipeline (vision, ladder, normalization) is untouched — eval comparability
(023/024/025) is preserved by construction.

## Technical Context

**Language/Version**: Python ≥3.12 (existing `collection-agent` pin)
**Primary Dependencies**: FastAPI + uvicorn (existing scan HTTP surface),
httpx (existing `DiscogsClient`), pydantic / pydantic-settings (existing);
static page is dependency-free vanilla HTML/JS/CSS. **Zero new dependencies.**
**Storage**: existing append-only fsync'd JSONL scan-session journal
(unchanged schema); existing local snapshot (read-only here)
**Testing**: pytest (`cd collection-agent && pytest`), no live API calls;
`FakeDiscogsClient` grows scriptable master-versions responses
**Target Platform**: home-LAN HTTP service (default `0.0.0.0:8022`), phone
browser as primary client (plain HTTP, 022's recorded v1 risk unchanged)
**Project Type**: single component — `collection-agent/` (FastAPI subcommand
+ static page); no other component touched
**Performance Goals**: default results view adds **zero** Discogs requests
and zero latency vs today; on-demand versions fetch = exactly ONE governed
Discogs request per tap
**Constraints**: Discogs 60 req/min authenticated budget (governed
`_request` path); links only from genuine Discogs identifiers (019
discipline); write gate (session allowlist + duplicate confirmation)
must not weaken; journal schema untouched
**Scale/Scope**: owner-scale (one user, 300–1k records); masters can have
100+ versions — single-page fetch capped by the new settings field with
honest truncation messaging

## Constitution Check

*GATE: evaluated against Constitution v1.2.1 before Phase 0; re-checked
after Phase 1 design.*

**Component(s) touched**: `collection-agent` only.

- **I. Layered, contract-first data architecture** — PASS. No ETL layer
  touched. Contract-first is honored for the two contract surfaces this
  feature changes: Discogs API consumption (new read endpoint → 
  `contracts/amendment-017-discogs-consumption-4.md`) and the scan HTTP API
  (new fields + endpoint → `contracts/amendment-022-scan-api-3.md`), both
  written in Phase 1 before implementation.
- **II. Streaming, bounded-memory processing** — N/A. No XML/dump handling.
  The versions fetch is one page, capped.
- **III. Reproducible runs** — N/A (no pipeline runs). The scan journal's
  append-only fsync discipline is unchanged; no new journal line kinds.
- **IV. Data quality gates** — N/A. No layer outputs change.
- **V. Agent-friendly analytics surface** — N/A. DuckDB surface untouched.
- **VI. Components & Contracts** — PASS. All changes live under
  `collection-agent/`; no cross-component imports; the component still runs
  end-to-end alone. The published DuckDB is not read or written.
- **VII. Implementation Discipline** —
  - **(a) Configuration sources**: the versions page-size cap is a NEW
    `Settings` field (`COLLECTION_AGENT_SCAN_VERSIONS_MAX`); Discogs web
    links derive from the EXISTING `DISCOGS_WEB_BASE_URL` settings field —
    the static page never hardcodes the URL shape; it renders only
    server-built links (this is also what keeps the page secrets-free and
    settings-driven). PASS.
  - **(b) Prompt-authoring discipline**: N/A — the vision prompt and agent
    prompts are untouched (explicitly out of scope, as in 023/024/025).
  - **(c) Read-only runtime mechanics**: N/A — no new read-only mounts.
    The eval package is not modified; the 023 AST read-only guard is
    unaffected.
- **Secrets**: PASS — the page stays fully static (existing grep-guarded
  test); the new endpoint carries no token material; links are public web
  URLs.
- **Workflow gates**: this plan states the component, cites principles, and
  writes contracts in the same change set (pipeline-change gate analog for
  the two amended contracts).

**Initial gate result: PASS — no violations, Complexity Tracking empty.**
**Post-Phase-1 re-check: PASS** (design introduced no new components, no
new dependencies, one settings field, two contract amendments written).

## Project Structure

### Documentation (this feature)

```text
specs/026-scan-release-selection/
├── plan.md                                      # This file
├── research.md                                  # Phase 0 (R1–R9)
├── data-model.md                                # Phase 1
├── quickstart.md                                # Phase 1 (+ owner checklist)
├── checklists/requirements.md                   # From /speckit-specify
├── contracts/
│   ├── amendment-017-discogs-consumption-4.md   # + GET /masters/{id}/versions
│   └── amendment-022-scan-api-3.md              # + link fields, + /api/master-versions
└── tasks.md                                     # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── settings.py                  # + scan_versions_max (ONE new field)
│   ├── discogs/client.py            # + get_master_versions (read-only)
│   ├── tools/common.py              # release_page_url refactored to id-based
│   │                                #   core + NEW master_page_url (single
│   │                                #   URL-shape site per id space, 019/020
│   │                                #   grep discipline)
│   └── scan/
│       ├── models.py                # Candidate + release_page_url/master_page_url;
│       │                            #   NEW VersionsResponse wire model
│       ├── search.py                # _candidate_from_result enriches links
│       │                            #   (settings passed down); NEW
│       │                            #   versions→Candidate mapping
│       ├── server.py                # NEW GET /api/master-versions (cycle-gated,
│       │                            #   allowlist-registering, no generation bump);
│       │                            #   _CycleContext tracks candidate master_ids
│       └── static/index.html        # selected/master/alternatives layout,
│                                    #   new-tab links, on-demand pressings UI
└── tests/                           # new unit+integration tests (~30);
                                     #   FakeDiscogsClient grows master-versions
                                     #   scripting; grep-guards extended
```

**Structure Decision**: single existing component `collection-agent/`; no
new top-level directories; `eval/`, `agent/`, `etl/`, `frontend/` untouched.

## Complexity Tracking

No constitution violations — table intentionally empty.
