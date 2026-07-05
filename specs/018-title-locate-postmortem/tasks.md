# Tasks: Title-Aware Record Location (Postmortem)

**Input**: Design documents from `/specs/018-title-locate-postmortem/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/amendment-017-agent-tools.md, quickstart.md

**Tests**: Included — the spec explicitly requires them (SC-004: new tests
for title matching and prompt guidance; full existing suite stays green).
Written first, verified failing, per this repo's workflow.

**Organization**: Grouped by user story. All work is inside the
`collection-agent/` component; no other component is touched.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 = title attribute; US2 = presence-check guidance

## Path Conventions

Component root: `collection-agent/` (own `pyproject.toml`; run tests with
`cd collection-agent && pytest`). Source under `src/collection_agent/`,
tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm a green baseline so regressions are attributable.

- [ ] T001 Run the full existing suite (`cd collection-agent && pytest`) and record the passing count (~106) as the baseline; no code changes

---

## Phase 2: Foundational (Blocking Prerequisites)

*None.* The registry framework (`text` kind in `OPS_BY_KIND`,
fold()-based `matches()`), `filter_records`, and the prompt renderer all
exist (017). This feature only declares into them — user stories can begin
immediately after T001.

---

## Phase 3: User Story 1 - Locate a record by artist and title (Priority: P1) 🎯 MVP

**Goal**: `title` is a filterable attribute — substring (`contains`) and
exact (`eq`) matching, case/diacritic-insensitive, AND-combinable with
artist, auto-rendered into the prompt attribute block (FR-001…FR-005,
FR-007).

**Independent Test**: `pytest tests/unit/test_registry.py -k title` plus
the filter test — a multi-record artist's record is findable by
artist + title substring without reading unrelated rows; `title` appears
in `render_attribute_block()` output.

### Tests for User Story 1 (write first, verify they FAIL) ⚠️

- [ ] T002 [P] [US1] Add title-spec unit tests in `collection-agent/tests/unit/test_registry.py`: registry resolves `title`/`titulo`/`título`/`titles` to a text-kind spec with ops `(contains, eq)`; `matches()` cases — `contains` substring hit and miss, case folding ("FOCUS ON" vs "Focus On Guido Schneider"), diacritic folding ("espaco" matches "Espaço E Tempo"), `eq` exact-modulo-folding, empty-title record matches nothing (extract → None), unsupported op (e.g. `between`) raises `UnsupportedOp`
- [ ] T003 [P] [US1] Add filter-tool tests in `collection-agent/tests/unit/test_filters.py`: `filter_records` with `artist eq "Guido Schneider" AND title contains "focus on"` returns only the matching record from a snapshot where that artist has several records (incident fixture shape); title-only criterion works across the whole collection; a substring present only in the artist name does NOT match on `title` ("Styleways" by Guido Schneider is excluded for `title contains "guido"` while "Focus On Guido Schneider" matches); `title` appears in `render_attribute_block()` output (FR-005)

### Implementation for User Story 1

- [ ] T004 [US1] Add the `title` `AttributeSpec` to `build_registry()` in `collection-agent/src/collection_agent/registry.py` per data-model §1: `name="title"`, aliases `("título", "titulo", "titles", "títulos", "titulos")`, kind `"text"`, `extract=lambda r: r.title or None`, `unknown_label="unknown title"`, description one-liner — one declaration, no other registry/tool code changes (SC-003a)
- [ ] T005 [US1] Run `cd collection-agent && pytest` — T002/T003 tests now pass; baseline suite still green (FR-008)

**Checkpoint**: US1 delivers the MVP — the incident's P1 failure
("Focus On Guido Schneider" unfindable) is now mechanically impossible to
reproduce via artist + title filtering.

---

## Phase 4: User Story 2 - Presence checks never silently truncate (Priority: P2)

**Goal**: The assistant's standing instructions make artist+title
filtering, format-noise stripping, full-cap listings, and artist-only
retry the default presence-check procedure (FR-006).

**Independent Test**: A test asserts the rendered system prompt contains
the locate-a-record guidance; manual replay of the two incident queries
per quickstart.md.

### Tests for User Story 2 (write first, verify they FAIL) ⚠️

- [ ] T006 [US2] Add a prompt-guidance test (in `collection-agent/tests/integration/test_agent_loop.py`, or `tests/unit/test_registry.py` if a render-only unit test fits the existing layout better): `render_system_prompt(build_registry(settings))` output contains the locate-a-record section covering all four FR-006 rules (artist + title-substring filtering; format-noise stripping; no reduced limit on presence checks; artist-only retry before declaring absence) — assert on stable phrases, not exact prose

### Implementation for User Story 2

- [ ] T007 [US2] Add a "Locating a specific record" procedural section to `collection-agent/src/collection_agent/prompts/system.md` per data-model §2 (exactly the four FR-006 rules; procedure only — no attribute inventory, which stays in the registry-rendered `{attribute_block}`; keep the existing tone/format of the Answer style section)
- [ ] T008 [US2] Run `cd collection-agent && pytest` — T006 passes; full suite green (FR-008)

**Checkpoint**: Both stories independently testable; incident replay
should now locate all four records.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T009 [P] Check `collection-agent/README.md` for any attribute list or filtering examples and update if `title` belongs there (runbook accuracy only; no new attribute prose that duplicates the registry)
- [ ] T010 Verify SC-003 mechanically: `git diff main -- collection-agent/src/collection_agent/tools/` is empty (no tool-code edits) and the registry diff is a single `AttributeSpec` block plus tests/prompt
- [ ] T011 Run quickstart.md validation: full suite (`cd collection-agent && pytest`), attribute-block grep, and — if a live snapshot is present — replay the four incident queries in `python -m collection_agent chat` expecting zero false "not in your collection" answers (SC-001)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none — start immediately
- **Foundational (Phase 2)**: empty — no blocker
- **US1 (Phase 3)**: after T001; tests T002/T003 before implementation T004
- **US2 (Phase 4)**: after T001; independent of US1 files (different
  source file), but its *behavioral* value assumes US1 is in (guidance
  references title filtering) — implement in priority order
- **Polish (Phase 5)**: after US1 + US2

### Parallel Opportunities

- T002 ∥ T003 (different test files)
- US2's T006/T007 touch different files than US1's T004 and could proceed
  in parallel after T001 if staffed; solo execution should stay in
  priority order
- T009 ∥ T010 (different surfaces)

---

## Implementation Strategy

MVP = Phase 3 (US1): the registry entry alone makes the incident records
locatable by anyone driving `filter_records` correctly. US2 then makes
correct driving the assistant's default. Commit per phase (docs already
committed at spec/plan boundaries; implementation commits split: US1
code+tests, US2 prompt+test, polish).
