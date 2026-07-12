# Implementation Plan: Evidence-Replay Eval Mode + Barcode Plausibility Gate

**Branch**: `025-eval-replay-barcode-gate` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/025-eval-replay-barcode-gate/spec.md`

## Summary

Two follow-ups from the 2026-07-11 post-024 eval run, `collection-agent`
only, zero new dependencies:

1. **Evidence-replay eval mode** (`eval-run --replay <run_id>`): re-run
   ONLY the production search ladder over the evidence values recorded in
   a prior run's `results.jsonl` (the 024 `evidence` field — the journal's
   compact shape — exists for exactly this). Zero vision calls, zero
   OpenAI dependency at replay time; per-image outcomes are scored against
   the replayed records' own recorded truth. This is the instrument the
   2026-07-11 analysis proved missing: ±10/94 images flip on vision
   nondeterminism alone, so single-run strict-rate comparisons cannot
   resolve ladder changes. Implementation: a new `eval/replay.py` (source-
   run reader + carry-through mapping) feeding the existing
   `harness.py`/`scoring.py` scoring and summary paths; new provenance
   fields (`replay_of` on the summary, `replayed` per record) keep replay
   output distinguishable while remaining 023/024-reader compatible.
2. **Barcode plausibility gate**: a sub-8-digit digits-only barcode is not
   a barcode (real UPC-E/EAN-8..EAN-13 are 8–13 digits) — cleared at the
   single shared normalization site, `scan/models.py::ScanEvidence`
   (mirrors 022 FR-019's `BARCODE_MIN_DIGITS` reclassification; new
   `BARCODE_PLAUSIBLE_MIN_DIGITS = 8` domain constant, no settings knob).
   Because replay re-materializes evidence through `ScanEvidence`, the
   gate is itself measurable by replaying the 2026-07-11 run: the Cybotron
   record (`3070` fake barcode suppressing catno `D-216`) converts
   miss→hit with no plausible-barcode record touched.

Plus FR-013: an honest inconclusive-reading note in 024's quickstart
SC-002 item.

## Technical Context

**Language/Version**: Python 3.12 (`collection-agent/pyproject.toml`, `requires-python >=3.12`)
**Primary Dependencies**: existing only — pydantic v2 + pydantic-settings, httpx (Discogs client), rich (CLI); openai/langsmith NOT needed on the replay path. Zero new dependencies.
**Storage**: existing gitignored eval artifacts — run dirs under `COLLECTION_AGENT_EVAL_RESULTS_DIR` (default `collection-agent/data/eval/runs/`), each with fsync'd append-only `results.jsonl` + `summary.json`; dataset manifest at `COLLECTION_AGENT_EVAL_DATASET_DIR` read-only for truth-master resolution
**Testing**: pytest (`cd collection-agent && pytest`), 450 tests green at branch point; no live API calls in tests (`FakeDiscogsClient` scriptable search)
**Target Platform**: owner's laptop (macOS), same CLI entrypoint `python -m collection_agent`
**Project Type**: monorepo component CLI (`collection-agent/`), eval subsystem
**Performance Goals**: a ~94-record replay completes in under 5 minutes under the existing header-driven rate governor (search reads only, ~1–3 requests/image, 60 req/min authenticated); zero vision latency/cost
**Constraints**: replay is structurally read-only (existing AST guard sweeps `eval/` recursively — new module inherits it); never modifies the source run; gate is deterministic normalization with the vision prompt frozen; all 023/024 result/summary invariants keep holding
**Scale/Scope**: dataset currently 94 images / 47 releases; design unchanged up to the 300–1k-record collection target

## Constitution Check

*GATE: evaluated against constitution v1.2.1 before Phase 0; re-checked after Phase 1 design — PASS (no violations, Complexity Tracking empty).*

**Components touched**: `collection-agent` only.

- **I. Layered, contract-first data architecture** — engaged at the
  contract level only: no DuckDB/pipeline layers touched. The two changed
  owner-facing surfaces are already contracted and get amendments in this
  feature (`eval-results` second amendment for replay; `scan-api` second
  amendment for the gate) before implementation. PASS.
- **II. Streaming, bounded-memory** — not engaged (no XML/ETL). Replay
  reads one results.jsonl (~100s of lines) line-by-line; bounded. PASS.
- **III. Reproducible runs, manifest & logs** — the eval analog is
  respected and strengthened: every replay produces its own run dir with
  incremental fsync'd results + summary, and now carries explicit input
  provenance (`replay_of`). Re-running the same replay against the same
  source run and unchanged code yields logically equivalent outputs
  (SC-001) — replay exists precisely to make eval comparisons
  reproducible. PASS.
- **IV. Data quality gates** — the summary sum invariants (023 §3, 024
  invariants 8–10) are the eval's DQ checks; this feature adds replay
  invariants (vision_calls == 0; denominator parity with the source run;
  carried-through/replayed partition sums) with unit tests in the same
  change set. PASS.
- **V. Agent-friendly analytics surface** — not engaged (no analytics
  tables). PASS.
- **VI. Components & contracts** — `collection-agent` only; no
  cross-component imports; no DuckDB consumption change; no new component.
  The live-Discogs consumption shape is unchanged (same `/database/search`
  read path under the same governor — replay makes the same calls the
  camera eval makes, just without vision). PASS.
- **VII. Implementation discipline** —
  - *(a) configuration sources*: no new hardcoded config; the replay run
    id is a CLI argument (per-invocation input, not config);
    `BARCODE_PLAUSIBLE_MIN_DIGITS = 8` is a domain constant following the
    sanctioned `BARCODE_MIN_DIGITS = 10` precedent (barcode formats don't
    vary by deployment — recorded in research R6). Zero new Settings
    fields. PASS.
  - *(b) prompt-authoring*: not engaged — the vision prompt is explicitly
    frozen (spec FR-010). PASS.
  - *(c) read-only mechanics*: replay's read-only posture is inherited
    structurally (AST guard, rglob over `eval/`); the source run dir is
    opened read-only and the replay writes only inside its own new run
    dir (023 §1 rule, restated in the amendment). PASS.
- **Workflow gates** — spec → plan → tasks → analyze → implement, each
  phase committed (single-PR flow per owner decision 2026-07-07). PASS.

## Project Structure

### Documentation (this feature)

```text
specs/025-eval-replay-barcode-gate/
├── spec.md
├── plan.md                              # this file
├── research.md                          # Phase 0
├── data-model.md                        # Phase 1
├── quickstart.md                        # Phase 1 (incl. owner live-validation checklist)
├── checklists/requirements.md
├── contracts/
│   ├── amendment-023-eval-results-2.md  # replay mode: CLI, provenance, carry-through, invariants 11–14
│   └── amendment-022-scan-api-2.md      # barcode plausibility gate in evidence-normalization semantics
└── tasks.md                             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── cli.py                       # eval-run: --replay arg, --source/--replay exclusion,
│   │                                #   replay skips the OPENAI_API_KEY gate, summary print
│   │                                #   gains replay provenance rows
│   ├── eval/
│   │   ├── replay.py                # NEW: source-run reader (torn-line tolerant),
│   │   │                            #   replayability partition, truth-master re-resolution
│   │   ├── harness.py               # run_replay() beside run_eval(); shared run-dir/
│   │   │                            #   results-writing/summarize plumbing
│   │   └── scoring.py               # EvalResult.replayed, EvalSummary.replay_of (+ replay
│   │                                #   summary invariants); scoring math unchanged
│   └── scan/
│       └── models.py                # BARCODE_PLAUSIBLE_MIN_DIGITS = 8; gate model_validator
│                                    #   ordered after the FR-019 reclassification
├── tests/
│   ├── unit/
│   │   ├── test_scan_models.py      # gate: <8 cleared, ==8 kept, composes with FR-019,
│   │   │                            #   gate-only evidence ⇒ is_empty, kinds reflect post-gate
│   │   ├── test_eval_replay.py      # NEW: reader, partition, provenance, invariants,
│   │   │                            #   fail-fast (missing run / no evidence / torn line)
│   │   ├── test_eval_scoring.py     # summary replay fields + invariants 11–14
│   │   └── test_eval_readonly_guard.py  # unchanged — auto-covers eval/replay.py
│   └── integration/
│       └── test_eval_harness.py     # replay end-to-end over a fixture source run w/
│                                    #   FakeDiscogsClient; determinism (two replays identical);
│                                    #   CLI arg-conflict + no-OpenAI-key path
└── (no settings.py change, no new deps, no prompt change)

specs/024-scan-accuracy-followups/quickstart.md   # FR-013 honest SC-002 note
```

**Structure Decision**: grow the existing `eval/` package by one module
(`replay.py`) and extend the two existing seams (`harness.py` run loop,
`scoring.py` models) rather than a parallel harness — replay MUST flow
through the same `find_candidates` + `score_search_outcome` +
`summarize` paths the camera eval uses, or it stops measuring the
production ladder (023 FR-011 discipline). The gate lands in
`scan/models.py` because that is the one shared normalization site both
the phone page and the eval (camera and replay alike) construct
`ScanEvidence` through.

## Complexity Tracking

> No constitution violations — table intentionally empty.
