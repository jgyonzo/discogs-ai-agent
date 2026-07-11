# Data Model: Evidence-Replay Eval Mode + Barcode Plausibility Gate (025)

All changes are additive to 023/024 shapes; no schema breaks, no new
Settings fields, no new files formats. Full field semantics in
`contracts/amendment-023-eval-results-2.md` and
`contracts/amendment-022-scan-api-2.md`.

## 1. Source run record (input; existing shape, read-only)

One parsed line of a prior run's `results.jsonl` (023 §2 + 024 delta 1).
Replay never modifies it. Fields consumed:

| Field | Type | Replay role |
|---|---|---|
| `image` | str | copied verbatim; per-image diff join key |
| `source` | `discogs` \| `retained` | copied verbatim; also drives truth-master policy (R5) |
| `truth_release_id` | int \| absent | scoring truth; absent/None ⇒ unlabeled carry-through |
| `outcome` | 023 taxonomy | carry-through category when not replayable |
| `error_kind` | str \| absent | preserved on carried-through errors |
| `evidence` | dict \| absent | **replayability predicate** + ladder input (via `ScanEvidence(**evidence)`) |

Parsing rules: JSONL, one record per line; blank lines skipped; a torn /
JSON-invalid **trailing** line is tolerated (skipped) — same posture as
the 023 manifest reader. Unknown fields ignored (forward-compatible).

**Replayable** iff `evidence` is present and non-empty. A run with zero
replayable records is not a replay input (fail-fast, `EXIT_CONFIG`).

## 2. `ReplayItem` (new, internal — `eval/replay.py`)

The replay analog of `EvalItem`: one unit of replay work.

| Field | Type | Notes |
|---|---|---|
| `image` | str | from source record |
| `source` | `discogs` \| `retained` | from source record |
| `truth_release_id` | int \| None | from source record |
| `truth_master_id` | int \| None | re-resolved via manifest (R5); always None for `retained` |
| `evidence` | dict \| None | recorded compact dump; None ⇒ carry-through |
| `carry_outcome` | outcome \| None | set iff not replayable: the outcome category to carry |
| `carry_error_kind` | str \| None | preserved original `error_kind` for carried errors |

Validation: `evidence` and `carry_outcome` are mutually exclusive and
exactly one is set (the partition of R3).

## 3. `EvalResult` (extended — `eval/scoring.py`)

New optional field; everything else unchanged, `exclude_none`
serialization keeps camera-run records byte-identical to 024.

| Field | Type | Rule |
|---|---|---|
| `replayed` | bool \| None | present on **every** record of a replay run (`true` = ladder re-ran, `false` = carried through); absent on camera runs |

Replay-run field rules (per record):

- `vision_calls == 0` always; `elapsed_s` measures search only (0.0 when
  carried through).
- replayed records: `outcome ∈ {hit, miss}` scored fresh, or `error` with
  `error_kind="discogs_error"` if the fresh search fails; `evidence` =
  the **post-re-materialization** compact dump (reflects current
  normalization, e.g. a gated barcode is absent); `evidence_kinds`,
  `rungs_tried`, `rung`, `rank`, `candidate_ids`, `miss_master_relation`
  as in a camera run.
- carried-through records: original outcome category preserved
  (`unlabeled` / `no_evidence` / `error`+original kind, plus the
  defensive hit/miss-without-evidence case flagged via `detail`); no
  candidates, no rungs, no evidence.

## 4. `EvalSummary` (extended — `eval/scoring.py`)

| Field | Type | Rule |
|---|---|---|
| `replay_of` | str \| None = None | source run id; present iff the run is a replay |

Existing fields under replay: `run_id` = `YYYYMMDD-HHMMSSZ-replay`;
`source` = the source records' (homogeneous) source;
`dataset_snapshot_completeness` = None; `vision_calls` = 0; `limited` as
usual. Defaults keep every 023/024 summary readable and vice versa.

**New normative invariants** (11–14, continuing 023's 1–7 and 024's
8–10; unit-tested):

11. In a replay run, `vision_calls == 0` in the summary and on every
    record.
12. `replay_of` is present iff the run is a replay, and iff every record
    carries `replayed`; `replayed` never appears in a camera run.
13. Denominator parity: an unlimited replay has `images_total` equal to
    the source run's complete-record count, one output record per source
    record, same `image` names (relational — verified by tests/diff
    tooling over the pair of runs).
14. Carried-through (`replayed == false`) records contribute only to
    `no_evidence` / `errors` / `unlabeled` counts; `hits + misses` come
    only from `replayed == true` records (with the flagged defensive
    exception of §3, which preserves its original category).

Invariants 1–10 continue to hold unchanged for replay runs.

## 5. `ScanEvidence` (extended — `scan/models.py`)

New domain constant and normalization step (shared by phone page + both
eval modes; state transition below is the full gate):

```text
BARCODE_PLAUSIBLE_MIN_DIGITS = 8   # UPC-E/EAN-8 are the shortest real forms

order of normalization (pydantic v2, definition order):
  1. _normalize_barcode (existing)      barcode := digits only, or None
  2. _blank_to_none     (existing)
  3. _reclassify_barcode_in_catno       catno with 10+ stripped digits
     (existing, FR-019)                 → barcode (≥10 digits by construction)
  4. _gate_implausible_barcode (NEW)    barcode with 1..7 digits → None
                                        (never moved to catno — R7)
```

Invariants: a surviving `barcode` has ≥ 8 digits; a barcode produced by
step 3 is never cleared by step 4; `evidence_kinds`, `is_empty`, and
`compact_dump()` (journal + eval evidence) all reflect the post-gate
state with no further changes (they derive from fields at read time).
Plausible barcodes (≥ 8 digits) and all non-barcode fields are untouched
— byte-identical to 024 behavior.

## 6. Unchanged shapes (explicitly)

- `EvalItem`, `evaluate_item`, `score_search_outcome`,
  `classify_miss_master`, `summarize` math — untouched logic; `summarize`
  only passes through the new summary fields.
- Dataset manifest (023/024), scan journal schema (022), scan API wire
  models, snapshot schema — untouched.
- `Settings` — zero new fields (first eval feature with none).
