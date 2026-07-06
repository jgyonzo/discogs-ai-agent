# Tasks: YouTube Playlist Integration

**Input**: Design documents from `/specs/020-youtube-playlist-integration/`
**Prerequisites**: plan.md, spec.md (re-scoped 2026-07-06: anonymous play links), research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — the contracts specify unit-tested invariants (completeness partition, chunk discipline, link integrity), and offline pytest coverage with no network calls is the repo norm (146 tests at branch time).

**Organization**: Tasks are grouped by user story. All paths are relative to the repo root; all source work is inside `collection-agent/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single existing component: `collection-agent/src/collection_agent/`, tests in `collection-agent/tests/`. Run tests with `cd collection-agent && pytest`.

---

## Phase 1: Setup

**Purpose**: Configuration surface for the feature (Constitution VII(a))

- [ ] T001 Add settings fields `youtube_web_base_url` (alias `YOUTUBE_WEB_BASE_URL`, default `https://www.youtube.com`) and `youtube_playlist_max_ids` (alias `YOUTUBE_PLAYLIST_MAX_IDS`, default `50`, int) to `collection-agent/src/collection_agent/settings.py`, grouped with the existing `discogs_web_base_url` comment style (019 precedent: web base ≠ API base; here there is no API at all)

**Checkpoint**: `Settings()` loads with defaults; no new env vars required (SC-004).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The pure link-mechanics module every story depends on

- [ ] T002 Create `collection-agent/src/collection_agent/youtube_links.py` with `video_id_from_uri(uri: str) -> str | None` (deterministic parser: `watch?v=`, `youtu.be/`, `shorts/`, `embed/`, extra query params tolerated; anything else → `None` — research R2 / data-model §2) and `build_watch_videos_url(video_ids: list[str], base_url: str) -> str` (`{base}/watch_videos?video_ids=<comma-joined>` — the ONLY place this URL shape exists, mirroring 019's `release_page_url` discipline; raise/assert on empty list and on > cap handled by callers)
- [ ] T003 [P] Unit tests in `collection-agent/tests/unit/test_youtube_links.py`: parser accepts all four URL shapes (with/without extra params) and returns `None` for non-YouTube hosts, malformed URIs, and missing ids; builder joins ids in order onto the given base and never appears elsewhere in the codebase (grep-style assertion like `test_release_url.py`'s single-source check, if present there)

**Checkpoint**: `pytest tests/unit/test_youtube_links.py` green — pure functions ready for all stories.

---

## Phase 3: User Story 1 — Playable playlist link from conversation records (Priority: P1) 🎯 MVP

**Goal**: Two-prompt journey ends with click-to-play link(s) built only from stored videos, with skips reported and honest save-on-site guidance (FR-001/002/003/004/007/008/009/010).

**Independent Test**: Filter records, then "create a youtube playlist called discogs-minimal and insert the links" → answer contains a `watch_videos` URL whose ids all trace to the listed records' stored URIs, plus skip reasons and the save hint; opening it in a browser plays the videos in order (quickstart SC-001).

- [ ] T004 [US1] Create `collection-agent/src/collection_agent/tools/playlist.py`: `PlaylistLinksArgs` (`record_refs: list[str]`, `use_last_listing: bool`, `suggested_name: str | None`; `videos_per_record` arrives in US3) and `make_playlist_tools(settings, store) -> list[ToolDef]` registering read-only `playlist_links`; resolution via `from collection_agent.tools.media import _resolve` (exact `organize.py` precedent) and the `load_for_serving`/`with_warnings` envelope from `tools/common.py`; `no_records_resolved` error payload when nothing resolves (contract §2.1)
- [ ] T005 [US1] In `collection-agent/src/collection_agent/tools/playlist.py`, implement video assembly: per resolved record parse each stored `MediaLink.uri` with `video_id_from_uri`; records with no parseable video → `skipped_records` entries (`no_videos` / `unresolvable_uri`); duplicate video ids collapse to first listing-order occurrence + `duplicate_notes` entry; enforce the completeness partition (every resolved record lands in exactly one of covered ∪ skipped — data-model §1)
- [ ] T006 [US1] In `collection-agent/src/collection_agent/tools/playlist.py`, implement the payload (data-model §1): when usable videos ≤ `settings.youtube_playlist_max_ids`, one link via `build_watch_videos_url` with `index`/`video_count`/`records`/`label`, plus `link_count`, `total_videos`, `covered_record_count`, `suggested_name` echo, fixed `save_hint`, and `detail` stating nothing was created or saved; when videos exceed the cap, return an explicit `over_capacity` warning payload naming the counts and NO link (honest interim behavior — replaced by US2 chunking; silent truncation forbidden); all-skipped ⇒ `links: []` + explanatory detail, never an empty URL
- [ ] T007 [US1] Register the tool: add a `playlist_links` block to `_register_story_tools` in `collection-agent/src/collection_agent/cli.py` (import `make_playlist_tools` from `collection_agent.tools.playlist`, register like the `make_media_tools` block)
- [ ] T008 [US1] Amend `collection-agent/src/collection_agent/prompts/system.md` per contract delta 10: extend ground rule 1 (play links come ONLY from the `playlist_links` payload; never assemble a YouTube URL from ids) and rephrase ground rule 6 (playlist requests supported via play links; saving/naming/editing playlists in the owner's account and YouTube search remain unsupported; relay `save_hint` + `suggested_name`; never claim a playlist was created/saved/named; records without usable videos are skipped, never substituted)
- [ ] T009 [P] [US1] Unit tests in `collection-agent/tests/unit/test_playlist_links.py` (fixture style of `test_media.py`): resolution semantics (refs, name mentions, `use_last_listing`, `not_found`), skip reasons both kinds, dedup-first-occurrence with note, all-skipped ⇒ no links, `no_records_resolved`, single-link payload fields (label, totals, `suggested_name`, `save_hint`, `detail`), over-capacity interim warning contains counts and no URL, completeness partition holds on every case (SC-003), warnings envelope passthrough (stale/partial)
- [ ] T010 [P] [US1] Prompt-rule tests in `collection-agent/tests/unit/test_playlist_prompt.py` (pattern of the 019 prompt assertions in `test_release_url.py`): rendered system prompt names `playlist_links` as the only play-link source, forbids URL assembly from identifiers, contains the save-on-site obligation, and no longer lists YouTube playlists as unsupported while still listing YouTube search; `{attribute_block}` remains the only schema prose (VII(b) analog)
- [ ] T011 [US1] Integration test in `collection-agent/tests/integration/test_agent_playlist.py` (stub-LLM style of `test_agent_loop.py`): a turn whose stub calls `playlist_links` with `use_last_listing` after a `filter_records` turn returns the link payload to the model; assert the tool is registered, is NOT gated (no pending plan created), and the session's `last_listing_instance_ids` is consumed, not modified

**Checkpoint**: `cd collection-agent && pytest` fully green — US1 is the shippable MVP (small slices; large slices get the honest over-capacity warning until US2).

---

## Phase 4: User Story 2 — Large slices: chunked, labeled links (Priority: P2)

**Goal**: Requests exceeding one link's capacity return multiple record-aligned, labeled links covering every usable video — no silent truncation (FR-005). This replaces US1's interim over-capacity warning.

**Independent Test**: Request a slice whose stored videos exceed the cap (e.g. 10+ video-dense records); verify each link ≤ cap, labels' record ranges correct, links disjoint and jointly complete, and a within-cap request still yields exactly one link.

- [ ] T012 [US2] Add `chunk_record_videos(per_record_ids: list[tuple[record, list[str]]], cap: int) -> list[chunk]` to `collection-agent/src/collection_agent/youtube_links.py`: listing order preserved; chunk boundaries never split a record unless that single record alone exceeds the cap (then split with a note flag); each chunk carries its records and video count (research R3)
- [ ] T013 [US2] In `collection-agent/src/collection_agent/tools/playlist.py`, replace the `over_capacity` interim payload with chunked links: one `links[]` entry per chunk (`index`, `label` "link N — records i–j (K videos)", per-link `records`), totals across links, split-record notes into `duplicate_notes`-style notes; single-chunk requests keep producing exactly one unlabeled-range-free link (no gratuitous chunking — US2 acceptance 3)
- [ ] T014 [P] [US2] Property-style unit tests in `collection-agent/tests/unit/test_youtube_links.py` (chunker) and `collection-agent/tests/unit/test_playlist_links.py` (payload): every chunk ≤ cap; chunks disjoint; union equals the deduped usable-video set; order preserved; record-aligned boundaries; oversized single record splits with note; ≤-cap input yields one chunk; multi-link payload labels match actual contents; completeness partition still holds across links (SC-003)

**Checkpoint**: pytest green; a 10-record video-dense request yields correctly labeled multi-link answers.

---

## Phase 5: User Story 3 — One video per record (Priority: P3)

**Goal**: Sampler mode — `videos_per_record="first"` takes only each record's first stored video (FR-006).

**Independent Test**: Same slice with and without the instruction; first-mode link has exactly one video per video-bearing record (the first stored one); default remains all videos.

- [ ] T015 [US3] Add `videos_per_record: Literal["all","first"] = "all"` to `PlaylistLinksArgs` in `collection-agent/src/collection_agent/tools/playlist.py` (Field description telling the LLM when to use `first`: "one track per record" style requests); apply selection before dedup/chunking; echo the effective mode in the payload
- [ ] T016 [P] [US3] Unit tests in `collection-agent/tests/unit/test_playlist_links.py`: first-mode includes exactly the first stored video of each video-bearing record in listing order; skip reporting unchanged; omitted arg defaults to `all` (pydantic default, not `model_fields_set` — no 018-style ambiguity here); dedup and chunking operate on the selected set

**Checkpoint**: pytest green; "just one track per record" produces a single ~50-record-capable link.

---

## Phase 6: Polish & Live Verification

**Purpose**: Whole-suite health and the owner-run success-criteria replays (018/019 precedent)

- [ ] T017 Run the full suite `cd collection-agent && pytest` and fix any fallout; confirm zero network calls in tests (SC-004 groundwork) and note the new test count for the eventual CLAUDE.md post-merge update
- [ ] T018 Live replay (owner-run, quickstart): SC-001 — two-prompt journey, click a returned link, verify play order matches the listing and the site-side "Save playlist" works; SC-002 — audit every `video_ids` entry in the emitted links against the records' `media_links` output (zero unexplained ids, zero non-payload YouTube URLs in answers); record results as a spec addendum if any deviation surfaces (018 precedent)
- [ ] T019 SC-004 zero-setup check: confirm no Google/YouTube configuration exists anywhere (no new deps in `collection-agent/pyproject.toml`, no new required env vars) and give `specs/020-youtube-playlist-integration/quickstart.md` an accuracy pass against the implemented behavior

---

## Dependencies

```text
Phase 1 (T001 settings)
  └─► Phase 2 (T002 helpers; T003 tests [P] after T002)
        └─► Phase 3 / US1 (T004 → T005 → T006 → T007; T008 anytime; T009/T010 [P] after T006/T008; T011 after T007)
              └─► Phase 4 / US2 (T012 → T013; T014 [P] after T013)   ← replaces US1's interim over-capacity warning
              └─► Phase 5 / US3 (T015; T016 [P] after T015)          ← independent of US2
                    └─► Phase 6 (T017 → T018 → T019)
```

- US2 and US3 are independent of each other; both depend only on US1's tool module.
- T008 (prompt) has no code dependency and can be done in parallel with T004–T007.

## Parallel Execution Examples

- After T002: **T003** alongside starting **T004**.
- Within US1: **T008** (prompt) parallel with **T004–T006** (tool code); then **T009 + T010** in parallel (different test files).
- After US1: **US2 (T012–T014)** and **US3 (T015–T016)** can proceed in parallel — different concerns, small overlap in `playlist.py` (coordinate the selection-before-chunking order from T015).

## Implementation Strategy

**MVP = Phase 1–3 (US1)**: shippable on its own — small slices get a working play link; oversized slices get an honest warning instead of a wrong answer. Then US2 (chunking makes large slices first-class — the normal case at 7.5 videos/record), then US3 (sampler mode), then the live-verification gate (T018) before merge, per the 018/019 replay precedent.
