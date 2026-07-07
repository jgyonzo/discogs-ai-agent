# Tasks: Scan Identification Eval Dataset & Harness

**Input**: Design documents from `/specs/023-scan-eval-harness/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R10), data-model.md, contracts/ (eval-dataset.md, eval-results.md, amendment-017-discogs-consumption-2.md), quickstart.md

**Tests**: Included — spec FR-018 mandates offline unit coverage of all pure
logic, and the component's standing discipline (022 precedent) is
test-with-feature. The suite must stay 100% offline.

**Organization**: By user story. US1 = dataset builder (P1), US2 = eval
harness (P2), US3 = photo retention (P3). All paths are repo-relative.

## Phase 1: Setup

**Purpose**: Config surface + test isolation every story needs.

- [X] T001 Add the five new Settings fields (`eval_dataset_dir`, `eval_images_per_release`, `eval_results_dir`, `scan_retain_photos`, `scan_retention_dir` — aliases/defaults per data-model.md) with VII(a)-style comments in `collection-agent/src/collection_agent/settings.py`
- [X] T002 Extend the shared `settings` fixture with tmp-path overrides for the three new directories (no test may touch real `data/`) in `collection-agent/tests/conftest.py`
- [X] T003 [P] Add the containment guard test (repo-root `.gitignore` has an active un-negated `data/` rule; all three new dir defaults resolve under `collection-agent/data/`; contract eval-dataset.md §4) in `collection-agent/tests/unit/test_eval_gitignore_guard.py`

---

## Phase 2: Foundational (blocking all stories)

**Purpose**: Image-capable Discogs client + fakes — US1 needs downloads, US2/US3 need the fakes.

- [X] T004 Add `DiscogsClient.download_image(uri) -> bytes | None` through the governed `_request` path (absolute-URL GET; `None` on 404/403; non-`image/*` content-type → `None`; research R2, amendment delta 2) in `collection-agent/src/collection_agent/discogs/client.py`
- [X] T005 [P] Grow `FakeDiscogsClient` with scriptable `get_release` image payloads and byte-serving `download_image` (per-URI success/failure scripting; research R10) in `collection-agent/tests/fixtures/fake_client.py`
- [X] T006 Unit-test `download_image` via `httpx.MockTransport` (image bytes ok · 403 → None · 404 → None · non-image content-type → None · governor/headers untouched by header-less CDN responses) in `collection-agent/tests/unit/test_discogs_client_images.py`

**Checkpoint**: client + fakes ready — user stories can start.

---

## Phase 3: User Story 1 — Discogs-image dataset builder (P1) 🎯 MVP

**Goal**: One command → gitignored labeled dataset + manifest from the owner's snapshot (spec US1, FR-001..006).

**Independent Test**: with a prebuilt tmp snapshot and `FakeDiscogsClient`, running the builder yields images + parseable manifest with correct ground truth; interrupt/re-run converges; nothing trackable by git.

- [X] T007 [US1] Manifest models (`ManifestHeader`, `ManifestImage`, `ManifestRelease` per data-model.md) + append/load helpers (append-only JSONL, torn-trailing-line tolerance, done-release resume rule) in `collection-agent/src/collection_agent/eval/dataset.py` (create `collection-agent/src/collection_agent/eval/__init__.py`)
- [X] T008 [US1] Builder run loop in `collection-agent/src/collection_agent/eval/dataset.py`: distinct release_ids from `SnapshotStore` (missing snapshot → typed error), per-release `get_release` → secondary-first selection capped at `images_per_release` (FR-003), atomic image writes (`tmp` + rename), `NOTICE.txt`, `run_header` with snapshot completeness, `release` lines (`downloaded`/`no_images`/`failed`), resume skips done releases and retries `failed`, `--limit` support, progress via `rich`
- [X] T009 [US1] Wire `eval-dataset` subcommand (`--limit`, `--images-per-release`; lazy imports; missing snapshot → message + `EXIT_CONFIG`) in `collection-agent/src/collection_agent/cli.py`
- [X] T010 [P] [US1] Unit tests in `collection-agent/tests/unit/test_eval_dataset.py`: secondary-preference + cap · primary-only release taken · `no_images` recorded not skipped · failed download recorded, build continues · resume skips `downloaded`/`no_images` and retries `failed` · torn manifest line ignored · manifest (not filename) is truth · NOTICE.txt written · run_header stamps snapshot completeness · CLI exit codes (no snapshot → 2)

**Checkpoint**: US1 delivers standalone value (a labeled local dataset).

---

## Phase 4: User Story 2 — Eval harness (P2)

**Goal**: `eval-run` over a labeled dataset → per-image results.jsonl + invariant-checked summary via the production pipeline seams (spec US2, FR-011..018).

**Independent Test**: tmp dataset (hand-written manifest + image files), stub LLM + `FakeDiscogsClient` → one result line per image, summary satisfying contract eval-results.md invariants 1–7, zero write-method references in `eval/`.

- [X] T011 [US2] Scoring module (`EvalItem`, `EvalResult`, `EvalSummary`; `score_image(...)` hit/rank/rung/taxonomy; `summarize(...)` with sum invariants, error-excluded denominators, `None` on zero denominator; contract eval-results.md §2–3) in `collection-agent/src/collection_agent/eval/scoring.py`
- [X] T012 [P] [US2] Sources module, discogs source first: newest-manifest-header echo + `downloaded` images → `EvalItem`s (mime from extension) in `collection-agent/src/collection_agent/eval/sources.py`
- [X] T013 [US2] Harness run loop in `collection-agent/src/collection_agent/eval/harness.py`: run_id `YYYYMMDD-HHMMSSZ-<source>`, per-image `extract_evidence` (production seam, injected LLM client) → `find_candidates` with `pending_duplicate_checker` (FR-011, R6/R7), per-image error capture (`vision_error`/`discogs_error`, run continues — FR-015), incremental flushed `results.jsonl`, `summary.json` at end, rich summary table, `--limit` honored + `limited` flag, unlabeled items skipped with zero vision calls
- [X] T014 [US2] Wire `eval-run` subcommand (`--source discogs|retained`, `--limit`; LLM client via `_build_llm_client` so LangSmith tracing applies; `DiscogsClient` for search; empty/missing source → message + `EXIT_CONFIG`; per-image errors do NOT fail the run — exit 0; contract eval-results.md §5) in `collection-agent/src/collection_agent/cli.py`
- [X] T015 [P] [US2] Unit tests in `collection-agent/tests/unit/test_eval_scoring.py`: hit rank 1/n · miss · no_evidence vs miss separation · error taxonomy · rung = last tried · invariants 1–7 including zero-denominator `None` rates and `hits_by_rung` sum
- [X] T016 [P] [US2] Unit tests in `collection-agent/tests/unit/test_eval_sources.py` (discogs source): only `downloaded` images yielded · ground truth from manifest · newest header echoed · missing/empty dataset → typed "nothing to evaluate" error
- [X] T017 [P] [US2] Read-only AST guard test (no `add_to_collection`/`create_folder`/`move_instance` references and no `scan.journal`/`scan.session` imports anywhere under `src/collection_agent/eval/`; contract eval-results.md §4) in `collection-agent/tests/unit/test_eval_readonly_guard.py`
- [X] T018 [US2] Integration test in `collection-agent/tests/integration/test_eval_harness.py`: full `eval-run` over a tmp dataset with scripted-stub LLM + `FakeDiscogsClient` — results/summary files written · invariants hold · a scripted vision failure yields an `error` record while the run completes · `--limit` truncates and flags `limited` · results.jsonl survives a simulated mid-run abort (partial lines parse)

**Checkpoint**: the measurement loop works end-to-end offline; owner can run it live.

---

## Phase 5: User Story 3 — Opt-in real-photo retention (P3)

**Goal**: default-off flag persists scan uploads keyed by session/cycle; journal joins give labels; harness scores the retained source (spec US3, FR-007..010, FR-012).

**Independent Test**: TestClient scan with flag on → file saved under `pending-*` then renamed to `<scan_id>.<ext>`; flag off → no directory, existing scan tests untouched; harness over a tmp retention dir + journal scores added-cycle photos and reports others unlabeled.

- [X] T019 [US3] `PhotoRetainer` (`save_pending(bytes, content_type) -> handle`, `assign(handle, scan_id)` atomic same-dir rename, content-type → extension map, every failure = one loud `logging.warning` + no raise; research R9) in `collection-agent/src/collection_agent/scan/retention.py`
- [X] T020 [US3] Flag-gated hook in `collection-agent/src/collection_agent/scan/server.py`: retainer constructed in `create_app` only when `settings.scan_retain_photos`; save immediately after the size gate; `assign` at each of the three scan_id-assignment points in `POST /api/scan`; vision-error/superseded paths leave `pending-*` untouched; `/api/search` (no photo) unaffected; flag off ⇒ zero new code paths execute
- [X] T021 [US3] Retained source in `collection-agent/src/collection_agent/eval/sources.py`: walk `<retention_dir>/<session_id>/`, join `<scan_journal_dir>/<session_id>.jsonl` — `outcome=="added"` + matching scan_id → labeled, everything else (skipped/no_match/failed/auto-closed/missing journal/`pending-*`) → unlabeled `EvalItem`s (contract eval-dataset.md §3.1)
- [X] T022 [P] [US3] Unit tests in `collection-agent/tests/unit/test_scan_retention.py`: save→assign rename semantics · extension mapping · original bytes preserved · unwritable dir → warning logged, no exception · flag-off construction never touches the filesystem
- [X] T023 [US3] Integration cases in `collection-agent/tests/integration/test_scan_server.py`: flag ON — scan saves + renames to the returned scan_id; scripted vision error leaves a `pending-*` file; retention failure (unwritable dir) still returns a normal scan response; flag OFF — retention dir never created and ALL pre-existing scan tests pass unmodified (SC-003)
- [X] T024 [P] [US3] Unit tests for the journal join in `collection-agent/tests/unit/test_eval_sources.py`: added → labeled with journal release_id · skipped/no_match → unlabeled · `pending-*` → unlabeled · missing journal file → unlabeled · multiple sessions merged
- [X] T025 [US3] Extend `collection-agent/tests/integration/test_eval_harness.py`: `--source retained` run — labeled photos scored, unlabeled counted with `vision_calls == 0`, summary invariant 7 (`unlabeled` only for retained source)

**Checkpoint**: all three stories independently done.

---

## Phase 6: Polish & Cross-Cutting

- [X] T026 [P] Update `collection-agent/README.md`: `eval-dataset` / `eval-run` runbook, retention flag, cost + licensing notes (local-only images)
- [X] T027 [P] Cross-check spec/plan/contracts/quickstart consistency (field names, env aliases, exit codes, invariant numbering) and fix doc drift in `specs/023-scan-eval-harness/`
- [X] T028 Full offline gate: `cd collection-agent && pytest` — all tests green, zero live calls, secrets-hygiene audit still counts exactly 3 sanctioned `get_secret_value` sites (no new ones added)

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Foundational (T004–T006)** → user stories.
- **US1 (T007–T010)**: needs T001/T002 (settings/fixtures), T004/T005 (client+fake). Internally T007 → T008 → T009; T010 after T007–T009.
- **US2 (T011–T018)**: needs Foundational + T001/T002. Does NOT need US1 code (integration tests hand-write manifests), but T012 reads the manifest schema fixed by T007 — implement after US1 (priority order anyway). Internally: T011, T012 [P] → T013 → T014; T015–T017 [P] anytime after their modules; T018 last.
- **US3 (T019–T025)**: needs T001/T002 only (server + journal exist from 022) — could run parallel to US2 except T021/T024/T025 touch `sources.py`/harness tests shared with US2 → schedule after US2.
- **Polish (T026–T028)**: last; T026/T027 parallel; T028 final gate.

## Parallel Opportunities

- T003 ∥ T001/T002 · T005 ∥ T004 · T010 test-writing ∥ T009 wiring
- Within US2: T011 ∥ T12; T015 ∥ T016 ∥ T017
- Within US3: T022 ∥ T023; T024 ∥ T025 prep
- T026 ∥ T027

## Implementation Strategy

MVP = Phase 1–3 (US1): a labeled dataset exists and is git-safe — already
useful. Then US2 turns it into numbers (first measured identification rate),
then US3 starts accumulating the real distribution. Stop-and-ship is viable
after every phase checkpoint.
