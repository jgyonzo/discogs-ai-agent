# Data Model: Scan Accuracy Follow-ups (024)

Field-level deltas only — every 023 entity survives unchanged except as
listed. All additions are optional/additive; 023-format files stay valid.

## Settings (VII(a))

| Field | Env alias | Default | Used by |
|---|---|---|---|
| `scan_catno_search_depth: int` | `COLLECTION_AGENT_SCAN_CATNO_SEARCH_DEPTH` | `50` | catno rung fetch depth (`per_page = max(depth, scan_candidates_max)`); catno rung only |

## `scan/models.py::Candidate` (delta)

| Field | Type | Rule |
|---|---|---|
| `master_id` | `int \| None` (NEW) | verbatim from the search result's `master_id`; absent/0 stays `None` — never constructed (019 discipline). Additive on the scan API wire (amendment-022-scan-api). |

## `scan/search.py` (behavioral, no model)

- `normalize_catno(s: str) -> str`: strip spaces/hyphens/dots/slashes/
  underscores, casefold.
- Exact match: any comma-separated part of a result's `catno` string
  normalizes equal to the normalized searched catno. No catno ⇒ never exact.
- Catno rung only: fetch `per_page = max(scan_catno_search_depth,
  scan_candidates_max)`; stable partition (exact first) on raw results;
  then existing dedup + cap + verbatim Candidate build. `more_matches` =
  true total (`pagination.items`) > served count (unchanged formula).

## `eval/dataset.py::ManifestRelease` (delta)

| Field | Type | Rule |
|---|---|---|
| `master_id` | `int \| None` (NEW) | truth release's master id from the release payload; `0`/absent ⇒ `None` ("no master") |

**New reader rule (normative, shared by resume + sources)**: when a
release_id has multiple `release` lines, the NEWEST (last) line is
authoritative — for status, images, and `master_id`. (Formalizes 023's
failed→retried duplicate-line case; backfill relies on it.)

**Backfill mode** (`eval-dataset --backfill-masters`): for each done release
whose newest line lacks `master_id`: `get_release` → append a copy of the
newest line with `master_id` set (images preserved verbatim, `fetched_at`
refreshed). 404/failure ⇒ counted, skipped, old line stays. No image
downloads; normal-build stats extended with `backfilled` / `backfill_failed`.

## `eval/scoring.py` (deltas)

### `EvalItem`

| Field | Type | Rule |
|---|---|---|
| `truth_master_id` | `int \| None` (NEW) | from the manifest's newest line (discogs source); always `None` for retained source (FR-014) |

### `EvalResult`

| Field | Type | Rule |
|---|---|---|
| `evidence` | `dict \| None` (NEW) | `ScanEvidence.compact_dump()` — journal's FR-021 shape; present iff a vision call produced evidence; empty extraction ⇒ omitted; `unlabeled` ⇒ absent |
| `miss_master_relation` | `Literal["same_master", "different", "unknown"] \| None` (NEW) | set iff `outcome == "miss"`: `same_master` (truth master known ∧ any candidate master equals), `different` (truth master known ∧ ≥1 candidate master present ∧ none equal), `unknown` (truth master unknown ∨ no candidate masters — incl. zero candidates) |

### `EvalSummary`

| Field | Type | Rule |
|---|---|---|
| `misses_same_master` | `int` (NEW) | miss bucket counts; **invariant 8**: the three sum to `misses` |
| `misses_different` | `int` (NEW) | |
| `misses_master_unknown` | `int` (NEW) | |
| `practical_rate` | `float \| None` (NEW) | `(hits + misses_same_master) / (hits + misses + no_evidence)` — same denominator as the strict rate; `None` when denominator 0. **Invariant 9**: `practical_rate ≥ identification_rate`, equal iff `misses_same_master == 0` |

**Invariant 10**: every result with `vision_calls ≥ 1` and non-empty
extraction carries `evidence`.

Strict `identification_rate` / `top1_rate`: definitions unchanged (SC-005).

## `eval/sources.py` (behavioral)

- Discogs source consumes the newest release line per release_id (dedup) and
  threads `truth_master_id` onto each `EvalItem`.
- Retained source: `truth_master_id=None` always.

## Compatibility matrix

| Artifact | 023 file read by 024 code | 024 file read by 023 code |
|---|---|---|
| `manifest.jsonl` | ✅ `master_id` defaults `None` → misses classify `unknown` | ✅ extra key ignored by pydantic `extra="ignore"`-style validation (models tolerate unknown keys) |
| `results.jsonl` | ✅ absent new fields tolerated | ✅ additive keys |
| scan API `Candidate` | n/a | additive `master_id` field; page ignores unknown keys |
