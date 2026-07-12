# Amendment 2 (025) to Contract: Eval Run Results & Summary (023)

023's `contracts/eval-results.md` and 024's first amendment stay
authoritative; 025 adds a **replay mode** to the same contracted surface.
Everything is additive: camera-run output is byte-identical to 024, and
023/024-format files remain valid inputs for every reader (including the
replay mode itself, subject to §4's replayability rule).

## Delta 1 — CLI: replay invocation

```text
python -m collection_agent eval-run --replay <run_id> [--limit N]
```

- `<run_id>` names an existing run directory under
  `COLLECTION_AGENT_EVAL_RESULTS_DIR` (the id 023 prints and uses as the
  directory name). The replay's input is that run's `results.jsonl` ONLY
  — images, dataset, journals, and the source run's `summary.json` are
  not required (an interrupted source run with results but no summary is
  replayable).
- `--replay` and an explicit `--source` are mutually exclusive — naming
  both is a configuration error (`EXIT_CONFIG`), never a precedence rule.
  `--limit N` applies to the replayed record list exactly as it applies
  to an image source (sets `limited`).
- Replay makes **zero vision/LLM calls** and does not require
  `OPENAI_API_KEY`. It performs live Discogs `/database/search` reads
  through the existing governed client, identically to a camera run.
- Fail-fast (`EXIT_CONFIG`, no run directory left behind): source run
  directory missing, `results.jsonl` missing/empty/unreadable, or zero
  records carrying `evidence` (e.g. a pre-024 run). A torn/JSON-invalid
  trailing line is tolerated (skipped); complete records are used.
- Exit codes otherwise unchanged: `0` completed (per-record errors are
  data), `1` unexpected, `2` configuration.

## Delta 2 — §1 run layout: replay run id

A replay writes a standard run directory:
`<COLLECTION_AGENT_EVAL_RESULTS_DIR>/<YYYYMMDD-HHMMSSZ-replay>/` with the
same `results.jsonl` (incremental, fsync'd per line) and `summary.json`.
The replay never writes to — or otherwise modifies — the source run's
directory (read-only input; §4 of the base contract extends to it).
Replays are themselves replayable (their records carry `evidence`).

## Delta 3 — §2 result record: new field + replay semantics

| Field | Rule |
|---|---|
| `replayed` | boolean; present on **every** record of a replay run, absent otherwise. `true` = the production search ladder was re-run over the record's recorded evidence; `false` = the record was carried through without search work. |

Replay record semantics:

- **Replayable source records** (those carrying `evidence` — including
  original post-vision `discogs_error` records): the evidence dict is
  re-materialized through the production evidence model (current
  normalization deliberately applies — this is how normalization changes
  are A/B-ed) and run through the unmodified production ladder. Outcome
  is scored fresh against the record's own `truth_release_id`: `hit` /
  `miss` (with `miss_master_relation` recomputed per Delta 4 of the 024
  amendment over the FRESH candidates), or `error`/`discogs_error` if
  the fresh search fails. The record's `evidence` field carries the
  post-re-materialization dump (a normalization-gated value is absent);
  `image`, `source`, `truth_release_id` are copied verbatim.
- **Non-replayable source records** (no `evidence`): carried through
  exactly once each, preserving the original outcome category —
  `unlabeled` → `unlabeled`; `no_evidence` → `no_evidence`; `error`
  without evidence → `error` with the original `error_kind` and a
  `detail` noting the carry-through. Defensive case: a `hit`/`miss`
  record without `evidence` (impossible in a well-formed 024 run,
  invariant 10) is carried through under its original category with an
  explanatory `detail` — never silently re-scored.
- All replay records: `vision_calls = 0`; `elapsed_s` measures search
  only (`0.0` when carried through).

## Delta 4 — §3 summary: new field

| Field | Rule |
|---|---|
| `replay_of` | source run id (string); present iff the run is a replay. Default absent — 023/024 summaries stay valid. |

Under replay: `run_id` ends `-replay`; `source` is the source records'
(homogeneous) source; `dataset_snapshot_completeness` is `null` (that
field describes the dataset state at camera-eval time — follow
`replay_of` to the source run for it); `vision_calls` is `0`; `limited`
as usual. All existing rate definitions (strict, top-1, practical) and
their denominators are unchanged.

## Delta 5 — §3 invariants 11–14 (normative, unit-tested)

11. In a replay run, `vision_calls == 0` in the summary and on every
    record.
12. `replay_of` is present iff every record carries `replayed`;
    `replayed` never appears in a non-replay run.
13. Denominator parity (relational): an unlimited replay yields exactly
    one record per complete source record, with the same `image` names —
    so `images_total` equals the source run's complete-record count and
    every rate is directly comparable between the two runs.
14. `replayed == false` records contribute only to
    `no_evidence`/`errors`/`unlabeled` (plus the flagged defensive
    carry-through of Delta 3, which keeps its original category);
    `hits` and top-1 counts come only from `replayed == true` records.

Invariants 1–10 hold unchanged for replay runs.

## Delta 6 — §4 read-only guarantee: unchanged and extended

The eval package's structural read-only guard (no Discogs writes, no
`scan.journal`/`scan.session` imports) automatically covers the replay
module (the guard sweeps the whole `eval/` package). Additionally
normative: replay treats the source run directory as read-only input.
