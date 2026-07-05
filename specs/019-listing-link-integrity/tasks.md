# Tasks: Listing Link Integrity

**Input**: Design documents from `/specs/019-listing-link-integrity/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/amendment-017-agent-tools.md, quickstart.md

**Tests**: Included — the spec's success criteria (SC-002/SC-003/SC-004) and
research R5 explicitly define the automated test surface; repo norm (017/018)
is tests-first, no live API calls.

**Organization**: Grouped by user story. All source paths are under
`collection-agent/` (single component; plan gate).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (page-link asks), US2 (no invented links in listings),
  US3 (media links preserved)

## Phase 1: Setup

**Purpose**: Confirm the 018 baseline before touching payloads.

- [X] T001 Run the baseline suite (`cd collection-agent && pytest`) and confirm all 131 tests green on branch `019-listing-link-integrity`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The settings field and shared URL helper every story's payload
change depends on (research R2/R3; data-model §1–2).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add `discogs_web_base_url: str` (alias `DISCOGS_WEB_BASE_URL`, default `https://www.discogs.com`, no trailing slash) to `collection-agent/src/collection_agent/settings.py`, alongside the existing API-base field
- [X] T003 [P] Write failing unit tests for the URL helper in `collection-agent/tests/unit/test_release_url.py`: fixture record with `instance_id != release_id`; assert the URL equals `{settings.discogs_web_base_url}/release/{release_id}`, embeds `release_id`, never contains the `instance_id` digits (data-model §2 id-space invariant); assert env override via `DISCOGS_WEB_BASE_URL`
- [X] T004 Implement `release_page_url(settings, record) -> str` in `collection-agent/src/collection_agent/tools/common.py` (no URL literals outside the settings default — Constitution VII(a)); make T003 pass (depends on T002, T003)

**Checkpoint**: Helper green — payload changes can proceed in any story order.

---

## Phase 3: User Story 1 — Ask for a record's Discogs page (Priority: P1) 🎯 MVP

**Goal**: A "give me the Discogs link" ask is answered from a genuine
tool-provided `release_url` in the `filter_records` listing (including 018
fallback listings), backed by the extended ground rule.

**Independent Test**: quickstart replay prompt 1 — locate a record, ask for
its link; the URL shown is the payload's `release_url`, wrong-id-space URLs
impossible by construction (unit-tested).

### Tests for User Story 1

- [X] T005 [P] [US1] Write failing unit tests in `collection-agent/tests/unit/test_filters.py`: every `matches[]` entry carries `release_url` per data-model §3.1; `fallback_matches[]` entries (zero-match text+non-text path) carry it too; id-space assertion with `instance_id != release_id`; `instance_id` key/type unchanged
- [X] T006 [P] [US1] Write failing prompt-surface test in `collection-agent/tests/integration/test_agent_loop.py`: rendered system prompt contains the link-sourcing rule (page links only from `release_url`; media links only from `media_links`; URL construction from any identifier forbidden — contract delta 7)

### Implementation for User Story 1

- [X] T007 [US1] Add `"release_url": release_page_url(settings, rec)` to `_display` in `collection-agent/src/collection_agent/tools/browse.py` (single point — covers `matches` and `fallback_matches`; thread `settings` if not already in scope); make T005 pass
- [X] T008 [US1] Extend ground rule 1 in `collection-agent/src/collection_agent/prompts/system.md` with the delta-7 sentences (page link only from `release_url`; media only from `media_links`; never build a URL from `instance_id` or any identifier, including for absent records); make T006 pass
- [X] T009 [US1] Checkpoint run: `cd collection-agent && pytest` — full suite green; SC-004 regression check (move/ordinal/last-listing tests untouched and passing)

**Checkpoint**: US1 fully functional — link asks answerable from tool output.

---

## Phase 4: User Story 2 — Listings never carry invented links (Priority: P2)

**Goal**: Ranking listings (`top_n`) carry `release_url` too, and a
loop-level invariant pins every listing-producing tool result.

**Independent Test**: quickstart replay prompts 2–3 — filtered listing and
ranking with link follow-ups; every Discogs URL in answers appears verbatim
in the session's tool output.

### Tests for User Story 2

- [X] T010 [P] [US2] Write failing unit tests in `collection-agent/tests/unit/test_analytics.py`: `top_n` entries for every basis carry `release_url` per data-model §3.2, id-space asserted, existing basis fields unchanged
- [X] T011 [P] [US2] Write failing integration test in `collection-agent/tests/integration/test_agent_loop.py`: every listing-shaped tool payload (`filter_records` matches + fallback_matches, `top_n`) carries `release_url` on each per-record entry (contract delta 6 invariant)

### Implementation for User Story 2

- [X] T012 [US2] Add `"release_url": release_page_url(settings, rec)` to `_display` in `collection-agent/src/collection_agent/tools/analytics.py` (thread `settings` if not already in scope); make T010 and T011 pass

**Checkpoint**: US1 + US2 — all filter/ranking listing shapes link-complete.

---

## Phase 5: User Story 3 — Media links remain the source for music/video links (Priority: P3)

**Goal**: `media_links` per-record entries gain `release_url` without
disturbing the verbatim-URI + explicit-`none` answer shape; the payload note
distinguishes the release page from playable media.

**Independent Test**: ask for a record's music links — URIs verbatim, no-media
records get the explicit statement; the release page is offered only as the
record's page (quickstart replay prompt 2, media half).

### Tests for User Story 3

- [X] T013 [P] [US3] Write failing unit tests in `collection-agent/tests/unit/test_media.py`: each `per_record` entry carries `release_url` per data-model §3.3 (id-space asserted); `links[]` uri/title/duration_s stay verbatim; `none` flag semantics unchanged; note text distinguishes release **page** from playable media

### Implementation for User Story 3

- [X] T014 [US3] Add `release_url` to `per_record` entries and update the payload `note` in `collection-agent/src/collection_agent/tools/media.py` (contract deltas 6+8); make T013 pass

**Checkpoint**: All three stories independently green.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T015 Full-suite gate: `cd collection-agent && pytest` — record the new test count (was 131) and confirm zero pre-existing tests modified in their expectations (SC-003)
- [X] T016 [P] Cross-check `specs/019-listing-link-integrity/contracts/amendment-017-agent-tools.md` deltas 6–8 against the implementation (field name, settings alias/default, helper location, prompt sentences); fix any drift in the same change set
- [X] T017 Execute the quickstart replay (`specs/019-listing-link-integrity/quickstart.md`, live snapshot, chat) — prompts 1–4; SC-001 gate: zero `discogs.com` URLs in assistant answers absent from tool results. If any invented URL survives, record a replay-postmortem addendum in `specs/019-listing-link-integrity/spec.md` (018 precedent) before closing
- [X] T018 Manual SC-002 spot check: open one returned `release_url` in a browser and confirm it resolves to the correct release page (never automated)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately
- **Foundational (Phase 2)**: after T001 — BLOCKS all user stories (T004 is the gate)
- **User Stories (Phases 3–5)**: each depends only on Phase 2; independent of each other (different tool files); priority order US1 → US2 → US3 when executed sequentially
- **Polish (Phase 6)**: after all desired stories; T017/T018 need a synced live snapshot

### Within Each User Story

- Tests written first and failing before implementation (T005/T006 → T007/T008; T010/T011 → T012; T013 → T014)
- T008 (prompt) is independent of T007 (payload) — both required for US1's replay to pass

### Parallel Opportunities

- T002 ∥ T003 (different files)
- T005 ∥ T006 (different test files); T010 ∥ T011 ∥ T013 across stories once Phase 2 is done
- US1/US2/US3 implementation tasks touch disjoint tool files (browse/analytics/media) — fully parallelizable after T004
- T016 ∥ T015

---

## Implementation Strategy

**MVP = Phase 1 + 2 + 3 (US1)**: the incident's direct ask — "give me the
link" — answered with a real URL, ground rule updated, id-space bug
impossible in the primary listing shape. Stop, run the suite, replay
quickstart prompt 1.

Then increment: US2 (rankings + loop invariant) → US3 (media payload) →
Polish (full gate + replay + contract cross-check). Commit after each task
or logical group (repo norm: split commits by concern).
