# Implementation Plan: Scan Accuracy Follow-ups (Eval-Driven)

**Branch**: `024-scan-accuracy-followups` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/024-scan-accuracy-followups/spec.md`

## Summary

Three small, evidence-driven changes inside `collection-agent`, all traced to
023's first measured eval (94-image run + 14-miss live spot-check):

1. **Exact-catno re-rank** (`scan/search.py`): the catno rung fetches a deeper
   page (`COLLECTION_AGENT_SCAN_CATNO_SEARCH_DEPTH`, default 50, one request as
   before), stable-partitions raw results so separator-normalized exact catno
   matches come first, then builds verbatim Candidates capped as today. Fixes
   the measured `SUB 15`-drowned-by-`SUB 150/152` class for both the scan page
   and the eval (shared pipeline).
2. **Evidence in eval results** (`eval/scoring.py` + `eval/harness.py`):
   `EvalResult` gains an optional `evidence` field carrying
   `ScanEvidence.compact_dump()` — the journal's exact FR-021 shape — so
   zero-candidate misses are diagnosable from `results.jsonl` alone.
3. **Same-master near-miss metric** (`eval/dataset.py`, `eval/sources.py`,
   `eval/scoring.py`, `scan/models.py`): manifest release lines gain optional
   `master_id` (from the already-fetched release payload; `--backfill-masters`
   upgrades existing datasets, newest-line-per-release wins), `Candidate`
   carries the search result's `master_id` verbatim, misses are classified
   `same_master` / `different` / `unknown`, and the summary reports a
   practical rate beside the unchanged strict rate with extended sum
   invariants.

Contract deltas are recorded as amendments (one per amended contract):
017 discogs-consumption (3rd amendment), 022 scan-api, 023 eval-dataset,
023 eval-results. Suite stays 100% offline.

## Technical Context

**Language/Version**: Python 3.12 (existing `collection-agent`)
**Primary Dependencies**: unchanged (httpx, pydantic v2, openai SDK, rich) — zero new dependencies
**Storage**: existing gitignored `data/eval/` files; manifest and results schemas extended additively
**Testing**: pytest, offline; 410 tests at branch point
**Target Platform**: owner's laptop, terminal CLI (+ LAN scan page)
**Project Type**: changes inside an existing component
**Performance Goals**: catno rung stays one search request (deeper `per_page`, same 60/min budget); backfill = one `get_release` per already-done release, governor-paced, one sitting at 300–1k scale
**Constraints**: strict rate definition unchanged; 023-format manifests/results stay readable; non-catno rungs byte-identical; no live calls in tests
**Scale/Scope**: ~5 source modules touched + `cli.py` + `settings.py`; ~7 test files extended

## Constitution Check

*Constitution v1.2.1. Component(s) touched: `collection-agent` only.*

| Principle | Engagement | Status |
|---|---|---|
| I–V (ETL/data-layer) | Not engaged — no DuckDB/published-artifact surface. Analog honored: every schema change lands as a contract amendment in this feature's `contracts/` before code. | ✅ |
| VI. Components & contracts | Single component; no cross-component imports; consumption change (search `master_id` field, catno `per_page`) recorded as the 3rd amendment to 017's discogs-consumption contract. | ✅ |
| VII(a). Configuration | One new Settings field (`scan_catno_search_depth`); no hardcoded depth. | ✅ |
| VII(b). Prompt authoring | Not engaged — vision prompt frozen (spec Out of Scope). | ✅ |
| VII(c). Read-only mechanics | Eval package stays structurally read-only; the existing AST guard automatically covers all new eval code (backfill lives in `eval/dataset.py` and uses only `get_release` — a read). | ✅ |
| Secrets | No new `get_secret_value` sites (audit count stays 3). | ✅ |
| Workflow gates | Spec → plan → tasks → analyze → implement, committed per phase; offline tests; README/quickstart updated. | ✅ |

**Post-design re-check** (after Phase 1): no violations; Complexity Tracking
stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/024-scan-accuracy-followups/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions R1–R7
├── data-model.md        # field-level deltas
├── quickstart.md        # owner runbook: backfill + re-eval + live validation
├── checklists/requirements.md
├── contracts/
│   ├── amendment-017-discogs-consumption-3.md   # +search master_id field; catno per_page=depth
│   ├── amendment-022-scan-api.md                # Candidate +master_id (verbatim); catno ordering note
│   ├── amendment-023-eval-dataset.md            # manifest +master_id; newest-line-wins; backfill mode
│   └── amendment-023-eval-results.md            # result +evidence, +miss_master_relation; summary practical fields + invariants 8–10
└── tasks.md             # /speckit-tasks output
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── settings.py            # +scan_catno_search_depth (default 50)
│   ├── cli.py                 # eval-dataset --backfill-masters; summary table practical row
│   ├── scan/
│   │   ├── models.py          # Candidate +master_id (verbatim optional)
│   │   └── search.py          # normalize_catno(); catno rung: depth fetch + stable exact-first partition
│   └── eval/
│       ├── dataset.py         # ManifestRelease +master_id; newest-line-per-release reader; backfill_masters()
│       ├── sources.py         # newest-line-wins consumption; EvalItem carries truth master_id
│       ├── scoring.py         # EvalResult +evidence +miss_master_relation; summary practical fields; invariants
│       └── harness.py         # passes evidence + master classification through
└── tests/
    ├── fixtures/discogs_payloads.py     # search_result(+master_id kwarg)
    ├── unit/test_scan_search.py         # re-rank ordering rules incl. the SUB 15 replay
    ├── unit/test_scan_models.py         # Candidate master_id verbatim/absent
    ├── unit/test_eval_dataset.py        # master_id recorded; backfill; newest-line-wins
    ├── unit/test_eval_sources.py        # dedup + truth-master passthrough
    ├── unit/test_eval_scoring.py        # classification + extended invariants
    └── integration/test_eval_harness.py # evidence in records; practical rate end-to-end
```

**Structure Decision**: pure extension of 023's layout — zero new modules;
every change lands in an existing file, keeping the diff reviewable one-to-one
against the four contract amendments.

## Complexity Tracking

No constitution violations to justify.
