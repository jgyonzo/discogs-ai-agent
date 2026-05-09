# Specification Quality Checklist: Catalog-aggregation postmortem

**Purpose**: Validate specification completeness and quality before proceeding to (or alongside) implementation
**Created**: 2026-05-09
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

### Validation pass — 2026-05-09

- **Tone caveat**: This is a post-implementation back-fill spec, mirroring 006-bugfix-postmortem. "Non-technical stakeholders" is interpreted as "the spec is readable by someone who knows the project but doesn't know SQLAlchemy + DuckDB internals." User-visible behavior (catalog-wide aggregations succeed) and the contract surfaces (memory_limit, tmpfs, glossary entry #3) are described; specific Python signatures and DuckDB internals belong in research.md.

- **Stack-shaped phrases that remain are intentional**: paths to deployed code (`agent/src/discogs_agent/prompts/code_generator.md`, `docker-compose.yml`, `_DOMAIN_GLOSSARY`) are present because (a) the spec is a back-fill documenting already-deployed code, (b) the contract amendments target real files, and (c) without these references the spec wouldn't anchor to the actual deployment state.

- **Reproducer threads are named**: `1b932140-4c0d-4d0d-a092-dbb8b04d1e94`, `91ef2ca2-003e-421a-862e-b7be8b1a27c9`, etc. — stable identifiers from the postgres run history. Future readers can correlate the spec to the actual logs.

- **Three bugs, one spec**: spec.md groups three hotfix commits into one postmortem because they all surfaced from the same incident class (catalog-wide aggregations exhausting DuckDB's working/spill budget). This mirrors 006-bugfix-postmortem's three-bugs-one-spec shape.

- **The flip-flop is part of the record**: spec.md "Assumptions" explicitly notes that during the cascade, the LLM was briefly told to PREFER `release_unique_view` (wrong) before being corrected to AVOID it. The intermediate state is not preserved as its own change; only the final state lands.

- **No clarification markers**: All edge cases (catalog growth, future-LLM-regression, view-OK-for-spot-check) have explicit Edge Cases / Assumptions entries.

### Items requiring follow-up post-merge

- T-D (synthetic-large-catalog regression test) is documented as deferred. When a future feature happens to need a "wide catalog" fixture for some other reason, that's the natural moment to land T-D as part of it. Not blocking 012's merge.
- T-E (ETL-side fix to `release_unique_view`'s definition) is the architecturally-correct fix and should be its own spec. The agent-side amendments here are workarounds. Not blocking 012's merge — the workarounds keep the demo path working indefinitely.
- T-F (`RLIMIT_AS` in the sandbox) is a defense-in-depth addition. Not required after 012 + 007 + 010 are all in place.
