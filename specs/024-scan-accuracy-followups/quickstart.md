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

- [ ] **SC-002** Fresh `eval-run --source discogs` after backfill: catno-rung
      hits ≥ 20/42-equivalent; drowned-exact-match class converted.
      New strict rate: ____ % · practical rate: ____ %.
- [ ] **SC-003** Pick any zero-candidate miss in the new results.jsonl and
      classify it (vision misread vs absent-from-Discogs) without any live
      lookup.
- [ ] **SC-004** Summary invariants hold: miss buckets sum to misses;
      practical ≥ strict.
- [ ] **US1 live** One physical scan of a short-catno record surfaces the
      exact pressing first on the phone page.
