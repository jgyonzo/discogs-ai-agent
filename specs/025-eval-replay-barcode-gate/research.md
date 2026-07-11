# Research: Evidence-Replay Eval Mode + Barcode Plausibility Gate (025)

All unknowns from the plan's Technical Context resolved. No new
dependencies anywhere below; every decision reuses an existing seam.

## R1 — Replay input: the source run's `results.jsonl` is sufficient and is the ground truth

**Decision**: replay consumes exactly one input, the prior run's
`results.jsonl`, parsed line-by-line with the same tolerance the manifest
reader established (023): a torn trailing line is skipped, every complete
line is used. The source run's `summary.json` is NOT required — an
interrupted source run (results but no summary) is still replayable,
which mirrors 023's "the manifest, not the filename, is ground truth"
posture: the per-record lines are the record of what happened.

Per 024's amendment (verified in `eval/scoring.py::EvalResult` and
`harness.py::evaluate_item`), each line carries everything replay needs:

| Field | Replay use |
|---|---|
| `image` | copied verbatim to the replay record (join key for diffing) |
| `source` | copied verbatim (`discogs`/`retained` — still the image's provenance) |
| `truth_release_id` | scoring truth; `None` ⇒ unlabeled carry-through |
| `outcome`, `error_kind` | carry-through category for non-replayable records |
| `evidence` | present iff a vision call produced non-empty values (invariant 10), **including post-vision `discogs_error` records** — the replayability predicate |

**Rationale**: zero coupling to images, dataset, or journals keeps replay
cheap, honest (it can never accidentally re-extract), and usable on any
machine that has the run dir.

**Alternatives considered**: (a) re-derive truth from the dataset
manifest — rejected: breaks for retained-source runs (labels come from
journals) and for records whose manifest lines changed since; the run's
own records are what that run measured. (b) Require `summary.json` for
metadata — rejected: excludes interrupted runs for no benefit.

## R2 — Evidence re-materialization goes through `ScanEvidence(**evidence)` — current normalization deliberately applies

**Decision**: each recorded `evidence` dict is re-materialized as
`ScanEvidence(**evidence)` (verified: `compact_dump()` keys are exactly
the model's field names with empties omitted, so the dict round-trips
through the constructor), then fed to the unmodified
`find_candidates(...)`. Construction re-runs ALL current validators —
including 022's FR-019 reclassification and 025's new plausibility gate.

**Rationale**: this is the point of the instrument. "The current search
ladder" includes current evidence normalization: replaying the 2026-07-11
run under 025 is precisely how the barcode gate is measured (the recorded
`"barcode": "3070"` is cleared at construction, the catno rung fires).
For unchanged rules re-validation is idempotent (recorded values are
already post-normalization outputs of the same validators).

**Alternatives considered**: bypassing validation
(`model_construct`) to replay "raw" recorded values — rejected: it would
measure a pipeline that doesn't exist in production and would make
normalization changes invisible to the instrument.

## R3 — Carry-through mapping for non-replayable records

**Decision**: every source record yields exactly one replay record
(denominator parity, spec FR-003). Partition by the `evidence` field:

| Source record | Replay record |
|---|---|
| `evidence` present (orig. hit / miss / post-vision `discogs_error`) | **replayed**: ladder re-runs, scored fresh against `truth_release_id`; a fresh search failure is that replay's own `error`/`discogs_error` |
| `outcome == "unlabeled"` | carried through: `unlabeled` |
| `outcome == "no_evidence"` | carried through: `no_evidence` (deterministic — the recorded extraction was empty) |
| `outcome == "error"` without `evidence` (vision-stage error) | carried through: `error` with the original `error_kind`, detail noting it was carried from the source run |
| `outcome ∈ {hit, miss}` without `evidence` (defensive; can't occur in a well-formed 024 run per invariant 10) | carried through with original outcome category, flagged in detail — never silently re-scored |

All records get `vision_calls=0`; carried-through records get
`elapsed_s=0.0` and empty candidate/rung fields. A new per-record boolean
`replayed` (present only in replay runs: `true` = ladder re-ran, `false`
= carried through) makes the partition machine-readable for diff tooling.

**Rationale**: comparability requires both runs to cover the same record
set; honesty requires never manufacturing an outcome for evidence that
was never extracted (spec US1 scenario 4).

**Alternatives considered**: dropping non-replayable records — rejected:
denominators diverge and rates stop being comparable. Copying original
hit/miss outcomes into the replay for evidence-less records — rejected
for the defensive case: a copied score is not a measurement; flag it
instead.

## R4 — Provenance & output shape: standard run dir, `-replay` run-id suffix, `replay_of` summary field

**Decision**: a replay writes a standard run dir
(`<results_dir>/<YYYYMMDD-HHMMSSZ-replay>/` with incremental fsync'd
`results.jsonl` + `summary.json`), reusing `harness.py`'s existing
run-dir/write/summarize plumbing. New additive fields:

- `EvalSummary.replay_of: str | None = None` — the source run's id
  (present iff replay). `EvalSummary.source` stays the records' source
  (`discogs`/`retained`), derived from the source records (homogeneous
  per run); `run_id` ends in `-replay`.
- `EvalResult.replayed: bool | None = None` — per R3.
- `dataset_snapshot_completeness` is `None` for replays (that field
  describes the dataset build state at *camera-eval* time; the replay's
  provenance chain points at the source run for it).

023-format and 024-format files stay readable (all new fields default);
existing readers of replay output see a valid 023/024-shape file.

**Rationale**: one output shape for all runs keeps every existing tool
(and 025's own diffing) working across camera runs and replays; the
explicit `replay_of` satisfies Principle III's input-provenance analog.

**Alternatives considered**: a separate `replays/` tree or new file
format — rejected: needless divergence; a replay IS an eval run.

## R5 — Truth master resolution: re-resolve from the local dataset manifest when available, else `unknown`

**Decision**: replay recomputes `miss_master_relation` with the same pure
function (`scoring.classify_miss_master`) over the FRESH candidate list.
Truth master ids are re-resolved locally: for `discogs`-source records,
`truth_release_id` → `master_id` via the existing manifest reader
(`dataset.load_manifest` + `newest_release_lines`, newest-line-wins) when
the manifest exists; manifest absent/unreadable ⇒ truth master `None` ⇒
bucket `unknown` (never guessed, never fetched — 024 FR-012 discipline).
`retained`-source records stay `None` (023/024 FR-014 rule).

**Rationale**: the relation depends on the NEW candidates, so it cannot
be copied from the source record; the manifest is the same local ground
truth the camera eval uses, and consulting it costs zero network.

**Alternatives considered**: recording `truth_master_id` into result
records now so future replays never need the manifest — rejected for
this feature: it doesn't help replaying *existing* runs (they lack the
field) and widens the record contract for a value the manifest already
holds locally; can be revisited if the manifest ever stops being local.

## R6 — CLI shape: `eval-run --replay <run_id>`, exclusion with `--source`, no OpenAI key needed

**Decision**: extend the existing `eval-run` subcommand (no new
subcommand): `--replay RUN_ID` names a run dir under
`settings.eval_results_dir` (the id as printed/directory name). To
enforce the spec's "configuration error, not silent precedence" rule with
argparse defaults in play, `--source`'s default changes to `None` and is
resolved to `"discogs"` only when `--replay` is absent; passing both
explicitly is an `EXIT_CONFIG` error. `--limit N` applies to replay
identically (truncates the record list, sets `limited`). In replay mode
the `OPENAI_API_KEY` presence gate is skipped and `_build_llm_client` is
never called — replay must work vision-free by construction (spec
FR-001), which also means no LangSmith tracing spans (nothing traced is
called). Missing/empty/evidence-free source runs map to `SourceError` →
`EXIT_CONFIG` (existing convention), before any run dir is created.

**Rationale**: one subcommand keeps the eval surface small; the
default-resolution trick is the minimal way to detect "both named"; the
key-gate skip is what makes replay runnable in CI-like or key-less
contexts later without widening scope now.

**Alternatives considered**: `--source replay:<id>` — rejected: overloads
a value enum with a parameterized form; separate `eval-replay` subcommand
— rejected: duplicates limit/summary/exit-code plumbing for no user gain.

## R7 — Barcode gate: threshold 8, drop-don't-reclassify, ordered after FR-019, domain constant

**Decision**: in `scan/models.py`, new constant
`BARCODE_PLAUSIBLE_MIN_DIGITS = 8` and a gate that clears
`ScanEvidence.barcode` when its digit count (the field is already
digits-only after the existing `_normalize_barcode` field validator) is
1–7. Ordering: the gate runs AFTER the FR-019 catno→barcode
reclassification model validator (pydantic v2 runs `model_validator`s in
definition order), so:

- a reclassified catno (by construction ≥ 10 digits) is never gated
  (spec FR-011 composition requirement is satisfied structurally);
- a vision-supplied short "barcode" is cleared regardless of other fields;
- the cleared value is NOT moved to `catno` — asymmetric with FR-019 by
  design: a 10+-digit run is *definitively* a barcode, but a short digit
  run is not definitively a catno, and injecting it could hijack the
  catno rung exactly the way the fake barcode hijacked the barcode rung
  (spec assumption, motivating case `3070` vs true catno `D-216`).

Threshold 8 = shortest real retail forms (UPC-E, EAN-8); no upper bound
(EAN add-ons legitimately reach 15/18 digits; the long direction is
FR-019's job). Constant, not a Settings field — same VII(a) posture as
the sanctioned `BARCODE_MIN_DIGITS = 10` precedent: barcode formats don't
vary by deployment, and a knob would invite silently divergent evals.
Downstream (`evidence_kinds`, `is_empty`, journal/eval `evidence` dumps)
reflects the post-gate value with zero extra code — all are derived from
the fields at read time (verified in `models.py`).

**Rationale**: single normalization site (the phone page's
`server.py` and both eval paths all construct `ScanEvidence`), zero
behavior change for plausible barcodes, and the fix is replay-measurable
(R2).

**Alternatives considered**: gating inside `search.py`'s barcode rung —
rejected: the journal/eval `evidence` dumps would keep advertising a
barcode the ladder ignores ("ghost rung", violates spec FR-012). Prompt
hardening — out of scope by owner decision (vision prompt frozen).

## R8 — Replay latency & rate-limit envelope

**Decision**: no new throttling. Replay issues only `/database/search`
reads through the existing governed `DiscogsClient` (60 req/min
authenticated, header-driven governor). The 94-record dataset averages
~1–2 rungs/record (most records carry barcode or catno evidence, and the
catno rung's deeper page is still one request — 024), so a full replay is
~100–190 requests ≈ 2–4 minutes; SC-003's 5-minute bound holds with
headroom. Carried-through records cost zero requests.

**Rationale**: measured request arithmetic, existing governor; nothing to
build.

**Alternatives considered**: caching/recording search responses for
fully-offline replay — rejected for 025: it would freeze the remote
catalog into a fixture and stop measuring the live substring-matching
behavior the ladder actually contends with (the 024 drowning bug lived
exactly there); recorded-response replay is a possible future feature
with its own honesty caveats.
