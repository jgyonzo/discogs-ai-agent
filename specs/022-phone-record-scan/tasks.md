# Tasks: Phone Record Scan — Load Physical Records into the Discogs Collection

**Input**: Design documents from `/specs/022-phone-record-scan/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R10), data-model.md,
contracts/ (scan-api, scan-journal-schema, amendment-017-discogs-consumption),
quickstart.md

**Tests**: included — the component convention is normative (spec FR-018,
SC-008: full suite passes with zero live vision/Discogs calls).

**Organization**: grouped by user story. US1 = the MVP scan→add loop;
US2 = duplicate awareness; US3 = session log/journal surfacing;
US4 = manual search fallback.

**⛔ Owner-only tasks**: Phase 8 tasks are EXCLUDED from
`/speckit-implement` — they require the owner, real records, and real
writes to the live Discogs account. They are listed for completeness
and stay unchecked until the owner runs them.

## Format: `[ID] [P?] [Story?] Description with exact file path`

All paths relative to repo root.

---

## Phase 1: Setup

**Purpose**: dependencies, package skeleton, configuration surface.

- [x] T001 Add `fastapi`, `uvicorn`, `python-multipart` to
      `collection-agent/pyproject.toml` dependencies and refresh
      `collection-agent/uv.lock` (`cd collection-agent && uv lock` or
      `uv sync`); suite still passes untouched.
- [x] T002 [P] Create the scan subpackage skeleton:
      `collection-agent/src/collection_agent/scan/__init__.py` and
      empty module stubs `models.py`, `vision.py`, `search.py`,
      `session.py`, `journal.py`, `server.py`, plus
      `collection-agent/src/collection_agent/scan/static/` directory.
- [x] T003 Add the seven scan settings fields to
      `collection-agent/src/collection_agent/settings.py` per research
      R2/R5–R9: `collection_agent_vision_model`
      (`COLLECTION_AGENT_VISION_MODEL`, default `gpt-4o-mini`),
      `scan_host` (`COLLECTION_AGENT_SCAN_HOST`, `0.0.0.0`),
      `scan_port` (`COLLECTION_AGENT_SCAN_PORT`, `8022`),
      `scan_target_folder_id` (`COLLECTION_AGENT_SCAN_FOLDER_ID`, `1`),
      `scan_candidates_max` (`COLLECTION_AGENT_SCAN_CANDIDATES_MAX`, `8`),
      `scan_max_image_bytes` (`COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES`,
      `10485760`), `scan_journal_dir`
      (`COLLECTION_AGENT_SCAN_JOURNAL_DIR`, default
      `<component>/data/scan-sessions`) — existing alias/`Field` idiom,
      no hardcoded literals downstream (Constitution VII(a)).
- [x] T004 [P] Extend the `settings` fixture in
      `collection-agent/tests/conftest.py` so scan tests get
      `SNAPSHOT_PATH`- and `COLLECTION_AGENT_SCAN_JOURNAL_DIR`-style
      isolation under `tmp_path` (keep `_env_file=None` discipline);
      add a `scan_settings` fixture if cleaner.

**Checkpoint**: `cd collection-agent && pytest` green (223 tests), new
deps importable.

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: domain models, Discogs client extensions + fakes, journal,
session — everything every story builds on.

- [x] T005 [P] Implement scan domain models in
      `collection-agent/src/collection_agent/scan/models.py` per
      data-model.md: `ScanEvidence` (all-optional fields, barcode
      digit-normalization validator, `is_empty`, `evidence_kinds`),
      `Candidate` (verbatim-source fields incl. `thumb_url`,
      `discogs_uri`), `DuplicateStatus`, `ScanCycleOutcome`, and the
      API request/response models (`ScanResponse`, `AddRequest`,
      `AddResponse`, `SkipRequest`, `SessionResponse`).
- [x] T006 [P] Unit tests for the models in
      `collection-agent/tests/unit/test_scan_models.py`: barcode
      normalization (spaces/hyphens stripped; garbage → None),
      `is_empty`, `evidence_kinds` derivation, outcome literal
      validation.
- [x] T007 [P] Add Discogs payload builders to
      `collection-agent/tests/fixtures/discogs_payloads.py`:
      search-result page (`results[]` with `id,title,year,country,
      format,label,catno,thumb,cover_image,uri` + `pagination.items`)
      and add-to-collection response (`instance_id`, …), with
      field-omission knobs for absent-field cases.
- [x] T008 Add `search_releases(params: dict) -> dict` and
      `add_to_collection(username, folder_id, release_id) -> dict` to
      `collection-agent/src/collection_agent/discogs/client.py`, both
      through `_get_json`/`_request` so auth + governor apply
      (research R3; write mirrors `create_folder`/`move_instance`
      shape).
- [x] T009 [P] Unit tests for the two client methods in
      `collection-agent/tests/unit/test_discogs_client_scan.py` via
      injected `httpx.MockTransport`: correct path/params, auth header
      present, 429→backoff→retry path, 401→`DiscogsAuthError`,
      5xx→retries→`DiscogsServerError`, add POST returns instance
      payload.
- [x] T010 Extend `collection-agent/tests/fixtures/fake_client.py`
      `FakeDiscogsClient` with scriptable `search_releases` (canned
      pages per params-rung, so ladder tests can assert which rung
      fired) and `add_to_collection` (records calls, returns builder
      payload, scriptable failure).
- [x] T011 [P] Implement the append-only JSONL journal in
      `collection-agent/src/collection_agent/scan/journal.py` per
      contracts/scan-journal-schema.md: dir creation, one file per
      `session_id`, append+flush per `ScanCycleOutcome`, loud failure
      on I/O error (never silent drop).
- [x] T012 [P] Unit tests in
      `collection-agent/tests/unit/test_scan_journal.py`: line shape
      matches contract, append-only across events, flush-per-event
      (file readable mid-session), unknown-key tolerance on read-back.
- [x] T013 Implement `ScanSession` in
      `collection-agent/src/collection_agent/scan/session.py` per
      data-model.md: `session_id` stamp, monotonic `seq`/`scan_id`
      issuance, `seen_release_ids` allowlist, `added_release_ids`
      counts, in-memory `log` mirrored to the journal atomically with
      each outcome; unit coverage inside
      `collection-agent/tests/unit/test_scan_journal.py` or a small
      `test_scan_session.py`.

**Checkpoint**: foundation green; user stories can start.

---

## Phase 3: User Story 1 — Scan one record and add it to the collection (P1) 🎯 MVP

**Goal**: photo → evidence → ranked candidates → tap → confirm → live
add → back to camera.

**Independent Test**: with stubbed vision + fake Discogs client, a
`TestClient` photo upload yields ranked candidates; confirming one
produces exactly one `add_to_collection` call for that release id and
the page state returns to camera-ready (spec US1 acceptance 1–5).

- [x] T014 [P] [US1] Author the vision evidence-extraction prompt at
      `collection-agent/src/collection_agent/prompts/scan_vision.md`:
      transcribe only what is legible (artist, title, label, catno,
      barcode digits, format hints), never guess, omit unreadable
      fields, output JSON only (keys matching `ScanEvidence`). No
      catalog-schema prose (Constitution VII(b) not engaged).
- [x] T015 [US1] Implement `extract_evidence(llm, settings,
      image_bytes, mime) -> ScanEvidence` in
      `collection-agent/src/collection_agent/scan/vision.py`: one
      `chat.completions.create` with base64 `data:` URL image part +
      prompt file, `response_format={"type":"json_object"}`, model
      from `settings.collection_agent_vision_model`; JSON parse +
      pydantic validation; invalid/unparseable reply → one retry, then
      raise a typed `VisionExtractionError` (→ 502 at the API); a
      valid reply with no fields is a legal empty `ScanEvidence`
      (research R2).
- [x] T016 [P] [US1] Unit tests in
      `collection-agent/tests/unit/test_scan_vision.py` with the
      `StubLLM` shape: happy extraction, invalid JSON → retry →
      error, empty evidence, image encoded as data URL, model name
      taken from settings (no literal).
- [x] T017 [US1] Implement the candidate pipeline in
      `collection-agent/src/collection_agent/scan/search.py`:
      precision ladder per FR-004 (barcode → catno+label →
      artist+title; next rung only when prior absent/zero), free-text
      rung for manual search (US4 reuses it), dedup by `release_id`,
      cap at `settings.scan_candidates_max`, `more_matches` from
      `pagination.items`, verbatim field mapping search-result →
      `Candidate` (absent keys stay None/[] — FR-005/006), duplicate
      overlay left as an injectable hook defaulting to
      `unknown("duplicate check pending")` until US2.
- [x] T018 [P] [US1] Unit tests in
      `collection-agent/tests/unit/test_scan_search.py`: ladder order
      + fallback-on-zero, no lower rung when higher rung hits, dedup,
      cap + `more_matches`, and the 019-style verbatim audit — every
      candidate field byte-equal to the fake payload, absent fields
      absent, zero constructed URLs.
- [x] T019 [US1] Implement the FastAPI app factory + routes in
      `collection-agent/src/collection_agent/scan/server.py` per
      contracts/scan-api.md: `create_app(settings, llm_client,
      discogs_client, store, session, journal)`; `GET /` (static
      page), `GET /api/health`, `POST /api/scan` (multipart; size gate
      413 before any work; media-type gate 415; vision → ladder →
      candidates; allowlist registration; no-match = 200 with empty
      candidates + honest message; `vision_unavailable` /
      `discogs_unavailable` 502 mapping), `POST /api/add` (allowlist
      gate 403 `unknown_candidate` → live add → `added` w/
      `instance_id` | `failed` w/ honest detail; journal + session
      update; duplicate gate lands in US2), `POST /api/skip`
      (idempotent per scan_id; `skipped`/`no_match` journaling),
      typed error bodies `{"error":{code,message}}` throughout.
- [x] T020 [US1] Author the self-contained phone page at
      `collection-agent/src/collection_agent/scan/static/index.html`:
      vanilla HTML/CSS/JS, no external resources except the API and
      verbatim `thumb_url` images; `<input type="file"
      accept="image/*" capture="environment">`; state machine
      camera-ready → identifying → choosing → confirm → added →
      camera-ready (FR-014: one step back to camera); candidate cards
      render exactly the API fields; honest no-match + error states.
- [x] T021 [US1] Add the `scan` subcommand to
      `collection-agent/src/collection_agent/cli.py`: subparser with
      `--host/--port` overriding settings; `_cmd_scan(settings)` —
      guard `openai_api_key is None → EXIT_CONFIG` (mirror
      `_cmd_chat`), build LLM via existing `_build_llm_client`, build
      `DiscogsClient`/`SnapshotStore`/`ScanSession`/journal, validate
      `scan_target_folder_id` live against `client.get_folders()` at
      startup (fail fast, research R9), print LAN URL banner
      (stdlib best-effort local IP), run uvicorn.
- [x] T022 [US1] Integration tests (part 1) in
      `collection-agent/tests/integration/test_scan_server.py` via
      `TestClient` + stub vision + `FakeDiscogsClient`: happy path
      photo→candidates→add (exactly one recorded add, correct
      folder/release), oversized upload → 413 before vision runs,
      non-image → 415, `unknown_candidate` 403 (no Discogs call),
      vision failure → 502 typed body, zero-result ladder → 200
      no-match shape, add failure → `failed` + honest detail + no
      snapshot change, and a secrets audit: no response (incl. `GET /`
      HTML and error bodies) contains the token or API key strings.

**Checkpoint**: MVP loop fully functional against stubs — US1
acceptance scenarios 1–5 all covered.

---

## Phase 4: User Story 2 — Duplicate awareness before adding (P2)

**Goal**: snapshot-driven duplicate markers, server-enforced second
confirmation, post-add snapshot reconciliation.

**Independent Test**: with a snapshot fixture containing release X,
scanning a record resolving to X shows `in_collection` with the right
count; adding X without `confirm_duplicate` never writes; with it,
writes once and marks the snapshot stale (spec US2 acceptance 1–4).

- [x] T023 [US2] Implement duplicate-status computation in
      `collection-agent/src/collection_agent/scan/search.py` (replace
      the T017 hook): per data-model.md rules — complete snapshot →
      `in_collection(count)`/`not_in_collection`; missing snapshot →
      `unknown("no snapshot")`; partial/stale snapshot → presence
      shows counts "as of last sync", absence degrades to `unknown`
      (never `not_in_collection` — FR-010); session-added releases
      always `in_collection` with `added_this_session=true` and
      session copies included.
- [x] T024 [P] [US2] Unit tests in
      `collection-agent/tests/unit/test_scan_search.py` (extend):
      each snapshot state (complete/partial/stale/missing) × presence
      matrix, session-add overlay, count arithmetic
      (snapshot instances + session adds).
- [x] T025 [US2] Wire the duplicate gate + reconciliation into
      `collection-agent/src/collection_agent/scan/server.py`
      `/api/add`: duplicate-status `in_collection` (or
      `added_this_session`) without `confirm_duplicate=true` → 200
      `needs_duplicate_confirmation` + duplicate payload, NO write;
      confirmed path → add, journal `added` with
      `duplicate_add=true`, `SnapshotStore.mark_stale()` after every
      successful add (research R4), session `added_release_ids`
      update.
- [x] T026 [US2] Page support in
      `collection-agent/src/collection_agent/scan/static/index.html`:
      render duplicate markers ("already in your collection — N
      copies" / "duplicate status unknown — <reason>"), drive the
      extra confirmation from the `needs_duplicate_confirmation`
      response (never send `confirm_duplicate:true` on first tap).
- [x] T027 [US2] Integration tests (part 2) in
      `collection-agent/tests/integration/test_scan_server.py`:
      duplicate double-confirm flow (first add attempt → no write;
      second with flag → exactly one write), `mark_stale` invoked on
      success only, same-release-again-in-session shows
      `added_this_session` with updated count, degraded snapshot →
      `unknown` markers.

**Checkpoint**: US1 + US2 independently green.

---

## Phase 5: User Story 3 — Batch session with reviewable log (P2)

**Goal**: on-page session log + persisted journal reviewable after
interruption.

**Independent Test**: several stubbed cycles with mixed outcomes → the
`/api/session` log lists all outcomes newest-first and the JSONL file
contains one line per outcome, intact if the server is killed
mid-session (spec US3 acceptance 1–3).

- [x] T028 [US3] Add `GET /api/session` to
      `collection-agent/src/collection_agent/scan/server.py` returning
      `{session_id, entries[]}` newest-first per contracts/scan-api.md.
- [x] T029 [US3] Add the session-log panel to
      `collection-agent/src/collection_agent/scan/static/index.html`:
      renders `/api/session`, refreshes after every completed cycle,
      shows outcome + release identity + duplicate_add badge.
- [x] T030 [US3] Integration tests (part 3) in
      `collection-agent/tests/integration/test_scan_server.py`: mixed
      added/skipped/no_match/failed sequence → `/api/session` order
      and contents correct; journal file on disk has exactly one
      line per completed cycle matching the contract schema
      (validated line-by-line); earlier entries byte-unchanged after
      later appends; a journal-write failure surfaces as a `failed`
      cycle, never a silent drop.

**Checkpoint**: US3 independently green.

---

## Phase 6: User Story 4 — Manual search fallback (P3)

**Goal**: free-text search with the identical candidate/confirm/log
flow.

**Independent Test**: stubbed `GET /api/search?q=…` returns the same
response shape as `/api/scan` (`source: manual_search`), flows through
duplicate markers, confirmation, and journaling identically (spec US4
acceptance 1–3).

- [x] T031 [US4] Add `GET /api/search` to
      `collection-agent/src/collection_agent/scan/server.py`: blank
      `q` → 400 `empty_query`; otherwise free-text rung of the T017
      pipeline (`q=` search), same response model, allowlist
      registration, `evidence_summary.kinds=["text"]`,
      `source="manual_search"`.
- [x] T032 [US4] Page support in
      `collection-agent/src/collection_agent/scan/static/index.html`:
      manual-search box offered on no-match and via "none of these";
      results reuse the same candidate/confirm components; skip/add
      logged as usual.
- [x] T033 [US4] Integration tests (part 4) in
      `collection-agent/tests/integration/test_scan_server.py`:
      response-shape parity with `/api/scan`, empty query → 400,
      manual-search add journals with `source="manual_search"`,
      no-match manual search followed by skip journals `no_match`.

**Checkpoint**: all four stories independently green.

---

## Phase 7: Polish & repo consistency

- [x] T034 [P] Update `collection-agent/README.md`: new `scan`
      subcommand section (run, config table from quickstart, LAN
      posture + no-auth risk note, journal location, test pointer).
- [x] T035 [P] Verify secrets-hygiene conventions: grep-style static
      audit that no scan module calls `get_secret_value` outside the
      sanctioned sites and the static page contains no templated
      config; extend the existing secrets-hygiene test if one guards
      this (`collection-agent/tests/` — locate and amend in place).
- [x] T036 Full suite gate: `cd collection-agent && pytest` — all
      green, record the new test count; confirm zero network sockets
      (TestClient in-process; no live API markers).
- [x] T037 Write the post-merge CLAUDE.md merged-state block for 022
      on this branch (single-PR flow, owner decision 2026-07-07):
      replace the in-flight note with the merged-state summary
      (leave PR number/merge date as placeholders for the owner to
      finalize at merge time).

---

## Phase 8: ⛔ Owner-only live validation (EXCLUDED from /speckit-implement)

**These tasks require the owner, real records, the live Discogs
account, and real writes. `/speckit-implement` MUST stop before this
phase.** Checklist mirrors quickstart.md.

- [ ] T038 ⛔ [OWNER] Live session: run `python -m collection_agent
      scan`, open the LAN URL on the phone, scan a 10-record batch;
      validate SC-001 (<15 s to candidates), SC-002 (≥8/10 correct
      pressing present), SC-003 (≤3 taps per add, 4 for duplicates).
- [x] T039 ⛔ [OWNER] Write-gate & honesty audit on the live batch:
      SC-004 (zero unconfirmed writes — cross-check Discogs web
      history), SC-005 (spot-check fields/links/thumbnails verbatim
      against discogs.com), SC-006 (duplicate markers + counts
      correct).
- [x] T040 ⛔ [OWNER] Interruption drill: kill the server mid-session,
      verify SC-007 (journal accounts for every completed cycle);
      then `python -m collection_agent sync` and confirm the chat
      agent sees the additions. Record a live-validation note in
      `specs/022-phone-record-scan/quickstart.md` (021 precedent).
- [ ] T041 ⛔ [OWNER] Decide whether/how to expose the scan server
      beyond the home LAN (auth, HTTPS) — explicitly out of v1 scope;
      record the decision in the spec if taken up.

---

## Phase 9: Replay round 1 fixes (spec addendum 1, 2026-07-07)

Live session `20260707-130810Z` (0/4 identified) — findings F1–F3.

- [x] T042 Harden `collection-agent/src/collection_agent/prompts/scan_vision.md`
      per FR-003 refinement: barcode-digits-vs-catno, label≠artist,
      12″ lead-track-is-title convention, new `tracks` field.
- [x] T043 `ScanEvidence` gains `tracks` + FR-019 normalization
      (10+-digit catno → barcode) in
      `collection-agent/src/collection_agent/scan/models.py`; `is_empty`
      counts tracks; unit tests incl. the live cycle-2/3/4 payloads.
- [x] T044 FR-020 composed free-text fallback rung in
      `collection-agent/src/collection_agent/scan/search.py`
      (`compose_query`; fires only when structured rungs are absent or
      all-zero; `tried` gains `text`); unit tests incl. the live
      cycle-1 (label-only) and cycle-2 replays.
- [x] T045 FR-021 journaled evidence values: `ScanCycleOutcome.evidence`,
      session plumbing, server passes compact evidence (photo) / query
      (manual); journal + integration tests.
- [x] T046 Full suite gate green; contracts/data-model/spec addendum 1
      consistent.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → user stories**: T001–T004 first; T005–T013
  block all stories.
- **US1 (Phase 3)** depends only on Foundational. T014∥T016 prep,
  T015 needs T014; T017 needs T005/T010; T019 needs T015+T017+T013;
  T020 needs T019's contract (can draft in parallel against
  contracts/scan-api.md); T021 needs T019; T022 last.
- **US2 (Phase 4)** depends on US1's server/page (T019/T020) plus
  Foundational; T023→T025→T027, T026 parallel with T025 after T023.
- **US3 (Phase 5)** depends on Foundational journal/session
  (T011–T013) + server (T019); independent of US2.
- **US4 (Phase 6)** depends on T017 + T019/T020; independent of
  US2/US3.
- **Phase 7** after all implemented stories; T037 last before PR.
- **Phase 8** owner-only, after merge-ready state.

### Parallel opportunities

- Phase 1: T002 ∥ T004 (T001, T003 sequential w.r.t. lock/settings).
- Phase 2: T005 ∥ T007 ∥ T011; tests T006 ∥ T009 ∥ T012 once their
  targets exist.
- Phase 3: T014 ∥ T016-scaffold ∥ T018-scaffold; T020 drafts against
  the contract while T019 is built.
- Phases 4–6 are mutually independent after US1 (different concerns;
  where they touch the same files — server.py, index.html, the
  integration test module — apply sequentially).

## Implementation Strategy

MVP-first: Phases 1–3 deliver a demoable scan→add loop (US1) fully
covered by stubs. Then US2 (duplicate safety), US3 (session log), US4
(manual fallback) as independent increments, each leaving the suite
green. Stop after Phase 7: the branch is PR-ready; Phase 8 stays with
the owner. Commit after each phase (or logical task group) on
`022-phone-record-scan`; nothing merges to main.
