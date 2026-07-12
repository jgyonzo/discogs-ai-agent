# Tasks: Scan Release & Master Selection

**Input**: Design documents from `/specs/026-scan-release-selection/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R9), data-model.md,
contracts/ (amendment-017-discogs-consumption-4, amendment-022-scan-api-3),
quickstart.md

**Tests**: included — this repo's workflow gates every feature on the
offline pytest suite (`cd collection-agent && pytest`, no live API calls);
test tasks precede or accompany implementation per story.

**Organization**: grouped by user story; each story is independently
implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1 (selected/master/alternatives), US2 (Discogs links), US3 (on-demand pressings)

## Path Conventions

All source paths are under `collection-agent/src/collection_agent/`, all
test paths under `collection-agent/tests/` (single-component feature per
plan.md — no other component is touched).

---

## Phase 1: Setup

No setup tasks — the component, its dependency manifest, and its test
harness already exist; the feature adds zero dependencies.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: settings, link builders, and wire-model extensions every story
renders or serves. No story work starts before these.

- [x] T001 Add `scan_versions_max` Settings field (alias
      `COLLECTION_AGENT_SCAN_VERSIONS_MAX`, default 25, data-model §5) in
      `collection-agent/src/collection_agent/settings.py`, with a
      default+alias unit test alongside the other scan-settings assertions
      in `collection-agent/tests/unit/test_scan_models.py`
- [x] T002 [P] Refactor `release_page_url` in
      `collection-agent/src/collection_agent/tools/common.py` to an
      id-based core (`release_page_url_for_id(settings, release_id)`) with
      the existing record-based signature delegating unchanged, and add
      `master_page_url(settings, master_id)`; extend
      `collection-agent/tests/unit/test_release_url.py` (existing 019
      assertions must pass with unchanged expected URLs)
- [x] T003 Extend `collection-agent/tests/unit/test_release_url.py` with a
      grep-style single-site guard: the `/release/{id}` and `/master/{id}`
      URL shapes each exist in exactly ONE `src/` code site
      (`tools/common.py`) — 020 precedent, contract Delta 1
- [x] T004 [P] Add additive `release_page_url: str | None = None` and
      `master_page_url: str | None = None` fields to `Candidate`, and the
      NEW `VersionsResponse` wire model (data-model §3), in
      `collection-agent/src/collection_agent/scan/models.py`; unit tests in
      `collection-agent/tests/unit/test_scan_models.py` (old Candidate
      constructions remain valid via defaults; VersionsResponse shape)
- [x] T005 Thread `settings` into `_candidate_from_result` in
      `collection-agent/src/collection_agent/scan/search.py` and populate
      both link fields via the T002 builders (`master_page_url` iff
      `master_id` — data-model §1 invariant); update its call sites in
      `_run_search`
- [x] T006 Pin eval comparability (research R9) in
      `collection-agent/tests/unit/test_scan_search.py`: for a fixed fake
      search payload, `find_candidates` returns byte-identical ordering and
      field values apart from the two new link fields; link fields correct
      against `DISCOGS_WEB_BASE_URL`

**Checkpoint**: settings + builders + wire models ready — user stories can
begin (US1/US2/US3 are independent from here).

---

## Phase 3: User Story 1 - Selected release, master, alternatives (Priority: P1) 🎯 MVP

**Goal**: results render as ONE designated selected release
(`candidates[0]`, contract Delta 2) with its master identity when present,
followed by the remaining candidates as selectable alternatives; selecting
an alternative adds THAT release through the unchanged confirmation flow;
identical presentation for photo scans and manual search (FR-001–004,
FR-014).

**Independent Test**: scan (or manually search) a record yielding ≥2
candidates → exactly one card is the selected match, master row shown iff
the release has a master, alternatives listed below, adding an alternative
adds the alternative with duplicate confirmation intact.

### Implementation for User Story 1

- [x] T007 [US1] Restructure the results rendering in
      `collection-agent/src/collection_agent/scan/static/index.html`: one
      shared card renderer; `candidates[0]` rendered as a visually
      prominent "Selected match" card with a master row (work identity =
      the candidate's own title, research R2) shown ONLY when the
      candidate carries a master; `candidates[1..]` under an "Other
      possibilities" heading; zero-candidate and manual-search flows keep
      existing behavior (same renderer ⇒ FR-014); add buttons and
      "None of these" unchanged
- [x] T008 [US1] Integration tests in
      `collection-agent/tests/integration/test_scan_server.py`: `/api/scan`
      and `/api/search` responses carry the new candidate link fields;
      single-candidate response has empty alternatives implied
      (`len(candidates)==1`); adding `candidates[1]` adds that release_id
      (not `candidates[0]`) with duplicate confirmation unchanged
- [x] T009 [P] [US1] New page guard test
      `collection-agent/tests/unit/test_scan_page_links.py`: `index.html`
      contains NO hardcoded Discogs host and never string-builds
      `/release/` or `/master/` paths — the page renders only server-built
      link fields (019 discipline / VII(a); contract Delta 1)

**Checkpoint**: US1 fully functional — MVP: designation + master identity +
alternative selection, still zero outbound links.

---

## Phase 4: User Story 2 - Open release/master on Discogs in a new tab (Priority: P2)

**Goal**: every displayed release (and the selected release's master)
offers a new-tab Discogs link, clearly distinct from the add action; links
never add, adds never navigate; the scan session survives tab-switching
(FR-005–009).

**Independent Test**: tap the release link on any card and the master link
on the selected card → correct Discogs pages open in new tabs; return to
the page → results intact, an add still works; tapping a link never
triggers an add.

### Implementation for User Story 2

- [x] T010 [US2] Add outbound anchors in
      `collection-agent/src/collection_agent/scan/static/index.html`: each
      card gets a "View release on Discogs ↗" `<a>` from
      `release_page_url`; the selected card's master row gets a
      "Master page ↗" `<a>` from `master_page_url`; all anchors
      `target="_blank" rel="noopener noreferrer"`, rendered only when the
      field is non-null (no fabricated links), structurally separate from
      add `<button>`s, no card-level click handler (FR-009)
- [x] T011 [P] [US2] Extend
      `collection-agent/tests/unit/test_scan_page_links.py`: every anchor
      built from a `*_page_url` field carries `target="_blank"` and
      `rel="noopener noreferrer"`; add buttons carry no `href`/navigation
- [x] T012 [US2] Integration tests in
      `collection-agent/tests/integration/test_scan_server.py`: link-field
      correctness — `release_page_url == {base}/release/{release_id}` for
      every served candidate, `master_page_url == {base}/master/{master_id}`
      iff `master_id` else `None` (masterless candidate case), honoring an
      overridden `DISCOGS_WEB_BASE_URL`

**Checkpoint**: US1 + US2 — the full default results experience.

---

## Phase 5: User Story 3 - On-demand other pressings of the master (Priority: P3)

**Goal**: an explicit "Show other pressings" action on the selected card
fetches the master's versions (ONE governed Discogs request, only on tap),
shows them as additional alternatives with identical duplicate/link/add
semantics, honest empty/failure/truncation messaging; scans without the
tap issue zero extra requests (FR-010–013, SC-005/006).

**Independent Test**: with fake versions scripted, request
`/api/master-versions` for a displayed master → mapped, deduped candidates
return and become addable; unknown master → 403; Discogs failure → 502
with the cycle still usable; on the page, the button appears only when the
selected release has a master.

### Implementation for User Story 3

- [x] T013 [P] [US3] Add `get_master_versions(master_id, per_page)` to
      `collection-agent/src/collection_agent/discogs/client.py`
      (`GET /masters/{id}/versions`, `page=1`, governed `_get_json` path —
      contract amendment-017-4); unit tests in
      `collection-agent/tests/unit/test_discogs_client_scan.py` (path,
      params, error mapping)
- [x] T014 [P] [US3] Grow `FakeDiscogsClient` in
      `collection-agent/tests/fixtures/fake_client.py` with scriptable
      master-versions responses (payload queue + raise-on-demand +
      call/param recording, matching its search/add scripting style)
- [x] T015 [US3] Add `candidates_from_versions(payload, master_id,
      settings, duplicate_checker, exclude_ids)` to
      `collection-agent/src/collection_agent/scan/search.py` implementing
      the verbatim mapping + dedup rule of data-model §2; unit tests in
      `collection-agent/tests/unit/test_scan_search.py` (field-by-field
      verbatim audit incl. `str(released)`, whole-`format` wrapping,
      `discogs_uri=None`, requested `master_id`, duplicate overlay,
      dedupe drops already-registered ids incl. the selected release)
- [x] T016 [US3] In `collection-agent/src/collection_agent/scan/server.py`:
      track candidate master ids on `_CycleContext` (data-model §4),
      refreshed by `_register`
- [x] T017 [US3] Add `GET /api/master-versions` (sync-def handler) in
      `collection-agent/src/collection_agent/scan/server.py` per contract
      Delta 3: gates in order (unknown/closed cycle → 409 `superseded`;
      master not in cycle's set → 403 `unknown_master`), generation
      captured but NOT bumped, fetch via T013 capped by
      `settings.scan_versions_max`, map via T015 excluding the cycle's
      registered ids, register results into session allowlist + cycle
      titles, return `VersionsResponse` with verbatim `total_versions` and
      honest empty `message`; `DiscogsError` → 502 `discogs_unavailable`
      with zero state effects
- [x] T018 [US3] Integration tests in
      `collection-agent/tests/integration/test_scan_server.py`: happy path
      (mapped fields, dedupe, `total_versions`); 403 unknown master; 409 on
      closed cycle; 409 when a newer scan supersedes an in-flight fetch
      (fake-client hook) with no allowlist pollution; 502 on scripted
      failure leaves the cycle addable; add-from-version succeeds through
      the normal gate incl. duplicate confirmation and journals `added`
      with the cycle's original source; a versions fetch does NOT
      auto-close the cycle (selected release still addable after);
      scan-only session issues zero versions calls (fake-client call
      recording — SC-006)
- [x] T019 [US3] Wire the page in
      `collection-agent/src/collection_agent/scan/static/index.html`:
      "Show other pressings" button on the selected card (only when
      `master_page_url` non-null), disabled while fetching; append an
      "Other pressings of this master" section via the SAME card renderer
      (links + add + dup badges identical); honest inline messages for
      empty result / 502 / "showing N of T" when `total_versions` exceeds
      the shown count; section resets with everything else on a new
      scan/search (supersede semantics unchanged)

**Checkpoint**: all three stories functional and independently testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T020 [P] Update `collection-agent/README.md`: scan-page section
      (selected/master/alternatives, new-tab links, on-demand pressings)
      and the new `COLLECTION_AGENT_SCAN_VERSIONS_MAX` env var
- [x] T021 Full-suite verification: `cd collection-agent && pytest` green,
      `git diff --stat` confirms zero changes under
      `collection-agent/src/collection_agent/eval/` and to
      `scan/vision.py` (research R9); record the new test count
- [x] T022 Write the merged-state CLAUDE.md block for 026 on this branch
      (single-PR flow — feature + post-merge CLAUDE.md state in ONE PR)
- [x] T023 Owner-only live validation: run
      `specs/026-scan-release-selection/quickstart.md` checklist
      SC-001..SC-006 on the phone against live Discogs (stays open past
      merge if deferred, 022/023 precedent)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: T001–T006 block all stories.
  T005 depends on T002+T004; T006 depends on T005; T001–T004 can start
  immediately (T002∥T004∥T001).
- **US1 (Phase 3)**: after Phase 2. T008 depends on T005; T007/T009
  independent of each other.
- **US2 (Phase 4)**: after Phase 2. T010 builds on T007's renderer (run
  US1 first when sequential); T011 after T010; T012 only needs T005.
- **US3 (Phase 5)**: after Phase 2. T013∥T014 first; T015 needs T004+T005;
  T016 before T017; T017 needs T013+T015+T016; T018 needs T014+T017;
  T019 needs T017 (and T007's renderer).
- **Polish (Phase 6)**: T020 anytime; T021 after all code tasks; T022
  before the PR opens; T023 owner-only, after merge-ready build.

### User Story Dependencies

- US1, US2, US3 are mutually independent at the server level (all consume
  Phase 2 outputs). On the single static page, US2's anchors and US3's
  button attach to US1's card renderer — sequential P1→P2→P3 is the
  natural solo order.

### Parallel Opportunities

- Phase 2: T001 ∥ T002 ∥ T004.
- US3: T013 ∥ T014 while another track does US1/US2 page work.
- T009 ∥ T007; T020 ∥ any code task.

---

## Parallel Example: User Story 3

```bash
# After Phase 2, launch simultaneously:
Task: "get_master_versions in discogs/client.py + tests (T013)"
Task: "FakeDiscogsClient versions scripting in tests/fixtures/fake_client.py (T014)"
# then T015 → T016 → T017 → T018/T019
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 2 (T001–T006) → foundation.
2. Phase 3 (T007–T009) → **stop and validate**: selected/master/
   alternatives on the phone, alternative add works. Demoable.

### Incremental Delivery

1. + US2 (T010–T012) → verify links live → the complete default view.
2. + US3 (T013–T019) → verify on-demand pressings with fakes, then live.
3. Polish (T020–T023); T023 stays owner-only.

---

## Notes

- Every add path reuses the 022 write gate — no task may introduce a
  second add/confirmation surface.
- The vision prompt, ladder order, normalization, and `eval/` are
  out-of-bounds for all tasks (research R9; 023 AST guard).
- Commit after each task or logical group (repo convention: split by
  concern).
