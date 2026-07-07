# Data Model: Scan Identification Eval Dataset & Harness (023)

Pydantic v2 models in `collection_agent/eval/` (manifest/results) and plain
settings fields. Existing models (`ScanEvidence`, `Candidate`,
`ScanCycleOutcome`, snapshot models) are consumed unchanged.

## New Settings fields (VII(a); all `COLLECTION_AGENT_*`)

| Field | Env alias | Default | Used by |
|---|---|---|---|
| `eval_dataset_dir: Path` | `COLLECTION_AGENT_EVAL_DATASET_DIR` | `<component>/data/eval/discogs-images` | builder, harness (`--source discogs`) |
| `eval_images_per_release: int` | `COLLECTION_AGENT_EVAL_IMAGES_PER_RELEASE` | `2` | builder (secondary-preferred cap; CLI `--images-per-release` overrides per run) |
| `eval_results_dir: Path` | `COLLECTION_AGENT_EVAL_RESULTS_DIR` | `<component>/data/eval/runs` | harness |
| `scan_retain_photos: bool` | `COLLECTION_AGENT_SCAN_RETAIN_PHOTOS` | `False` | scan server (retention hook gate) |
| `scan_retention_dir: Path` | `COLLECTION_AGENT_SCAN_RETENTION_DIR` | `<component>/data/eval/scan-photos` | scan server (writes), harness (`--source retained`) |

All three directory defaults resolve under `collection-agent/data/` — covered
by the repo-root `.gitignore` `data/` rule (guard-tested, research R4).

## Manifest models (`eval/dataset.py`; file schema in `contracts/eval-dataset.md`)

### `ManifestHeader` — one line per build invocation

| Field | Type | Notes |
|---|---|---|
| `type` | `Literal["run_header"]` | line discriminator |
| `built_at` | `str` | UTC `YYYY-MM-DDTHH:MM:SSZ` |
| `snapshot_completeness` | `str` | `complete` / `partial` / `stale` at build time (spec edge case: coverage honesty) |
| `snapshot_synced_at` | `str \| None` | from snapshot meta |
| `images_per_release` | `int` | effective cap for this run |

### `ManifestImage` — nested in `ManifestRelease`

| Field | Type | Notes |
|---|---|---|
| `kind` | `str` | verbatim from `images[].type` — expected `primary`/`secondary`, tolerated as any string (verbatim discipline: never coerced or invented) |
| `source_uri` | `str` | verbatim `images[].uri` (possibly signed; lives only in gitignored data) |
| `file` | `str \| None` | filename relative to dataset dir; `None` when download failed |
| `status` | `str` | `downloaded` \| `failed` |
| `detail` | `str \| None` | failure reason |

### `ManifestRelease` — one line per processed release

| Field | Type | Notes |
|---|---|---|
| `type` | `str` (`"release"`) | line discriminator |
| `release_id` | `int` | **ground truth** for every image in `images` |
| `status` | `str` | `downloaded` (≥1 image on disk) \| `no_images` \| `failed` (release fetch or all downloads failed) |
| `images` | `list[ManifestImage]` | empty for `no_images` |
| `fetched_at` | `str` | UTC timestamp |
| `detail` | `str \| None` | e.g. 404 on release fetch |

**Resume rule** (FR-005): a release is *done* iff a `release` line with status
`downloaded` or `no_images` exists; `failed` releases are retried on the next
run. A torn trailing line is ignored on load.

**Validation**: image filenames are `{release_id}_{kind}{ordinal}.{ext}` for
human browsing only — the manifest, never the filename, is parsed for truth.

## Retention layout (no new journal fields; `contracts/eval-dataset.md` §3)

```text
<scan_retention_dir>/<session_id>/<scan_id>.<ext>     # cycle reached a scan_id
<scan_retention_dir>/<session_id>/pending-<n>.<ext>   # never got one (vision error / superseded)
```

- `session_id` / `scan_id` are 022's existing ids (`YYYYMMDD-HHMMSSZ`,
  `<session_id>-<seq>`); `<ext>` derives from the upload's content type.
- State transitions: `pending-<n>.<ext>` —(scan_id assigned, atomic same-dir
  rename)→ `<scan_id>.<ext>`. No other transitions; files are never deleted or
  rewritten by the component.
- **Label resolution** (FR-010, harness-side, lazy): journal line in
  `<scan_journal_dir>/<session_id>.jsonl` with `scan_id` matching the filename
  and `outcome == "added"` → label = that line's `release_id`. Everything else
  → `unlabeled`.

## Harness models (`eval/scoring.py`; file schema in `contracts/eval-results.md`)

### `EvalItem` — in-memory unit of work (from `eval/sources.py`)

| Field | Type | Notes |
|---|---|---|
| `image_path` | `Path` | |
| `mime` | `str` | from extension |
| `truth_release_id` | `int \| None` | `None` = unlabeled (retained source only) |
| `source` | `Literal["discogs", "retained"]` | |
| `meta` | `dict` | provenance: image kind / session+scan id |

### `EvalResult` — one `results.jsonl` line

| Field | Type | Notes |
|---|---|---|
| `image` | `str` | path relative to the source dir |
| `source` | `Literal["discogs", "retained"]` | |
| `truth_release_id` | `int \| None` | |
| `outcome` | `Literal["hit", "miss", "no_evidence", "error", "unlabeled"]` | taxonomy of research R8 |
| `rank` | `int \| None` | 1-based; set iff `hit` |
| `rung` | `str \| None` | rung that produced the candidate list (last entry of `rungs_tried`); set when candidates returned |
| `rungs_tried` | `list[str]` | verbatim from `find_candidates` |
| `evidence_kinds` | `list[str]` | from `ScanEvidence.evidence_kinds` |
| `candidate_ids` | `list[int]` | returned candidates, in order |
| `error_kind` | `Literal["vision_error", "discogs_error"] \| None` | set iff `error` |
| `detail` | `str \| None` | error message |
| `vision_calls` | `int` | billable calls for this image (0 for `unlabeled` — unlabeled images are skipped, not evaluated) |
| `elapsed_s` | `float` | per-image wall time |

**Invariant**: `outcome == "unlabeled"` ⇒ no vision/search call was made
(cost honesty); `unlabeled` occurs only for the retained source.

### `EvalSummary` — `summary.json`

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | `YYYYMMDD-HHMMSSZ-<source>` |
| `source` | `str` | |
| `images_total` | `int` | items seen in the source (post-limit) |
| `evaluated` | `int` | hit+miss+no_evidence+error |
| `hits`, `misses`, `no_evidence`, `errors`, `unlabeled` | `int` | **sum invariant**: hits+misses+no_evidence+errors+unlabeled == images_total |
| `identification_rate` | `float \| None` | hits / (hits+misses+no_evidence); `None` when denominator 0 |
| `top1_rate` | `float \| None` | rank-1 hits over same denominator |
| `hits_by_rung` | `dict[str, int]` | values sum to `hits` |
| `errors_by_kind` | `dict[str, int]` | values sum to `errors` |
| `vision_calls` | `int` | billable-call total (spec: cost visibility) |
| `limited` | `bool` | `--limit` truncated the source |
| `dataset_snapshot_completeness` | `str \| None` | echoed from the newest manifest header (discogs source) |

Note: `errors` are **excluded** from the identification-rate denominator
(provider unavailability is not a pipeline miss) but always reported beside it.
