# Specification Quality Checklist: Classifier carryover — multi-turn follow-up questions stop getting rejected

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-11
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
  - **Caveat (intentional)**: this is a structural-bugfix spec where naming surgical sites is necessary for the back-fill to anchor (`router.md`, `_carryover.py:46`, `state.py:23–24`). Same precedent as 013 + 014. The spec deliberately leaves the implementation choice between "router-builds-carryover" and "new prelude node" OPEN (Out of Scope explicitly defers Option B). The HOW is not prescribed.
- [x] Focused on user value and business needs
  - US1 directly frames against the user-facing bug (the two failing follow-ups in thread `9214f7fb-...`).
  - US2 frames against operator triage (distinguishing first-turn from short-circuit cases).
- [x] Written for non-technical stakeholders
  - Two clearly-numbered user stories with given/when/then scenarios + plain-English "Why this priority" sections.
  - The technical "Context" section is labeled and can be skipped.
- [x] All mandatory sections completed
  - User Scenarios & Testing ✓ (US1, US2, Edge Cases)
  - Requirements ✓ (FR-001 through FR-013)
  - Success Criteria ✓ (SC-001 through SC-006)
  - Assumptions ✓ + Out of Scope ✓ + Dependencies ✓

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
  - One open implementation choice (build carryover in router vs prelude node) is explicitly left flexible in the spec text, not deferred as a clarification.
  - One open persistence-shape choice (first-turn = `null` vs `turn_count: 0`) is explicitly left flexible in FR-008.
  - Both are deliberate flexibility, not clarifications.
- [x] Requirements are testable and unambiguous
  - Each FR names a specific file, function, line range, or placeholder name and what changes about it.
  - FR-003 includes suggested instruction wording for the router prompt.
  - FR-009 specifies the test-case shapes explicitly.
- [x] Success criteria are measurable
  - SC-001/002/003/004/006 are replay-or-grep verifiable.
  - SC-005 quantifies expected test count (≥151 passed, 3 skipped — pre-015 baseline 148 + at least 3 new).
- [x] Success criteria are technology-agnostic (no implementation details)
  - **Caveat (intentional)**: SC-003 names `agent_runs.metadata_json.carryover` and SC-006 names a specific contract file path. Same caveat as 013/014's specs. Verifiable artifacts of the deployed system, not new implementation choices.
- [x] All acceptance scenarios are defined
  - US1: four scenarios — anaphoric follow-up resolved, substitution follow-up resolved, first-turn isolation-ambiguous still rejected (regression guard), persistence at run-start.
  - US2: two scenarios — non-null carryover on 2nd+-turn clarification_needed, distinguishable from first-turn case.
- [x] Edge cases are identified
  - Seven edge cases listed: first-turn empty carryover, 4-turn cap, cross-thread isolation, compound follow-ups, carryover with failed prior turn, pre-existing isolation-ambiguous examples preserved, persistence sub-bug.
- [x] Scope is clearly bounded
  - Out of Scope section enumerates six exclusions (Options B/C deferred, no carryover widening, no unrelated classifier tuning, no other-node audit, ETL fix deferred).
- [x] Dependencies and assumptions identified
  - Dependencies section lists exact surgical sites + predecessors (009, 005, 004) + successor (016 renumbered).
  - Assumptions section covers `build_carryover_preamble` reuse, first-turn behavior, cap unchanged, cross-thread isolation, constitution compliance, persistence mechanism.

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
  - Each of FR-001 through FR-013 maps to one or more SC items + acceptance scenarios in US1 or US2.
  - FR-011/FR-012 (contract amendments) map to the contracts/ docs that will be written in `/speckit-plan`.
  - FR-013 (renumbering admin) is verifiable by SC-006.
- [x] User scenarios cover primary flows
  - Two primary flows: (a) user asks a short follow-up after an explicit prior turn and gets an answer (US1); (b) operator triages a clarification_needed run and can see the carryover the classifier had (US2). Both are covered.
- [x] Feature meets measurable outcomes defined in Success Criteria
  - Each user story's "Independent Test" maps to one or more SC items.
- [x] No implementation details leak into specification
  - Per the Content Quality caveat: the spec names *where* changes land (necessary for a back-fill) but doesn't prescribe *how*. The router-vs-prelude choice, the persistence-shape choice, and the optional DRY refactor of `query_understanding` are all left to implementation.

## Notes

- All checklist items pass on first iteration. No spec updates required before `/speckit-plan`.
- Interactive clarifications during this spec-drafting session (resolved before the spec was written):
  - Fix shape: Option A (plumb carryover into classifier; smallest diff) — selected over Options B (prelude refactor) and C (clarification_needed as routable state).
  - Cadence: SDD back-fill (full spec/plan/research/tasks) — mirrors 012, 013, 014 cadence; selected over hot-patch.
- The spec deliberately scopes US1 + US2 together but assigns different priorities (US1=P1, US2=P2). US1 alone is a valid MVP; US2 is a small, nearly-free improvement that falls out of US1's implementation (once carryover is built earlier, persisting it earlier is one more JSON write).
- The renumbering admin (FR-013) is the SECOND renumbering of 013's pointer doc — first time was 014's FR-018 (014 → 015), now this spec's FR-013 (015 → 016). The historical-context note in the renamed file needs to reflect both renumberings. Implementation should be straightforward (filename + content edits + note addition).
- Naming choice: `015-classifier-carryover` (the user-suggested short name was used directly). Avoided `postmortem` framing because the bug is a structural-wiring issue, not a postmortem of a recent decision (013/014 were postmortems of specific recent contradictions; 015 is a fix to a wiring that's been wrong since multi-turn support was introduced).
