# Research: Schema-context join graph

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

Three decisions taken during Phase 0. Each states what was chosen, why, what was rejected, and what would change the answer in the future.

---

## R1 — Where the "Join graph" section appears in the rendered block, and what it contains

### Decision

A new "Join graph" section is appended to the rendered block, ordered AFTER the existing tables/grain section and the sample-values section, and BEFORE the domain glossary. The section has three sub-blocks, in order:

1. **Edges** — explicit foreign-key pairs in `table.column ↔ table.column` form.
2. **Cross-grain traversal hints** — short prose explaining how to traverse master ↔ release ↔ bridge paths, with a one-line worked example.
3. **Forbidden joins** — explicit anti-patterns the LLM must NOT emit.

### Proposed exact wording (for reviewer eyeball; final prose lands in `contracts/amendment-005-schema-context.md`)

```text
Join graph (foreign-key relationships between allowlisted tables):

Edges:
- release_fact.release_id  ↔  release_unique_view.release_id
- release_fact.release_id  ↔  release_artist_bridge.release_id
- release_fact.release_id  ↔  release_label_bridge.release_id
- release_unique_view.release_id  ↔  release_artist_bridge.release_id
- release_unique_view.release_id  ↔  release_label_bridge.release_id
- release_fact.master_id  ↔  master_fact.master_id
- release_unique_view.master_id  ↔  master_fact.master_id

Cross-grain traversal hints:
- master_id and release_id are DIFFERENT identifier namespaces. They
  cannot be compared to each other.
- To go from master_fact to artists or labels, traverse through a
  release-grain table:
    master_fact -> release_unique_view (on master_id)
                -> release_artist_bridge (on release_id)
- Prefer release_unique_view (one row per release) over release_fact
  for cross-grain joins; release_fact is row-multiplied by style and
  may inflate counts.
- Bridges are NOT unique on release_id — one row per (release × artist)
  in release_artist_bridge, one row per (release × label) in
  release_label_bridge.

Forbidden joins (will return semantically wrong rows even if the SQL
runs):
- master_fact.master_id  =  release_artist_bridge.release_id
- master_fact.master_id  =  release_label_bridge.release_id
- master_fact.main_release_id  =  release_artist_bridge.release_id  (use
  the master_id traversal instead unless you specifically want only the
  primary release of the master)
```

When `has_master_fact = false`, the master-side edges and the
master-related traversal hint are omitted, and the "Forbidden joins"
list omits the master_fact entries.

### Rationale

- **Top-down LLM reading**: Tables → samples → relationships → glossary follows the natural order: "what exists" → "what values exist" → "how it connects" → "rules of thumb." Putting the join graph right before the glossary keeps relationship facts adjacent to rule-style guidance.
- **Explicit anti-patterns** are the load-bearing piece: the LLM's failure mode in the bug was *guessing* a join. Naming the wrong join out loud, in the prompt, makes it harder for the LLM to fall back on the same heuristic.
- **The "different namespaces" line** is the single most important sentence in the section. It's short, specific, and corrects the exact misconception the LLM had (treating BIGINT-BIGINT as join-compatible).
- **Edges as a flat list** rather than a "join graph picture" — the LLM doesn't render ASCII diagrams reliably. A flat enumeration of pairs is unambiguous and token-efficient.
- **Worded preference for `release_unique_view`** mirrors the 003 contract's explicit guidance.
- **The `main_release_id` forbidden line** is preemptive: another plausible-but-wrong join the LLM might invent when it sees `master_fact.main_release_id` and looks for a release-side counterpart. Naming it preempts the failure.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Add edges as inline annotations on each table block (e.g., "release_fact (joins to release_artist_bridge on release_id)") | Repetitive; adds tokens to every table. Concentrating relationship info in one section is more economical. |
| Render an ASCII-art relationship diagram | LLMs are unreliable at parsing 2D layouts; flat text is universally legible. |
| Put the join graph BEFORE the table list (most prominent position) | Tables and grains are the foundational facts. Putting relationships first risks the LLM treating them as authoritative even when it hasn't yet established what a "release" or "master" is. The current order grounds first, then connects. |
| Place the join graph inside the domain glossary as additional entries | Possible, but the glossary entries are sentences, not structured edge lists. A separate section keeps the structure clear. |
| Include common SQL skeletons (e.g., "Top artists by master count: SELECT ... FROM master_fact JOIN release_unique_view ...") | Risks copy-paste behavior over genuine reasoning. The traversal hint with one worked example is enough. Skeletons could be a future enhancement if the regression test reveals it's needed. |

### What would flip this decision

- A future LLM that reliably parses ASCII relationship diagrams. (Unlikely to matter — flat lists work everywhere.)
- A change in catalog scope that adds a new junction table (e.g., a `master_label_bridge` direct-join table). The renderer would gain new edges but the section structure is unchanged.

---

## R2 — Test strategy for the regression

### Decision

A two-layer test setup, both deterministic, neither depending on a live LLM call:

**Layer A — Unit-level rendering test** (`agent/tests/unit/test_schema.py`, extended): asserts on the output of `render_schema_block(...)` for two cases:

1. `has_master_fact = true` → output contains the section header `"Join graph"`, the master ↔ release edge, the "different identifier namespaces" anti-pattern line, and the explicit `master_fact.master_id = release_artist_bridge.release_id` forbidden-join line.
2. `has_master_fact = false` → output contains the section header AND the release ↔ bridge edges, but NOT any `master_fact`-prefixed line.

This locks in the structure of the rendered block without recording a brittle full-string golden file.

**Layer B — Integration-level snapshot test** (`agent/tests/integration/test_schema_context_join_graph.py`, new): runs `read_schema_context(...)` against an existing fixture DuckDB (using the `seed_duckdb` fixture from 005), then asserts that the cached `rendered_block` field matches a versioned golden snapshot.

The golden snapshot lives at `agent/tests/integration/golden/schema_context_block.txt`. Updating the golden requires rebuilding the snapshot intentionally (a comment in the test explains how). Drift in `render_schema_block`'s output without an intentional golden update fails the test.

**Not in scope (manual gate, not CI)**: SC-001's "9 of 10 attempts at the canonical reproducer generate correct SQL" is a manual smoke test executed during implementation against the live OpenAI backend. It's documented in `quickstart.md`. We do NOT add an OpenAI-calling test to CI because (a) it's nondeterministic (single-attempt success rate < 100% even with a perfect prompt), (b) it costs money per CI run, and (c) it's rate-limited.

### Rationale

- **Deterministic CI is non-negotiable**. A flaky regression test that catches the bug 70% of the time is worse than no test — it teaches the team to ignore failures.
- **Layer A** is the cheap deterministic gate: structural assertions, no I/O. Catches accidental refactors that drop the section.
- **Layer B** is the deeper gate: a pinned golden file makes ANY change to the rendered block visible in code review. If a future feature adds a new edge (e.g., when `artist_dim` lands), the golden file must be updated as part of that change, surfacing the contract change explicitly.
- **The manual smoke test** is the empirical proof that the LLM behavior changes. It's invoked via `quickstart.md` once during implementation and once during PR review. The bar is "the canonical reproducer never produces the forbidden join" — even one pre-fix reproduction confirms the bug; even ten post-fix reproductions confirm the fix.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Live OpenAI call in CI, asserting the generated SQL doesn't contain the forbidden join | Flaky (LLM nondeterminism), slow, expensive, rate-limited. Fails too often or passes by luck. |
| Stub LLM backend with a recorded prompt → recorded SQL response | The stub backend (`LLM_BACKEND=stub`) returns canned responses; it doesn't actually run the prompt-rendering against the schema-context block. Recording a "correct SQL response" doesn't prove the fix works; it just proves we can record. |
| No regression test at all (rely on manual smoke) | Violates the project's testing discipline. The whole reason 006 added Constitution VII.b was that "spec says don't do X" without a regression test fails to prevent X from creeping back. |
| Replace the existing rendering tests rather than extend them | The existing tests already lock in the table/grain/sample/glossary surfaces. Keeping them and adding new assertions is purely additive. |

### What would flip this decision

- A reliable, fast, free LLM-stub that produces real prompt-following behavior. (Doesn't exist yet at acceptable cost.)
- A reproducible LLM (e.g., a fully local model in the test stack with seed-based determinism). Not on our radar.

---

## R3 — Glossary update vs. dedicated section vs. both

### Decision

Both: a dedicated "Join graph" section (per R1) AND one new domain-glossary entry tightening the bridge-grain note.

The new glossary entry, paraphrased into plain prose:

> "release_artist_bridge and release_label_bridge are NOT unique on release_id. Each row is one (release × artist) or one (release × label). For 'releases per artist' or 'releases per label' counts, GROUP BY the artist/label and use COUNT(DISTINCT release_id) — naive COUNT(*) double-counts."

### Rationale

- **The dedicated section** is structured and machine-readable (edges, hints, forbidden joins). It teaches the join graph.
- **The glossary entry** is rule-style guidance that complements the join graph by warning about a related but different failure mode (counting in a row-multiplied table). The bug surfaced master ↔ artist; the related trap is "OK, I now correctly join through `release_artist_bridge`, but I do `COUNT(*)` and double-count releases that have multiple artists." Adding this glossary entry preempts the next failure.
- **Two surfaces, two scopes**: the section says how tables connect; the glossary entry says what to do with the connection once you've made it.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Dedicated section only, no glossary update | Doesn't address the bridge-grain row-multiplication trap. We have evidence the LLM gets identifier names wrong; we have weaker but credible reason to think it might also get aggregation grain wrong on bridges. Cheap to preempt. |
| Glossary update only, no dedicated section | Glossary entries are unstructured prose. The LLM needs the explicit edge list and forbidden-join list to reliably override its own pattern-matching defaults. |
| Add an entire "Aggregation rules" section | Out of scope for this feature. The bug is about joins, not aggregations. One glossary entry is enough; if "aggregation rules" becomes a recurring failure surface, that's a separate spec. |

### What would flip this decision

- Evidence that the bridge-grain trap recurs in production despite the dedicated section. We'd promote the glossary entry to its own section and add a regression test.

---

## Cross-decision invariants

- **Token budget**: the proposed wording (R1) is approximately 220 tokens. Combined with the glossary update (R3), the total addition is ~240 tokens. The 005 spec sized the rendered block at ~487 tokens for the full April 2026 catalog; post-009 the rendered block is ~727 tokens, well under the 1200-token budget. No truncation expected.
- **Truncation order**: if the budget is ever exceeded, the existing `_TRUNCATION_STEPS` (drop `country` top-20→top-10, drop `style` top-50→top-30) MUST run BEFORE any join-graph content is touched. Implementation: keep `_TRUNCATION_STEPS` unchanged; the join-graph section is rendered unconditionally and is not eligible for truncation.
- **Backwards-compat**: the `SchemaContext` TypedDict shape is unchanged. The new content is inside the existing `rendered_block` string. Consumers that read only `tables` / `has_master_fact` / `sample_values` / `domain_glossary` continue to work.
- **No prompt edits**: the fix MUST NOT modify any file under `agent/src/discogs_agent/prompts/`. Constitution VII.b. The integration test optionally asserts that no prompt template grew new occurrences of table names beyond the existing whitelist (the `release_fact` "Critical rule" line in `code_generator.md`).
