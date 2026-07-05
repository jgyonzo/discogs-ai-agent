# Tasks: Discogs Collection Agent

**Input**: Design documents from `/specs/017-discogs-collection-agent/`
**Prerequisites**: plan.md, spec.md (clarified 2026-07-05), research.md, data-model.md, contracts/ (3), quickstart.md

**Tests**: INCLUDED — research.md R12 defines the test strategy (no live API calls; fixture-driven fakes) and the two riskiest behaviors (rate limiting, confirmation gate) are verified by injected-failure tests.

**Organization**: Tasks grouped by user story. All paths relative to repo root.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 (analytics, P1), US2 (browse/filter, P2), US3 (media links, P2), US4 (organize, P3)

---

## Phase 1: Setup (component promotion)

**Purpose**: Promote `collection-agent/` from script experiment to packaged component; relocate the matcher.

- [x] T001 Mechanically move matcher scripts into their own package: `git mv` `collection-agent/matcher.py`, `collection-agent/review_batch.py`, `collection-agent/export_batch.py` → `collection-agent/src/collection_matcher/` (+ new `__init__.py`); fix intra-module imports and the DuckDB/data relative paths so `python -m collection_matcher.review_batch <batch>` works from `collection-agent/`; update the import/path cell in `collection-agent/notebooks/01_matcher_experiments.ipynb` and the paths/commands in `collection-agent/README.md`. **Zero behavior change; commit this task on its own before any other 017 work** (plan §Structure Decision).
- [x] T002 Create `collection-agent/pyproject.toml`: src-layout with both packages (`collection_matcher`, `collection_agent`), `requires-python >= 3.12`, deps `openai`, `httpx`, `pydantic>=2.7`, `pydantic-settings>=2.4`, `rich`; dev extra `pytest`; fold `collection-agent/requirements.txt` (matcher deps) into it and delete the requirements file. Verify `pip install -e ".[dev]"` succeeds and the matcher entry points still run.
- [x] T003 [P] Create the `collection_agent` package skeleton per plan tree: `collection-agent/src/collection_agent/{__init__.py,__main__.py,models.py,settings.py,registry.py,agent.py,cli.py}`, subpackages `discogs/`, `snapshot/`, `tools/` (each with `__init__.py`), `prompts/system.md` placeholder, and `collection-agent/tests/{unit,integration,fixtures}/` with `conftest.py`.
- [x] T004 [P] Data & secrets hygiene: ensure `collection-agent/data/snapshot.json` and `snapshot.sync.tmp.json` are gitignored (extend existing gitignore rules covering `collection-agent/data/`); document required env vars (`DISCOGS_USER_TOKEN`, `OPENAI_API_KEY`, optional `DISCOGS_USERNAME`, `COLLECTION_AGENT_MODEL`, `SNAPSHOT_PATH`) in `collection-agent/README.md` referencing repo-root `.env`.

**Checkpoint**: `pip install -e ".[dev]"` works; matcher unchanged in behavior at its new path; empty package importable.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Settings, Discogs client + rate limiting, snapshot store + sync, registry core, agent loop, CLI shell — everything every story sits on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T005 Implement `collection-agent/src/collection_agent/settings.py` (pydantic-settings, env/.env sourced per Constitution VII(a)): `DISCOGS_USER_TOKEN` (required, secret), `DISCOGS_USERNAME` (optional override), `COLLECTION_AGENT_MODEL` (default `gpt-4o-mini`), `USER_AGENT` (default per contracts/discogs-consumption.md §1), `SNAPSHOT_PATH` (default `collection-agent/data/snapshot.json`), `RATE_LIMIT_FLOOR` (default 2), rarity thresholds (`RARITY_MAX_FOR_SALE`=2, `RARITY_WANT_HAVE_RATIO`=2.0, `RARITY_MIN_HAVE`=10), `FILTER_RESULT_LIMIT` (default 50).
- [x] T006 [P] Implement pydantic models in `collection-agent/src/collection_agent/models.py` from data-model.md: `SnapshotMeta`, `CollectionRecord`, `MediaLink`, `Folder`, `Snapshot`, `WritePlan`, `PlannedMove` — with the normalization rules (rating 0→null, year 0→null, lists never joined strings) and `schema_version=1`.
- [x] T007 [P] Implement `collection-agent/src/collection_agent/discogs/ratelimit.py`: governor reading `X-Discogs-Ratelimit*` headers, sleep when remaining ≤ floor (60 s moving window), 429 exponential backoff with jitter (base 2 s, cap 60 s), user-visible "throttled, continuing…" callback hook (contracts/discogs-consumption.md §4).
- [x] T008 Implement `collection-agent/src/collection_agent/discogs/client.py` (httpx, depends T005+T007): token auth via `Authorization: Discogs token=…` header only, settings UA on every request, `get_identity()`, `get_folders()`, `iter_collection_pages()` (folder 0, per_page=100), `get_release(id)`, `get_collection_value()`, `create_folder(name)`, `move_instance(folder_id, release_id, instance_id, target_folder_id)`; 401 abort / 404-null / 5xx-retry semantics per contracts §4; token never appears in logs or exceptions.
- [x] T009 Implement `collection-agent/src/collection_agent/snapshot/store.py` (depends T006): load/validate snapshot, atomic save (`.tmp` + `os.replace`), enrichment journal (`<path>.sync.tmp.json`) read/write, completeness state transitions (complete/partial/stale per contracts/snapshot-schema.md), `mark_stale()`, `patch_records()`, sync-age helper.
- [x] T010 Implement `collection-agent/src/collection_agent/snapshot/sync.py` (depends T008+T009): two-phase sync per research R6 — instance pass (folders, collection pages, collection value) then per-unique-release enrichment reusing journaled results (`--full` bypass); `rich` progress; warnings collected into `meta.sync_stats`; resumable after interrupt; final meta returned.
- [x] T011 Implement `collection-agent/src/collection_agent/registry.py` (depends T006): `AttributeSpec` (name, aliases en+es, kind, multi, extract, unknown_label), alias lookup, and the launch registry — `genre, style, year, decade, label, country, artist, format, folder, my_rating, community_rating, have, want, num_for_sale, lowest_price, scarcity` — with derived extractors (decade from year; scarcity from settings thresholds) per contracts/agent-tools.md §3. Include unit tests `collection-agent/tests/unit/test_registry.py`: alias lookup (es/en, case/diacritic-insensitive — "género"→genre, "sello"→label), decade derivation (1994→1990s; null year→unknown), scarcity extractor against threshold settings, `unknown_label` bucketing for null extracts, unknown-attribute lookup returns the supported list.
- [x] T012 Build test doubles and fixtures (depends T006): `collection-agent/tests/fixtures/` recorded-shape JSON (collection pages incl. pagination, release details incl. videos/nulls/404, folders, collection value) + `FakeDiscogsClient` (replays fixtures; injectable 429s, 5xx, interruptions) + shared fixtures in `collection-agent/tests/conftest.py` (sample snapshots: complete/partial/stale).
- [x] T013 [P] Static guard test `collection-agent/tests/unit/test_no_cross_imports.py`: no `etl`/`discogs_etl`/`discogs_agent` imports anywhere under `collection-agent/src/`; no `collection_matcher` ↔ `collection_agent` imports (mirrors `agent/tests/unit/test_no_etl_imports.py`).
- [x] T014 [P] Unit tests `collection-agent/tests/unit/test_snapshot_store.py`: atomic write survives simulated crash, journal round-trip, state transitions, partial never reported complete, instance_id uniqueness validation.
- [x] T015 Integration tests `collection-agent/tests/integration/test_sync.py` (depends T010+T012): full sync happy path (meta counts reconcile), 429 injection (backoff, no failure), mid-enrichment interruption → resume completes without re-fetching enriched releases, enrichment 404 → record kept + warning, failed items → `partial` + exit-code contract.
- [x] T016 Implement `collection-agent/src/collection_agent/agent.py` (depends T005+T011): OpenAI tool-calling loop (plain SDK), tool dispatch table with pydantic-validated args, session state (message history, last-listing refs, pending WritePlan slot), system-prompt renderer filling `{attribute_block}` from the registry; author `collection-agent/src/collection_agent/prompts/system.md` per contracts/agent-tools.md §5 (dynamic attribute block placeholder, language mirroring, relay warnings, state basis/criterion, no static attribute prose — Constitution VII(b)).
- [x] T017 Implement CLI shell in `collection-agent/src/collection_agent/cli.py` + `__main__.py` (depends T009+T010): subcommands `chat` (REPL banner w/ snapshot age/state, offers sync when absent, meta-commands `/refresh` `/status` `/exit`), `sync [--full]`, `status`; exit codes 0/1/2/3 per contracts/agent-tools.md §6; config errors (missing token) → exit 2 with clear message.

**Checkpoint**: `python -m collection_agent sync` + `status` work end-to-end against the fake client in tests and a real token manually; `chat` opens (no tools registered yet beyond `snapshot_status`/`start_sync`).

---

## Phase 3: User Story 1 — Analyze my collection (P1) 🎯 MVP

**Goal**: The seven collection analytics (genres %, top labels, top rated, by country, rarest/most-wanted, collection value, most expensive) answered conversationally from the snapshot.

**Independent Test** (spec US1): with a synced non-empty collection, ask each analytic question; answers are grounded, proportions reconcile to instance count, rankings ordered, bases/criteria stated; empty/private collection explains itself.

- [ ] T018 [US1] Implement snapshot serving guard in `collection-agent/src/collection_agent/tools/common.py`: shared wrapper giving every read tool the no-snapshot "sync required" signal, partial-data warning prefix, and stale/age disclosure (FR-003b/c; contracts/agent-tools.md §1 serving rules).
- [ ] T019 [US1] Implement `aggregate_by(attribute)` and `collection_value()` in `collection-agent/src/collection_agent/tools/analytics.py` (depends T011+T018): buckets `{value,count,pct}` + explicit unknown bucket + multi-valued counting note (FR-004/005/007/009, instance counting per FR-025); value returns Discogs min/median/max verbatim with basis.
- [ ] T020 [US1] Implement `top_n(basis, n)` in `collection-agent/src/collection_agent/tools/analytics.py` (after T019, same file): `community_rating` (avg + vote count, per clarification Q3), `most_expensive` (lowest_price basis, no-price records listed separately), `rarest` (settings-thresholded composite, criterion string, `excluded_missing_data` count — never falsely rare) per research R9 (FR-006/008/010).
- [ ] T021 [US1] Register US1 tools in the agent loop (`agent.py` dispatch + OpenAI schemas) and verify the rendered system prompt exposes them; snapshot_status already present from T017.
- [ ] T022 [P] [US1] Unit tests `collection-agent/tests/unit/test_analytics.py`: percentages sum to 100% of instances (single-valued) / disclosed per-value counting (multi-valued), unknown buckets present, duplicate instances counted, rating ranking respects vote counts shown, rarity thresholds + missing-data exclusion, value passthrough verbatim, **zero-instance snapshot: no division-by-zero, tools return an explicit empty-collection signal (never a 0%-bucket distribution)**.
- [ ] T023 [US1] Integration test `collection-agent/tests/integration/test_agent_loop.py` (stubbed LLM): each of the 7 analytics dispatches to the right tool and the narrated result carries warnings (partial snapshot case) and bases; no-snapshot case surfaces "sync required"; **synced-but-empty collection (0 instances)** is narrated as a limitation — never zeros presented as a normal distribution (US1 acceptance scenario 8, edge case №1).

**Checkpoint**: MVP — full quickstart §5 analytics conversation works against a real collection.

---

## Phase 4: User Story 2 — Browse and filter my records (P2)

**Goal**: Attribute-driven filtered listings (genre and genre+decade guaranteed; any registry attribute combinable).

**Independent Test** (spec US2): genre and genre+decade lists contain only matching records with artist/title/year + count; another attribute honors the same contract; unsupported attribute named; empty result stated.

- [ ] T024 [US2] Implement filter operations in `collection-agent/src/collection_agent/registry.py` (extends T011): per-kind ops (categorical `eq/in`, numeric `eq/lt/lte/gt/gte/between/missing`, text `contains/eq`), multi-valued any-match semantics, case/diacritic-insensitive categorical matching (es/en values), per contracts/agent-tools.md §3.
- [ ] T025 [US2] Implement `filter_records(criteria, limit)` in `collection-agent/src/collection_agent/tools/browse.py` (depends T018+T024): AND-combined criteria, `unsupported_criteria` naming unknown attributes/ops with the supported list (FR-013a), match identity (artist/title/year/format/folder), `count` + `truncated` (settings limit), empty-result explicit (FR-013b); store result refs in session for follow-ups.
- [ ] T026 [US2] Register `filter_records` in the agent loop + prompt; verify decade phrasing ("los 90", "the 90s") resolves via registry aliases to `decade` criteria.
- [ ] T027 [P] [US2] Unit tests `collection-agent/tests/unit/test_filters.py`: genre filter, genre+decade AND, a third attribute (label) same contract (SC-003), unsupported attribute → named + supported list, empty result, truncation flag, multi-value any-match, and the **extensibility proof (SC-003a)**: register a throwaway attribute (e.g. `catno`) in-test and assert it filters+aggregates with zero tool-code changes while all prior assertions still pass.

**Checkpoint**: US1 + US2 work independently; "mis discos de house de los 90" returns a correct list.

---

## Phase 5: User Story 3 — Media links from Discogs metadata (P2)

**Goal**: Music/video links for one record or a list, grouped per record, verbatim URIs, explicit "no links".

**Independent Test** (spec US3): a record with videos returns every link in its metadata; a list groups links per record; a link-less record says so.

- [ ] T028 [US3] Implement `media_links(record_refs)` in `collection-agent/src/collection_agent/tools/media.py` (depends T018): resolve refs by instance id, by fuzzy artist/title mention, or from the session's last listing ("those"/"esos"); per-record `{record, links[], none}` with URIs verbatim (FR-014/015/016; snapshot-schema invariant 6).
- [ ] T029 [US3] Register `media_links` in the agent loop + prompt; ensure last-listing session refs flow from `filter_records` results (works standalone too — direct record mention needs no prior US2 call).
- [ ] T030 [P] [US3] Unit tests `collection-agent/tests/unit/test_media.py`: links returned verbatim (no URL edits), grouping per record, explicit `none` flag, ref resolution (id / name mention / last listing), unknown record → clear not-found (no fabrication).

**Checkpoint**: US1–US3 all independently functional.

---

## Phase 6: User Story 4 — Organize records into folders (P3)

**Goal**: Move records to existing/new folders — live, per-item validated, and unreachable without the CLI's y/N confirmation.

**Independent Test** (spec US4): move a record to an existing folder and to a new named folder via conversation; change visible on discogs.com; `n` cancels cleanly; failures reported per item.

- [ ] T031 [US4] Implement `propose_moves(record_refs, target_folder_name, create_if_missing)` in `collection-agent/src/collection_agent/tools/organize.py` (depends T008+T018): resolve instances (session refs supported), live folder-name check (case-insensitive collision → offer existing; folder 0 rejected, folder 1 valid), build `WritePlan{plan_id}` into session state (expiring any prior plan), return human-readable summary — the **only** organize action exposed as an LLM tool (contracts/agent-tools.md §4).
- [ ] T032 [US4] Implement `execute_plan(plan_id)` in `collection-agent/src/collection_agent/tools/organize.py` (after T031, same file): create folder if planned, per-move live re-validation (instance still exists / current folder) then `move_instance`, per-item ok/failed(+reason) without aborting the rest (FR-020), snapshot patch or `mark_stale()`, all through the rate-limit governor. **Not registered in the LLM tool schema.**
- [ ] T033 [US4] Implement the runtime confirmation gate in `collection-agent/src/collection_agent/cli.py` (depends T031+T032): when a turn ends with a pending plan, the REPL itself renders the plan table and prompts `¿Confirmás? [y/N]`; only interactive `y` invokes `execute_plan`; anything else cancels the plan; results table rendered after execution (FR-019; research R8).
- [ ] T034 [P] [US4] Integration tests `collection-agent/tests/integration/test_organize_flow.py` (depends T012): propose→confirm→execute happy path (existing + new folder), cancel path leaves Discogs untouched, live re-validation failure → that item fails with reason while others proceed, folder-name collision path, and the **gate proof**: assert `execute_plan` is absent from the LLM tool schema and unreachable without the CLI prompt returning `y`.

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & cross-cutting

- [ ] T035 [P] Rewrite `collection-agent/README.md` for the two-package component: matcher (moved paths, unchanged behavior) + conversational agent (setup → sync → chat, env vars, exit codes), linking `specs/017-discogs-collection-agent/quickstart.md` and `docs/discogs_api_reference.md`.
- [ ] T036 [P] Secrets & log hygiene sweep: assert token never printed/logged (grep test or unit assertion on client logging paths), snapshot contains no credentials (snapshot-schema invariant 5), error messages never echo the token.
- [ ] T037 Run the full quickstart.md validation walkthrough (§7 table) against the real account: sync bounds (SC-006), analytics reconciliation (SC-001/002), filter spot-checks (SC-003), links verbatim (SC-004), move+confirm on discogs.com (SC-005), groundedness/basis statements (SC-007). Record results in `specs/017-discogs-collection-agent/quickstart.md` notes or PR description.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: T001 first and committed alone; T002 depends on T001 (paths); T003/T004 after T002, parallel with each other.
- **Phase 2 (Foundational)**: depends on Phase 1. Internal chain: T005/T006/T007 parallel → T008 (needs T005,T007) → T009 (needs T006) → T010 (needs T008,T009) → T011 (needs T006) → T012 (needs T006) → T013/T014 parallel → T015 (needs T010,T012) → T016 (needs T005,T011) → T017 (needs T009,T010,T016). **BLOCKS all user stories.**
- **Phases 3–6 (US1–US4)**: each depends only on Phase 2 — independently implementable/testable. US3's session-ref *integration* touches US2's listing refs but T028 works standalone (direct record mentions); US4 uses session refs the same way.
- **Phase 7 (Polish)**: after desired stories complete (T037 after all four).

### User story dependency notes

- **US1 (P1)**: none beyond Foundational. T018 (`tools/common.py` guard) is created here and reused by US2/US3/US4.
- **US2 (P2)**: none beyond Foundational + T018. Registry ops (T024) extend `registry.py` — coordinate if US1/US2 run in parallel (different functions, same file as T011 baseline).
- **Shared-file coordination**: the tool-registration tasks (T021, T026, T029, T031) all edit `agent.py`'s dispatch table + schemas. If stories run in parallel, land registrations sequentially (or keep each story's registration in its own tool module and have `agent.py` collect them) — do not merge concurrent edits to the dispatch table blindly.
- **US3 (P2)**: Foundational + T018; last-listing refs enhance but don't require US2.
- **US4 (P3)**: Foundational + T018; recommended last (only mutating path; relies on trust built by read stories).

### Parallel opportunities

```text
Phase 2: T005 ∥ T006 ∥ T007        then  T013 ∥ T014 (after T009/T003)
Phase 3: T022 ∥ T023-prep while T019→T020 sequential (same file)
Cross-story (after Phase 2 + T018): US2 (T024–T027) ∥ US3 (T028–T030) — different files
Phase 7: T035 ∥ T036
```

---

## Implementation Strategy

**MVP first**: Phases 1 → 2 → 3, then STOP and validate US1 against the real collection (quickstart §4–5). That alone delivers the core value proposition (spec: "the reason a user would adopt the agent").

**Incremental delivery**: each subsequent story is a complete demoable increment — US2 (lists), US3 (links), US4 (organize, the only write path — land last, after the read paths have proven the snapshot/live plumbing). Commit per task or logical group; T001 stands alone by design.

**Single-developer order**: T001→T037 as numbered. **Pair/parallel**: after Phase 2 + T018, US2 and US3 can proceed concurrently; US4 follows.
