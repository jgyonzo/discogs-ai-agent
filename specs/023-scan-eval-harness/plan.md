# Implementation Plan: Scan Identification Eval Dataset & Harness

**Branch**: `023-scan-eval-harness` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/023-scan-eval-harness/spec.md`

## Summary

Build the measurement loop for 022's scan identification pipeline, entirely inside
the `collection-agent` component:

1. **Dataset builder** (`eval-dataset` CLI subcommand): walks the distinct
   release_ids of the existing local snapshot, re-fetches each release via the
   already-contracted `GET /releases/{id}` (now also consuming its `images[]`
   field — second amendment to 017's discogs-consumption contract), downloads up
   to N images per release (secondary-preferred) through the existing
   rate-limit-governed `DiscogsClient`, into a gitignored
   `collection-agent/data/eval/discogs-images/` directory with an append-only
   JSONL manifest as ground truth. Resumable and idempotent.
2. **Opt-in photo retention** (`scan/retention.py` + one hook in
   `scan/server.py`): a new default-off Settings flag persists each uploaded scan
   photo under `data/eval/scan-photos/<session_id>/`, renamed to
   `<scan_id>.<ext>` once the cycle id exists. Ground truth joins lazily against
   the existing scan journal (`added` outcome → release_id). Retention failure is
   loud (server log) but never breaks the scan flow.
3. **Eval harness** (`eval-run` CLI subcommand): feeds each labeled image through
   the production seams — `scan/vision.py::extract_evidence` (client built via
   `cli.py::_build_llm_client`, so LangSmith tracing applies) then
   `scan/search.py::find_candidates` — and scores hit/miss/rank/rung/evidence
   kinds into a run-scoped results JSONL plus a summary (identification rate,
   top-1 rate, per-rung attribution, no-evidence/error/unlabeled counts,
   billable-call count). Strictly read-only against Discogs, structurally
   guard-tested.

Owner-run only; the pytest suite stays 100% offline (pure logic covered by unit
tests over `FakeDiscogsClient`/scripted LLM stubs, per 022 precedent).

## Technical Context

**Language/Version**: Python 3.12 (existing `collection-agent` component)
**Primary Dependencies**: httpx, pydantic v2 + pydantic-settings, openai SDK,
rich (all already in `collection-agent/pyproject.toml`) — **zero new dependencies**
**Storage**: local files under gitignored `collection-agent/data/eval/`
(dataset images + JSONL manifest, retained photos, run results); existing
snapshot JSON and scan journals are read, never modified
**Testing**: pytest (`cd collection-agent && pytest`), offline; 344 tests at
branch point
**Target Platform**: owner's laptop (macOS), terminal CLI
**Project Type**: CLI subcommands inside an existing component
**Performance Goals**: full dataset build for 300–1k releases completes in one
sitting within the Discogs 60 req/min budget (minutes-scale, governor-paced);
eval throughput is vision-latency-bound (~1–3 s/image typical, 45 s hard cap
via existing `scan_vision_timeout_s`)
**Constraints**: no live API calls in tests; no image ever committed
(uploader-copyrighted); harness has no Discogs write path; retention default-off
with byte-identical behavior when off
**Scale/Scope**: 300–1k distinct releases → ≤2k dataset images; eval runs
typically limited (`--limit`) for cost control

## Constitution Check

*Constitution v1.2.1. Component(s) touched: `collection-agent` only.*

| Principle | Engagement | Status |
|---|---|---|
| I. Layered, contract-first data | Not engaged — no ETL layer touched. The analog is honored: dataset manifest and results schemas are documented contracts (`contracts/eval-dataset.md`, `contracts/eval-results.md`) before implementation. | ✅ |
| II. Bounded memory | Not engaged (no XML). Builder/harness stream: one release / one image at a time; JSONL appended incrementally. | ✅ |
| III. Reproducible runs, manifest & logs | ETL-scoped, but adopted as analog: every build appends a run-header + per-release lines to the dataset manifest; every eval run has a run id, per-image results JSONL, and a summary. Resume flags (`--limit`, idempotent re-run) mirror the discipline. | ✅ |
| IV. Data quality gates | Not engaged (no published layer). Summary sum-invariants are the analog and are unit-tested. | ✅ |
| V. Agent-friendly analytics surface | Not engaged — no DuckDB, no registry/tool changes, no prompt changes. | ✅ |
| VI. Components & contracts | `collection-agent` only. No cross-component imports (existing `test_no_cross_imports.py` still enforces). All new data lives under the component's own gitignored `data/`. The Discogs consumption change is recorded as a contract amendment in this feature's `contracts/`. | ✅ |
| VII(a). Configuration sources | Five new Settings fields (dirs, per-release image cap, retention flag), all env-driven `COLLECTION_AGENT_*`; no hardcoded paths/limits. | ✅ |
| VII(b). Prompt authoring | Not engaged — the scan vision prompt is deliberately untouched (spec Out of Scope: measuring, not improving). | ✅ |
| VII(c). Read-only mechanics | Engaged in spirit: the harness declares Discogs read-only and the plan documents the enforcement mechanics (no write-method references in `eval/`, AST/grep guard test — research R6). | ✅ |
| Secrets | Token stays in the auth header via the existing client; no new `get_secret_value` sites (static audit count unchanged at 3). Manifest stores image URIs (possibly signed) only inside gitignored `data/`. | ✅ |
| Workflow gates | Spec → plan → tasks → implement, committed per phase; tests offline; component README updated. | ✅ |

**Post-design re-check** (after Phase 1): no new violations; no Complexity
Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/023-scan-eval-harness/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0 — decisions R1–R10
├── data-model.md        # Phase 1 — entities + settings fields
├── quickstart.md        # Phase 1 — owner runbook incl. live validation
├── checklists/requirements.md
├── contracts/
│   ├── eval-dataset.md                          # dataset dir + manifest + retention layout
│   ├── eval-results.md                          # results JSONL + summary schema
│   └── amendment-017-discogs-consumption-2.md   # +images[] fields, +image binary GET
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── settings.py                # +5 fields (eval dirs/cap, retention flag/dir)
│   ├── cli.py                     # +eval-dataset, +eval-run subcommands
│   ├── discogs/client.py          # +download_image(uri) via the governed _request path
│   ├── scan/
│   │   ├── retention.py           # NEW — PhotoRetainer (save/rename, loud-warn on failure)
│   │   └── server.py              # retention hook in POST /api/scan (flag-gated)
│   └── eval/                      # NEW package (owner-run, imported only by cli.py)
│       ├── __init__.py
│       ├── dataset.py             # builder: snapshot → images[] → downloads + manifest
│       ├── sources.py             # manifest reader + retention/journal ground-truth join
│       ├── harness.py             # run loop: image → extract_evidence → find_candidates
│       └── scoring.py             # pure: per-image scoring + summary math (sum invariants)
└── tests/
    ├── unit/
    │   ├── test_eval_dataset.py        # selection, resume, manifest integrity (FakeDiscogsClient)
    │   ├── test_eval_sources.py        # manifest read, journal join, unlabeled rules
    │   ├── test_eval_scoring.py        # hit/rank/rung scoring + summary sum invariants
    │   ├── test_eval_readonly_guard.py # AST guard: no write-method refs in eval/
    │   ├── test_eval_gitignore_guard.py# data/ ignore rule + defaults under data/eval/
    │   └── test_scan_retention.py      # flag off = no writes; on = save/rename; failure loud+non-fatal
    └── integration/
        ├── test_scan_server.py         # +retention-through-endpoint cases
        └── test_eval_harness.py        # full run over tmp dataset, stubbed LLM + FakeDiscogsClient
```

**Structure Decision**: grow the existing `collection-agent` package with one new
`eval/` subpackage plus a `scan/retention.py` module; expose both new operations
as CLI subcommands on the existing `python -m collection_agent` entry point
(017's CLI-surface decision; "CLI as the source of truth" analog). No new
component, no new dependency manifest.

## Complexity Tracking

No constitution violations to justify.
