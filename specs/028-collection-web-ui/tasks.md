# Tasks: Collection-Agent Web UI

**Input**: Design documents from `/specs/028-collection-web-ui/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R10), data-model.md, contracts/ (web-ui-api.md, amendment-017-agent-tools.md deltas 12–14, amendment-022-scan-api-4.md), quickstart.md

**Tests**: included (house rule — every prior collection-agent feature ships its tests in the same change; SC-007 requires the full suite green with no live API calls). Write each story's tests first and watch them fail before implementing.

**Organization**: grouped by user story. All paths are relative to the repo root.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create the `web/` package skeleton: `collection-agent/src/collection_agent/web/__init__.py` plus empty module files `server.py`, `chat.py`, `syncrun.py`, `agent_factory.py`, `models.py` (docstring headers pointing at `specs/028-collection-web-ui/contracts/web-ui-api.md`); confirm `cd collection-agent && pytest` still passes (545) before any behavior change.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: shared machinery every story consumes — payload models, the SyncRunner (US1's `start_sync` tool AND US2's endpoints delegate to it), the tab shell the Chat/Collection UIs render into, the composed app, and the registration helper the web agent factory shares with the CLI.

- [X] T002 [P] Extract the story-tool registration loop from `cli.py::_register_story_tools` into `collection-agent/src/collection_agent/tools/registration.py::register_story_tools(agent, settings, store)` and make `cli.py` call it; behavior identical (all existing chat/CLI tests pass unmodified).
- [X] T003 [P] Implement the web payload models in `collection-agent/src/collection_agent/web/models.py` per data-model.md (`ChatRequest`, `ChatResponse`, `PendingPlanView`, `MoveOutcomeView`, `ChatEntry`, `HistoryResponse`, `PlanActionRequest`, `PlanConfirmResponse`, `SyncStatusView`, `CollectionStatusResponse`) with a unit test `collection-agent/tests/unit/test_web_models.py` (field defaults, ChatRequest empty-text rejection at the endpoint layer documented as 400).
- [X] T004 [P] Write failing unit tests for the SyncRunner in `collection-agent/tests/unit/test_sync_runner.py` (stubbed `run_sync`): state machine idle→running→complete/partial/failed, atomic single-occupancy (second `start()` refused while running), `on_progress` phase/done/total capture, `notify` → warnings, exception → `failed` with message, re-`start()` after partial/failed allowed, `full` is always False.
- [X] T005 Implement `collection-agent/src/collection_agent/web/syncrun.py::SyncRunner` per research R5 (daemon thread, own injected client factory closed in `finally`, mutex-guarded status snapshot, terminal state from `meta.completeness`); make T004 pass.
- [X] T006 [P] Reshape `collection-agent/src/collection_agent/scan/static/index.html` into the three-tab shell (Scan | Chat | Collection): existing scan markup/JS moves inside the Scan tab functionally unchanged; Chat/Collection tabs are empty containers for now; ALL existing page guard tests (`test_scan_page_links.py`, secrets grep) must pass — update a guard only if it pins incidental markup, never an invariant.
- [X] T007 Implement `collection-agent/src/collection_agent/web/server.py::create_web_app(settings, llm_client, discogs_client, store, scan_session, username, web_chat, sync_runner)` composing the untouched `scan.server.create_app` (research R1), story routes stubbed 404 for now; add integration regression test `collection-agent/tests/integration/test_web_app_composition.py` proving every scan endpoint behaves identically through the composed app (drive `/api/scan`-adjacent happy path + `/api/health` + `/` serves the tabbed page).

**Checkpoint**: foundation ready — scan works through the composed app, SyncRunner exists, page shell exists.

---

## Phase 3: User Story 1 — Chat with the collection from any LAN device (P1) 🎯 MVP

**Goal**: web chat with terminal parity plus the HTTP write gate (confirm card; declining/new-turn cancels; confirm executes with live re-validation).

**Independent Test**: with a snapshot fixture and stubbed LLM/Discogs clients, TestClient drives a question→answer turn, a propose→card→cancel flow (zero writes), and a propose→confirm flow (scripted moves executed, outcomes returned). Live: quickstart SC-001/SC-002.

### Tests for User Story 1 (write first, watch them fail)

- [X] T008 [P] [US1] Unit tests for WebChat in `collection-agent/tests/unit/test_web_chat.py` (stub Agent): lock busy behavior, pending-plan expiry on new turn (+ `plan_cancelled` entry), message-list REWIND on agent exception (session usable after — research R2), transcript entry kinds, PendingPlanView built from a `PROPOSED` WritePlan.
- [X] T009 [P] [US1] Integration tests for the chat endpoints in `collection-agent/tests/integration/test_web_chat_api.py` (TestClient, scripted stub LLM): `POST /api/chat` 200 reply, 400 `empty_message` (no LLM call), 409 `chat_busy` while a slow turn holds the lock, 502 `chat_error` + rewind + error transcript entry, pending_plan payload when the turn parks a plan; `GET /api/chat/history` returns entries + pending plan + `snapshot_state`; restart (new app) starts empty.
- [X] T010 [P] [US1] Integration tests for the plan gate in `collection-agent/tests/integration/test_web_plan_gate.py` (FakeDiscogsClient grown with scriptable `get_folders`/`get_release_instances`/`move_instance`/`create_folder`): confirm executes ONLY the server-held plan with per-move outcomes + snapshot patch; cancel writes nothing; 409 `no_pending_plan` (none, after cancel, after execute, after restart), 409 `plan_mismatch` (stale plan_id); new-turn expiry makes a later confirm 409; request body can never inject move data (FR-005 pin).

### Implementation for User Story 1

- [X] T011 [US1] Implement `collection-agent/src/collection_agent/web/chat.py::WebChat` per data-model.md turn algorithm (lock, expiry, rewind, transcript, plan confirm/cancel calling the unchanged `tools/organize.py::execute_plan`); make T008 pass.
- [X] T012 [P] [US1] Implement `collection-agent/src/collection_agent/web/agent_factory.py::build_web_agent(settings, store, llm_client, sync_starter)`: registry + Agent, `snapshot_status` via the existing `snapshot_status_payload`, web-owned `start_sync` ToolDef delegating non-blocking to the SyncRunner (`started`/`already_running`, `full` ignored with honest note — contract delta 13), story tools via `tools/registration.py`; unit test in `collection-agent/tests/unit/test_web_agent_factory.py` (tool names match CLI set, start_sync payloads, full-flag note).
- [X] T013 [US1] Runtime-neutral confirmation wording: `tools/organize.py` `propose_moves` payload `detail` and `prompts/system.md` write-confirmation prose stop naming the terminal (delta 13); update any existing test pinning the old string, intent preserved.
- [X] T014 [US1] Register the chat routes in `web/server.py`: `POST /api/chat`, `GET /api/chat/history`, `POST /api/chat/plan/confirm`, `POST /api/chat/plan/cancel` per contracts/web-ui-api.md §2 (scan error envelope, codes `empty_message`/`chat_busy`/`chat_error`/`no_pending_plan`/`plan_mismatch`); make T009/T010 pass.
- [X] T015 [US1] CLI wiring in `collection-agent/src/collection_agent/cli.py`: new `serve` subcommand + `scan` kept as working alias (same `--host`/`--port`, same startup validation — delta 14); startup builds `SyncRunner`, `build_web_agent`, `WebChat`, and `create_web_app`; banner mentions the three tabs; existing scan startup tests pass; add CLI test for the alias in `collection-agent/tests/unit/test_cli_serve.py`.
- [X] T016 [US1] Chat tab UI in `collection-agent/src/collection_agent/scan/static/index.html`: transcript rendering (user/assistant/error/plan entries), send box disabled while busy, plan confirmation card (Confirm/Cancel → the plan endpoints, echoing only `plan_id`), history fetch on page load (FR-016), typed-error display; self-contained, no secrets, no client-built URLs.

**Checkpoint**: web chat + write gate fully functional and independently testable (MVP).

---

## Phase 4: User Story 2 — Collection status + sync from the page (P2)

**Goal**: status view, single-occupancy background sync with live progress, stale banner, post-sync freshness in-process.

**Independent Test**: TestClient with stubbed `run_sync`: status payload correct for complete/stale/absent snapshots; `POST /api/sync` 202 then 409 while running; completion flips state and the next chat/duplicate answer reads the fresh snapshot. Live: quickstart SC-003/SC-005/SC-006.

### Tests for User Story 2 (write first, watch them fail)

- [X] T017 [P] [US2] Integration tests for status + sync endpoints in `collection-agent/tests/integration/test_web_collection_api.py`: `GET /api/collection/status` full shape (snapshot block = `snapshot_status_payload` shape, `null` when absent, `collection_url` present, sync view fields), `POST /api/sync` 202 started / 409 `sync_already_running` (atomic), terminal states complete/partial/failed with honest error, warnings passthrough, chat's `start_sync` tool and the endpoint sharing one occupancy.
- [X] T018 [P] [US2] Freshness pin (research R6) in `collection-agent/tests/integration/test_web_freshness.py`: in ONE app instance, a scripted sync atomically writes a new snapshot ⇒ the NEXT `GET /api/collection/status`, chat `snapshot_status` answer, and scan duplicate check all reflect it with no restart (guards against a future SnapshotStore cache).
- [X] T019 [P] [US2] `collection_page_url` unit + grep guard in `collection-agent/tests/unit/test_collection_link.py`: URL = `{DISCOGS_WEB_BASE_URL}/user/{username}/collection`, built only in `tools/common.py` (the `/user/` shape exists at exactly one src site — 019 discipline).

### Implementation for User Story 2

- [X] T020 [P] [US2] Add `collection_page_url(settings, username)` to `collection-agent/src/collection_agent/tools/common.py` beside `release_page_url`/`master_page_url`; make T019 pass.
- [X] T021 [US2] Register the collection routes in `web/server.py`: `GET /api/collection/status` (snapshot payload + `collection_url` + SyncRunner view) and `POST /api/sync` (202/409) per contracts/web-ui-api.md §3; make T017/T018 pass.
- [X] T022 [US2] Collection tab + banners in `collection-agent/src/collection_agent/scan/static/index.html`: status block, Sync button with progress line (poll `GET /api/collection/status` ~2s while running and on tab activation), honest failure/partial display with re-sync affordance, "View on Discogs" link (`target="_blank" rel="noopener noreferrer"`, server-provided URL verbatim), stale/absent banner + Sync action in the Chat tab (FR-011), sync-in-progress hint visible from Scan/Chat (FR-013).

**Checkpoint**: US1 + US2 both work; the full scan-add → stale → sync → fresh-chat loop is drivable from the page.

---

## Phase 5: User Story 3 — One page for everything, scan preserved (P3)

**Goal**: the tabbed page is one coherent surface; scan behavior provably unchanged; disciplines guard-pinned on the new content.

**Independent Test**: full scan flow (photo→candidates→add, manual search, pressings, duplicate confirm) via TestClient through the composed app; page guard suite green. Live: quickstart SC-004.

- [X] T023 [P] [US3] Page guard tests for the tabbed page in `collection-agent/tests/unit/test_web_page_guards.py`: no secrets/token/key strings, no hardcoded Discogs/YouTube hosts anywhere in the page, every external anchor carries `target="_blank" rel="noopener noreferrer"`, chat/collection sections present, no client-side URL construction for Discogs pages (extends the 022/026 grep discipline to the new content).
- [X] T024 [US3] Scan-regression integration test through the composed app in `collection-agent/tests/integration/test_web_scan_regression.py`: drive the full 022/026 cycle (scan→candidates→duplicate double-confirm→add→journal lines; manual search; master-versions fetch; supersede 409) against `create_web_app` and assert responses byte-equal to the same flow against bare `scan.server.create_app`.
- [X] T025 [US3] Tab UX polish in `collection-agent/src/collection_agent/scan/static/index.html`: switching tabs never resets an in-flight scan cycle or the chat transcript view (state lives outside tab visibility); default tab = Scan (phone-first parity).

**Checkpoint**: all three stories functional; suite green.

---

## Phase 6: Polish & Cross-Cutting

- [X] T026 [P] Update `collection-agent/README.md`: `serve` mode (with `scan` alias note), the three tabs, sync-from-page semantics (standard sync only; `--full` stays terminal), trust-model note (owner decision 2026-07-12), container invocation unchanged.
- [X] T027 Full-suite + guard sweep: `cd collection-agent && pytest` green with no live API calls; verify the 027 packaging guards (`test_docker_packaging.py`) and ALL pre-028 scan tests pass unmodified (except wording pins updated in T013/T006 with intent preserved — list them in the PR description).
- [X] T028 Write the post-merge CLAUDE.md state block for 028 on this branch (single-PR flow: feature + CLAUDE.md merged-state in one PR), replacing the in-flight pointer.
- [ ] T029 Owner-only: execute the live-validation checklist in `specs/028-collection-web-ui/quickstart.md` (SC-001..SC-007 + busy/expiry/reload checks) and record results in quickstart.md.

---

## Phase 7: Replay Addendum 4 — live write during a sync (FR-017, 2026-11-21)

Owner incident 2026-11-20 (spec addendum 4): a scan add during a page sync was overwritten by the sync's `complete` snapshot. Contract: `contracts/amendment-017-snapshot-schema.md` + web-ui-api §3 `stale` sync state.

- [X] T030 [P] Store tests in `collection-agent/tests/unit/test_snapshot_live_writes.py` (fail first): marker absent until a write; `mark_stale` and `patch_moved_instances` each bump it (distinct tokens), including with NO snapshot on disk; patch with no sync keeps `complete` (unchanged); the write lock is per-path and shared across `SnapshotStore` instances of the same path; a patch blocked on the lock cannot overwrite a snapshot saved inside the lock.
- [X] T031 [P] Sync tests in `collection-agent/tests/integration/test_sync_concurrent_writes.py` (fail first): add (`mark_stale`) during enrichment ⇒ meta + persisted `stale`, cause warning, journal KEPT; move (`patch_moved_instances`) during enrichment ⇒ `stale`; write during the first-ever sync (no snapshot) ⇒ `stale`; write before the sync started ⇒ `complete` (no false positive); concurrent write + 5xx ⇒ stays `partial` + warning; follow-up standard sync re-lists and enriches ONLY the new release ⇒ `complete`, journal cleared.
- [X] T032 Incident reproduction through the composed app in `collection-agent/tests/integration/test_web_sync_live_write.py`: real `run_sync` held open mid-enrichment; `/api/search` → `/api/add` during the sync ⇒ sync state `stale` + warning, snapshot `stale`; second `POST /api/sync` (Discogs now lists the add) ⇒ `complete`, record present, only that release enriched. SyncRunner unit test for the `stale` terminal state added to 028's own `test_sync_runner.py` (no pre-028 test file modified). Suite 617 → 633 (+16).
- [X] T033 Implementation: `snapshot/store.py` — `.live-writes` marker (`record_live_write`, `live_write_marker`), per-path `write_lock()`, `mark_stale`/`patch_moved_instances` bump-then-RMW under the lock; `snapshot/sync.py` — capture before the first request, compare-and-save under the lock, `complete→stale` + warning + journal kept; `web/syncrun.py` + `web/models.py` — `stale` terminal state; `scan/static/index.html` — stale-run message ("Sync again to include it"). `scan/server.py` diff stays zero.
- [X] T034 Docs: spec addendum 4 + FR-017 + edge case; `amendment-017-snapshot-schema.md` (NEW, first amendment to that contract); web-ui-api §3 + data-model state machines; README sync note; quickstart revalidation step for SC-003 incl. the live-write leg.

---

## Phase 8: Replay Addendum 5 — duplicate badge double-count (FR-018, 2026-11-21)

Owner observation during SC-004: "2 copies (incl. this session)" for one owned copy after a same-process sync absorbed the session's add. Contract: delta appended to `contracts/amendment-022-scan-api-4.md`.

- [X] T035 [P] Tests in `collection-agent/tests/unit/test_duplicate_session_reconcile.py` (fail first): session add absorbed by the snapshot (matching `instance_id`) ⇒ counted once; add not yet in the snapshot ⇒ still stacks; two adds, one absorbed ⇒ snapshot + 1; add with unknown `instance_id` ⇒ conservative count; `added_this_session`/state unchanged. 022's `TestDuplicateStatus` (log-less fake session) passes unmodified.
- [X] T036 [P] Owner flow through the composed app in `collection-agent/tests/integration/test_web_duplicate_after_sync.py`: search → add → page sync whose snapshot contains the add's instance → search again ⇒ `copies == 1`, `added_this_session` true; re-add without confirm ⇒ still `needs_duplicate_confirmation` (gate unchanged).
- [X] T037 Implementation in `collection-agent/src/collection_agent/scan/search.py::snapshot_duplicate_checker` (subtract absorbed session adds by `instance_id`; `scan/server.py` diff zero) + docs (spec addendum 5 + FR-018, contract delta, quickstart SC-004 record + deferred pressings-list UX note).

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → stories**: T001 first; T002–T007 next (T002/T003/T004/T006 parallel; T005 after T004; T007 after T003+T006).
- **US1 (T008–T016)**: needs Phase 2 (models, SyncRunner for the start_sync tool seam, shell, composed app). T008/T009/T010 parallel (fail first); T011 after T008; T012 parallel with T011; T013 anytime in-story; T014 after T011/T012 (makes T009/T010 pass); T015 after T014; T016 after T014.
- **US2 (T017–T022)**: needs Phase 2; independent of US1 except T017's shared-occupancy case (needs T012's tool — run that assertion after US1 or stub it). T017/T018/T019 parallel; T020 parallel with tests; T021 after T020; T022 after T021.
- **US3 (T023–T025)**: T023 parallel anytime after T006; T024 after T007; T025 after T016+T022.
- **Polish**: T026 parallel; T027 after all code tasks; T028 before the PR opens; T029 owner-only, after T027.

## Parallel Example: User Story 1

```text
# after Phase 2, launch together:
T008 unit tests WebChat          (tests/unit/test_web_chat.py)
T009 chat endpoint tests         (tests/integration/test_web_chat_api.py)
T010 plan gate tests             (tests/integration/test_web_plan_gate.py)
# then T011 + T012 in parallel, then T013/T014, then T015/T016
```

## Implementation Strategy

MVP = Phase 1 + Phase 2 + US1 (web chat + write gate) — independently demoable from a phone. Then US2 (status/sync closes the stale loop), then US3 (guards + regression proof), then polish. Sequential single-developer flow is the expectation; commit per task or logical group.

**Totals**: 29 tasks — Setup 1, Foundational 6, US1 9, US2 6, US3 3, Polish 4. Estimated new tests ≈ 45–55 (suite 545 → ~595).
