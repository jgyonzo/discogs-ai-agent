# Quickstart: Evidence-Replay Eval Mode + Barcode Plausibility Gate (025)

All commands from `collection-agent/` unless noted. Nothing here makes a
vision/LLM call; replays make governed read-only Discogs search requests
(~2–4 min for the 94-image dataset). `OPENAI_API_KEY` is NOT needed for
replays.

## Offline verification (no API calls)

```bash
cd collection-agent && uv run pytest
```

Expected: full suite green (450 pre-025 tests + 025's new tests), no
network.

## Replay a prior run

```bash
# the 2026-07-11 post-024 measured run
uv run python -m collection_agent eval-run --replay 20260711-222805Z-discogs
```

Prints the standard eval summary table plus replay provenance (`replay of
20260711-222805Z-discogs`, `billable vision calls 0`) and the new run
dir: `data/eval/runs/<YYYYMMDD-HHMMSSZ-replay>/`.

Errors you can expect: unknown run id, empty results file, or a pre-024
run without recorded evidence → clear message, exit 2, no run dir
created. `--replay` + `--source` together → exit 2.

## Diff two runs per image (the A/B instrument)

```bash
A=data/eval/runs/20260711-222805Z-discogs/results.jsonl
B=data/eval/runs/<replay_run_id>/results.jsonl
join -j1 <(jq -r '[.image,.outcome,.rung // "-"]|@tsv' $A | sort) \
         <(jq -r '[.image,.outcome,.rung // "-"]|@tsv' $B | sort) \
  | awk '$2" "$3 != $4" "$5'
```

Every line is an image whose outcome/rung changed between the runs. In a
replay-vs-source diff, evidence is identical by construction — changes
are attributable to ladder/normalization changes (or rare remote catalog
drift), never vision.

## Owner live-validation checklist (SC-001..SC-006)

- [x] **SC-001 — determinism**: run the replay command twice
  back-to-back; the per-image diff of the two replay runs (jq recipe
  above) is empty.
  **Validated 2026-07-12 (owner runs `20260712-001333Z-replay` and
  `20260712-001920Z-replay`, both replaying
  `20260711-222805Z-discogs`)**: the per-image outcome/rung diff is
  empty, and a stricter full-record comparison (every field except
  `elapsed_s`, including `rank`, `candidate_ids`, `evidence`, and
  `miss_master_relation`) is byte-identical across all 94 records —
  zero catalog drift between the runs, 100% determinism.
- [x] **SC-002 — barcode gate measured**: in the replay-vs-source diff of
  `20260711-222805Z-discogs`, `17859_secondary1.jpeg` (Cybotron) flips
  miss→hit via the `catno` rung; every other flipped image either has a
  sub-8-digit `evidence.barcode` in the source record or is explainable
  as catalog drift (check: `jq 'select(.evidence.barcode != null and
  (.evidence.barcode|length) < 8) | .image' $A` lists the gate-affected
  population).
  **Validated 2026-07-12 (owner replay `20260712-001333Z-replay`)**: the
  per-image diff contains exactly ONE line —
  `17859_secondary1.jpeg  miss barcode → hit catno`. The gate-population
  audit lists exactly that one image; zero drift, zero other changes
  across the remaining 93 records. Catno-rung hits 17 → 18 (the flip),
  strict 52.1% → 53.2%, practical 56.4% → 57.4%, miss split
  4 same-master / 16 different / 14 unknown (the converted miss came out
  of `different`). One recorded implausible barcode ⇒ exactly one
  outcome change — the instrument and the fix, both working as
  contracted.
- [x] **SC-003 — zero vision cost + latency**: the replay `summary.json`
  has `"vision_calls": 0`; wall time under 5 minutes.
  **Validated 2026-07-12**: `"vision_calls": 0` on the summary and every
  record; summed search `elapsed_s` ≈ 89 s for 94 records — well under
  the 5-minute bound (R8's arithmetic held).
- [x] **SC-004 — denominator parity**: replay summary's `images_total`,
  `evaluated`, `no_evidence`, `unlabeled` (and `errors` unless a live
  search failed during the replay) match the source run's summary, so the
  strict/top-1/practical rates are directly comparable.
  **Validated 2026-07-12**: 94/94 `images_total`, 94/94 `evaluated`,
  10/10 `no_evidence`, 0/0 `errors`, 0/0 `unlabeled` — exact parity;
  invariants 8–14 all hold on the replay summary
  (`replay_of: 20260711-222805Z-discogs`).
- [x] **SC-005 — no scan regression**: one physical scan session
  (phone page) on a record with a real (8+ digit) barcode behaves exactly
  as before — barcode rung fires, dup overlay/add flow unchanged.
  **Validated 2026-07-12 (owner physical scan)**: real-barcode record
  identified via the barcode rung; scan flow unchanged — the gate is
  invisible to plausible barcodes, as contracted.
- [x] **SC-006 — 024 quickstart note**: `specs/024-scan-accuracy-followups/
  quickstart.md` SC-002 now records the 2026-07-11 inconclusive-aggregate
  reading (catno hits 17 vs 20; all target conversions confirmed) and
  points at this feature's replay mode.
  **Validated 2026-07-12 (owner read-through)**: the note reads as an
  honest, self-contained record. Full checklist SC-001..SC-006 complete —
  live validation of 025 closed same-week as merge, with the replay
  instrument itself producing the SC-002 evidence.

## What replay does / does not hold constant

Holds constant: the extracted evidence per image (the recorded values),
the truth labels, the record set. Re-runs live: evidence normalization
(current code — deliberately, so normalization changes like the 025 gate
are measurable) and Discogs `/database/search` (the remote catalog can
drift between runs; back-to-back replays minimize it). A replay is an
eval run: its own results are replayable in turn.
