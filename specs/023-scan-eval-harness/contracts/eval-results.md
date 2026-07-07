# Contract: Eval Run Results & Summary (023)

Output shape of `python -m collection_agent eval-run`. Owner-facing and
consumed by future features (e.g. comparing runs after a prompt change), so
the shape is contracted.

## 1. Run layout

```text
<COLLECTION_AGENT_EVAL_RESULTS_DIR>/            # default collection-agent/data/eval/runs/
└── <run_id>/                                   # YYYYMMDD-HHMMSSZ-<source>, e.g. 20260707-190001Z-discogs
    ├── results.jsonl                           # one line per image, appended as evaluated
    └── summary.json                            # written once at run end
```

- One directory per invocation — concurrent/back-to-back runs never share
  files (spec edge case).
- `results.jsonl` is appended incrementally with flush per line: a crashed or
  interrupted run keeps every completed result.
- The harness never writes outside its own run directory (journals, snapshot,
  dataset, and retention dirs are read-only to it).

## 2. `results.jsonl` record

```json
{"image": "724223_secondary1.jpg", "source": "discogs",
 "truth_release_id": 724223, "outcome": "hit", "rank": 1,
 "rung": "barcode", "rungs_tried": ["barcode"],
 "evidence_kinds": ["barcode", "artist_title"],
 "candidate_ids": [724223, 297060],
 "vision_calls": 1, "elapsed_s": 2.4}
```

Serialization note: records are written with `exclude_none` — absent/None
fields (`rank` on a miss, `error_kind` outside errors, …) are omitted from
the line rather than serialized as `null`.

Field semantics (full typing in data-model.md):

| Field | Rule |
|---|---|
| `outcome` | `hit` · `miss` · `no_evidence` · `error` · `unlabeled` |
| `rank` | 1-based position of `truth_release_id` in `candidate_ids`; present iff `hit` |
| `rung` | last element of `rungs_tried` when candidates were returned (the rung that produced them); `null` otherwise |
| `rungs_tried` | verbatim from the production ladder (`find_candidates`), same meaning as the journal's `evidence_kinds` after 022 addendum 1 |
| `evidence_kinds` | what the vision step extracted (pre-ladder), for vision-vs-ladder attribution |
| `error_kind` | `vision_error` (extraction failed/timed out) or `discogs_error` (search failed); present iff `error` |
| `vision_calls` | billable calls made for this image; `0` for `unlabeled` (unlabeled images are never evaluated) |

## 3. `summary.json`

```json
{"run_id": "20260707-190001Z-discogs", "source": "discogs",
 "images_total": 200, "evaluated": 197,
 "hits": 151, "misses": 38, "no_evidence": 8, "errors": 3, "unlabeled": 0,
 "identification_rate": 0.766, "top1_rate": 0.641,
 "hits_by_rung": {"barcode": 88, "catno": 31, "artist_title": 24, "text": 8},
 "errors_by_kind": {"vision_error": 2, "discogs_error": 1},
 "vision_calls": 197, "limited": true,
 "dataset_snapshot_completeness": "complete"}
```

**Normative invariants** (unit-tested; spec FR-014 / SC-002):

1. `hits + misses + no_evidence + errors + unlabeled == images_total`
2. `evaluated == hits + misses + no_evidence + errors`
3. `identification_rate == hits / (hits + misses + no_evidence)` — errors are
   excluded from the denominator (provider unavailability is not a pipeline
   miss) but always reported beside it; `null` when the denominator is 0
4. `top1_rate` uses the same denominator, counting only `rank == 1` hits
5. `sum(hits_by_rung.values()) == hits`; `sum(errors_by_kind.values()) == errors`
6. `limited` is `true` iff `--limit` truncated the source
7. `unlabeled > 0` only for `source == "retained"`

## 4. Read-only guarantee (normative)

An eval run performs **zero** Discogs write calls. Enforced structurally: the
`eval/` package MUST NOT reference `add_to_collection`, `create_folder`, or
`move_instance`, and MUST NOT import `scan.journal` or `scan.session` (no
journal writes, no allowlist). Guard test:
`tests/unit/test_eval_readonly_guard.py`.

## 5. CLI exit codes

Existing component conventions: `0` run completed (even with per-image errors
— they're data, not process failure) · `1` unexpected error · `2`
configuration error (missing snapshot/dataset/keys, unknown `--source`).
An empty source ("nothing to evaluate") is a clear message + exit `2`.
