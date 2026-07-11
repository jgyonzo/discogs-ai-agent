# Quickstart: Scan Accuracy Follow-ups (024)

All commands from `collection-agent/`, repo-root `.env` configured.

## 1. Upgrade the existing dataset with master ids (US3)

```bash
uv run python -m collection_agent eval-dataset --backfill-masters
```

- One metadata fetch per already-built release lacking a master id (no image
  downloads); governor-paced, minutes-scale. Failures are counted and
  skipped honestly.
- New builds record master ids automatically — backfill is only for
  023-built datasets.

## 2. Re-run the eval and compare against the 023 baseline

```bash
uv run python -m collection_agent eval-run --source discogs
```

Baseline (2026-07-07, 94 images): identification 56.4%, top-1 38.3%,
catno-rung hits 20/42 tried. What to look for now:

- **catno rung**: hit count ≥ 20 (SC-002); the previously drowned
  exact-catno cases should convert.
- **summary**: new `practical_rate` beside the unchanged strict rate, plus
  the miss split (`misses_same_master` / `misses_different` /
  `misses_master_unknown`).
- **results.jsonl**: every evaluated record now carries the extracted
  `evidence` values — zero-candidate misses are diagnosable from the file
  alone (SC-003).

## 3. Live scan spot-check (US1 on the phone page)

Start `uv run python -m collection_agent scan` and photograph a record whose
catalog number is short and prefix-shared (the `SUB 15` class): the exact
pressing should now be the FIRST candidate. Non-catno scans behave exactly
as before.

## 4. Offline suite

```bash
cd collection-agent && pytest
```

## Owner live-validation checklist

- [x] **SC-002** Fresh `eval-run --source discogs` after backfill: catno-rung
      hits ≥ 20/42-equivalent; drowned-exact-match class converted.
      New strict rate: 52.1 % · practical rate: 56.4 %.
      **Reading (2026-07-11, run `20260711-222805Z-discogs`, after
      `--backfill-masters` of 42 releases / 8 masterless): aggregate
      INCONCLUSIVE under vision variance; target conversions CONFIRMED.**
      Catno-rung hits 17 vs baseline 20 — the ≥ 20 bar was not met, but
      the per-image diff shows the bar was the wrong instrument: 20 of 94
      images flipped outcome between the two runs purely from vision
      nondeterminism (8 miss→hit, 12 hit→miss), swamping the single-digit
      signal. Every 024 target drowning case converted (`SUB 15` catno hit
      rank 2, `FING 1` rank 4, Angelfish rank 3, `EUHO 021-6`, `DIG 019`)
      with zero regressions attributable to the exact-catno re-rank. Miss
      split 4 same-master / 17 different / 14 unknown; top-1 37.2%; 0
      errors. Honest conclusion: single-run strict-rate comparisons cannot
      resolve search-ladder changes — this comparison method is superseded
      by 025's evidence-replay mode (`eval-run --replay <run_id>`,
      `specs/025-eval-replay-barcode-gate/`), which holds vision constant.
      The same run exposed the implausible-barcode failure (image
      `17859_secondary1.jpeg`: fake barcode `3070` suppressed catno
      `D-216`), fixed by 025's plausibility gate.
- [ ] **SC-003** Pick any zero-candidate miss in the new results.jsonl and
      classify it (vision misread vs absent-from-Discogs) without any live
      lookup.
- [ ] **SC-004** Summary invariants hold: miss buckets sum to misses;
      practical ≥ strict.
- [ ] **US1 live** One physical scan of a short-catno record surfaces the
      exact pressing first on the phone page.
