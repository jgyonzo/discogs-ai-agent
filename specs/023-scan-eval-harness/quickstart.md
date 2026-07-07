# Quickstart: Scan Identification Eval (023)

All commands from `collection-agent/` with the repo-root `.env` configured
(`DISCOGS_USER_TOKEN`, `OPENAI_API_KEY`; optional `LANGSMITH_*` for traced
eval runs).

## 1. Build the Discogs-image dataset (US1)

```bash
uv run python -m collection_agent eval-dataset
# smoke first (spec sample-first analog):
uv run python -m collection_agent eval-dataset --limit 10
```

- Walks the snapshot's distinct releases (run `… sync` first if `… status`
  says there is no snapshot), fetches each release's image list, downloads up
  to 2 images (secondary-preferred; override with `--images-per-release` or
  `COLLECTION_AGENT_EVAL_IMAGES_PER_RELEASE`).
- Output: `data/eval/discogs-images/` — images + `manifest.jsonl` +
  `NOTICE.txt`. Interrupt freely; re-running resumes (failed releases retry,
  finished ones are skipped).
- Everything under `data/` is gitignored — never commit or share these images.

## 2. Run the eval (US2)

```bash
# cheap smoke (10 vision calls):
uv run python -m collection_agent eval-run --source discogs --limit 10
# full run:
uv run python -m collection_agent eval-run --source discogs
```

- Each image goes through the production pipeline (same vision prompt/model/
  timeout as the scan server, same search ladder). Cost ≈ 1 vision call per
  image — the summary prints the exact billable-call count.
- Output: `data/eval/runs/<run_id>/results.jsonl` + `summary.json`, plus a
  summary table in the terminal (identification rate, top-1, per-rung hits,
  no-evidence / error counts).
- The run is read-only against Discogs; your collection cannot change.

## 3. Accumulate real scan photos (US3)

```bash
COLLECTION_AGENT_SCAN_RETAIN_PHOTOS=true uv run python -m collection_agent scan
```

- Scan records from the phone as usual. Uploaded photos land in
  `data/eval/scan-photos/<session_id>/`; confirming an add labels that photo
  via the session journal automatically.
- Then evaluate the real-photo distribution:

```bash
uv run python -m collection_agent eval-run --source retained
```

- Photos from cycles that never ended in a confirmed add show up as
  `unlabeled` (counted, not scored, no vision cost).
- Retention default is OFF; without the env flag nothing is ever saved.

## 4. Offline test suite (unchanged discipline)

```bash
cd collection-agent && pytest
```

No live API calls; builder/harness/retention logic is covered by unit +
integration tests over fakes.

## Owner live-validation checklist (SC-001..007)

- [ ] **SC-001** `eval-dataset` full build finishes without a surfaced
      rate-limit error; manifest covers ≥95% of snapshot releases that have
      images (`no_images`/`failed` lines are visible for the rest).
- [ ] **SC-002** `eval-run --source discogs` produces results.jsonl +
      summary.json; counts satisfy the sum invariants; first measured
      identification rate recorded here: ____ % (top-1: ____ %).
- [ ] **SC-003** With retention unset, `pytest` passes and a scan session
      behaves exactly as before.
- [ ] **SC-004** With retention on: scan → confirm add → `eval-run --source
      retained` scores that photo with zero manual labeling.
- [ ] **SC-005** `git status` shows nothing trackable under
      `collection-agent/data/eval/` after all of the above.
- [ ] **SC-006** Collection count on Discogs unchanged after a full eval run.
- [ ] **SC-007** Ctrl-C a build mid-run, re-run, confirm it resumes and
      converges (no duplicate images, manifest parses).
