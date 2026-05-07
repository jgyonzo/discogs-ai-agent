# Specification Quality Checklist: Schema-context join graph

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-07
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

### Validation pass — 2026-05-07

- **Tone caveat**: This is an agent-internals bugfix; the "non-technical stakeholders" criterion is interpreted as "the spec is readable by someone who knows the project but doesn't know the rendering function's signature." Specifically, the spec describes user-visible behavior (cross-grain questions return correct SQL) and the contract surface (the rendered schema-context block), not Python signatures or token-counting logic — those belong in the plan.

- **Stack-shaped phrases that remain are intentional**: file paths to the producer (`agent/src/discogs_agent/duckdb_layer/schema.py`) and the test target (`agent/tests/integration/test_schema_context_join_graph.py`) are present because (a) the feature is by definition an agent-internal fix and (b) the test artifact is a load-bearing FR. They are observable from the maintainer's perspective; they do not bind a particular implementation detail (e.g., the exact rendering algorithm).

- **Reproducer is named with thread id**: `fc1a3324-80da-465e-85ce-0359d5bd7633` is a stable identifier for the bug instance. Future readers can correlate to logs.

- **Scope guardrail**: Explicit non-goal — retroactive flagging of prior wrong runs. The spec also rules out broader prompt-engineering improvements (chain-of-thought, FK-discovery node, etc.). If those are wanted later, a separate spec captures them.

- **Constitution VII.b is the load-bearing principle**: the spec invokes it explicitly in FR-007, SC-005, and Assumptions. The fix is the operationalization that VII.b's discipline implies but doesn't itself implement.

- **No clarification markers**: All edge cases (no-master_fact catalog, token budget, repair path, retroactive runs) have explicit decisions documented in Assumptions and Edge Cases.

### Items requiring follow-up at plan time

- Plan must decide whether the integration regression test uses (a) a recorded golden output of the agent's generated SQL, (b) the stub LLM backend with a pinned prompt, or (c) a separate unit test on `render_schema_block` plus a manual smoke test on the live agent. Trade-off: (a) and (b) are CI-friendly but don't exercise real LLM behavior; (c) is real-world but flaky. Recommendation deferred to plan/research.
- Plan must propose the exact prose for the new "Join graph" section in the rendered block. The spec only says it must exist and be agnostic to format — the plan picks wording, ordering, and the anti-pattern phrasing.
- Plan must identify whether the existing token-counting test in CI needs to be updated (it tracks `_TOKEN_BUDGET = 1200` against the full catalog; new content adds tokens).
