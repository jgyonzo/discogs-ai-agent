# Amendment to `005/contracts/schema-context.md` — Join graph

**Source feature**: `009-schema-context-join-graph`
**Target file**: `specs/005-agent-schema-context/contracts/schema-context.md`
**Insert as**: a new top-level section "## Join graph" placed immediately AFTER the existing "## Rendered block format" and BEFORE "## Token budget".
**Also update**: the "## Rendered block format" section's example block to include a "Join graph" sub-block in its illustrative output. The "## Consumer rules" section gains one new bullet enforcing VII.b on the new section.

This is the exact prose to land in `005/contracts/schema-context.md` in the same change set as the agent code change to `render_schema_block`. Mirrors the 007 amendment to `004/contracts/code-generation.md §3.1.1`.

---

## Insertion 1: New section "## Join graph"

```markdown
## Join graph

The rendered block carries a "Join graph" section listing the foreign-key relationships between allowlisted tables. The section is derived from the published-DuckDB contracts (`001-discogs-etl/contracts/duckdb-schema.md` and `003-masters-artists/contracts/duckdb-schema.md`); the renderer does NOT invent edges.

### Position in the rendered output

After the table/grain block and the sample-values block, BEFORE the domain glossary. The order in the rendered output is:

1. Available tables (allowlist) + grains
2. (optional) `master_fact is NOT present in this catalog` line
3. Sample distinct values
4. **Join graph** ← this section
5. Domain glossary

### Required sub-blocks

The "Join graph" section MUST contain three sub-blocks, in order:

1. **Edges** — a flat list of foreign-key pairs in `table.column ↔ table.column` form. Edges that reference `master_fact` are emitted only when `has_master_fact = true`. Minimum edges (when all tables are present):

   - `release_fact.release_id ↔ release_unique_view.release_id`
   - `release_fact.release_id ↔ release_artist_bridge.release_id`
   - `release_fact.release_id ↔ release_label_bridge.release_id`
   - `release_unique_view.release_id ↔ release_artist_bridge.release_id`
   - `release_unique_view.release_id ↔ release_label_bridge.release_id`
   - `release_fact.master_id ↔ master_fact.master_id` (master-side, conditional)
   - `release_unique_view.master_id ↔ master_fact.master_id` (master-side, conditional)

2. **Cross-grain traversal hints** — at minimum:

   - A line stating that `master_id` and `release_id` are different identifier namespaces and cannot be compared to each other.
   - A worked example showing the master → release → bridge traversal (master-side; emitted only when `has_master_fact = true`).
   - A note preferring `release_unique_view` over `release_fact` for cross-grain joins (because `release_fact` is row-multiplied by style).
   - A note that bridges are NOT unique on `release_id` (one row per release × artist or release × label).

3. **Forbidden joins** — at minimum (when `has_master_fact = true`):

   - `master_fact.master_id = release_artist_bridge.release_id` (the canonical bug)
   - `master_fact.master_id = release_label_bridge.release_id` (the same class of error on the label side)
   - `master_fact.main_release_id = release_*_bridge.release_id` (a related plausible-but-wrong join — `main_release_id` IS a release_id but its use should be deliberate, not the default cross-grain path)

   When `has_master_fact = false`, the "Forbidden joins" sub-block MAY be omitted entirely OR rendered with a single note stating that no master-side joins apply on this catalog.

### Catalog-conditional rendering

- When `has_master_fact = false`, the renderer MUST omit all `master_fact`-referencing edges, the master-side traversal hint, and the master-side forbidden-join lines. It MAY still render the section with the release-side edges only.
- When the catalog has fewer than two allowlisted tables (a degenerate case never produced by a valid published DuckDB), the renderer MAY skip the section entirely.

### Token budget interaction

The "Join graph" section is rendered unconditionally within the existing `_TOKEN_BUDGET = 1200`. Empirically (April 2026 full catalog) the section adds ~220 tokens. If the rendered block exceeds the budget, the truncation order in `_TRUNCATION_STEPS` MUST drop sample values BEFORE any join-graph content. Join-graph content is NOT eligible for truncation.

### Backwards compatibility

The `SchemaContext` TypedDict shape is unchanged by this amendment. The new content is inside the existing `rendered_block` string. Consumers that read only `tables`, `has_master_fact`, `sample_values`, or `domain_glossary` continue to work without modification.
```

---

## Insertion 2: Update the "## Rendered block format" example

Update the example block in the existing "## Rendered block format" section to include the new "Join graph" sub-block between the sample-values section and the domain glossary. Replace the current example with:

```markdown
```text
Available tables (allowlist):

- release_fact (grain: release × style):
  release_id, master_id, title, year, decade, country, style,
  primary_genre, primary_format_group, has_vinyl, has_cd, ...

- release_unique_view (grain: one row per release):
  release_id, master_id, title, year, decade, country,
  primary_genre, primary_format_group, ...

- release_artist_bridge: release_id, artist_id, ...
- release_label_bridge: release_id, label_id, ...
- master_fact (grain: master release): master_id, title,
  main_release_id, year, decade, release_count, ...

Sample distinct values for low-cardinality columns:

- release_unique_view.primary_genre (14): Rock, Electronic, ...
- release_unique_view.decade: 1900, 1910, ..., 2020.
- release_unique_view.country (top-20): US, UK, DE, ...
- release_fact.style (top-50): House, Techno, Pop Rock, ...

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
- To go from master_fact to artists or labels, traverse a release-grain
  table: master_fact -> release_unique_view (on master_id) ->
  release_artist_bridge (on release_id).
- Prefer release_unique_view (one row per release) over release_fact
  for cross-grain joins; release_fact is row-multiplied by style.
- Bridges are NOT unique on release_id — one row per (release × artist)
  in release_artist_bridge.

Forbidden joins (will return semantically wrong rows even if the SQL
runs):
- master_fact.master_id  =  release_artist_bridge.release_id
- master_fact.master_id  =  release_label_bridge.release_id
- master_fact.main_release_id  =  release_*_bridge.release_id

Domain glossary:

1) primary_genre is the coarse bucket (Rock, Electronic, ...).
   style is the granular subgenre (Techno, House, ...). Filter
   by 'style' on release_fact for subgenre questions; filter by
   'primary_genre' on release_unique_view only when the value
   literally appears in the primary_genre sample.

2) For "evolution / over time / trend" questions WITHOUT
   explicit yearly granularity, group by decade not year.
   Override only when the user says "year", "yearly", or
   "annual".

3) release_fact has grain release × style; counts of unique
   releases use COUNT(DISTINCT release_id) or release_unique_view.

4) release_artist_bridge and release_label_bridge are NOT unique
   on release_id — one row per (release × artist) or (release ×
   label). For "releases per artist" or "releases per label",
   GROUP BY the artist/label and use COUNT(DISTINCT release_id);
   naive COUNT(*) double-counts.
```
```

(Note that the example also adds the new glossary entry #4, per Phase 0 R3.)

---

## Insertion 3: Update the "## Consumer rules" section

Add one new bullet to the existing "## Consumer rules" section, immediately after the "Reviewers MUST reject prompt edits..." paragraph:

```markdown
The "Join graph" section is also subject to the consumer-rule constraint above: prompt templates MUST NOT contain static prose that lists table relationships, foreign-key pairs, or cross-grain traversal advice. All such information flows only through the rendered block. Specifically forbidden in prompt files:

- enumerations of foreign keys ("release_fact joins to bridges on release_id");
- statements about which join paths are correct or wrong ("don't join master_fact directly to bridges");
- worked SQL examples that demonstrate cross-grain joins.

These belong in the "Join graph" section of the rendered block, where they can stay in sync with the published-DuckDB contracts.
```

---

## Implementation pointer

The amendment lands together with:

- `agent/src/discogs_agent/duckdb_layer/schema.py` — extend `render_schema_block` with a join-graph builder. Recommended shape: a private `_render_join_graph(has_master_fact: bool) -> list[str]` helper that returns the lines to insert; integrated into `render_schema_block` between the sample-values block and the glossary block. Plus one new entry appended to `_DOMAIN_GLOSSARY`.
- `agent/tests/integration/test_schema_context_join_graph.py` — new regression test (see plan §"Phase 1" and research §R2).
- `agent/tests/unit/test_schema.py` — extended assertions on `render_schema_block`'s output for both `has_master_fact = true` and `false`.

No new dependencies. No prompt-template edits. No `SchemaContext` field additions.

## Why amend `005` rather than create a new `009/contracts/schema-context.md`

Same reasoning as the 007 amendment to `004/contracts/code-generation.md`:

- The schema-context contract is a single surface owned by `005`. Splitting it across multiple specs would force readers to chase the join-graph rules through the spec history.
- The "Join graph" is not a *new* contract surface; it's a property of the existing rendered block.
- This pattern keeps `005/contracts/schema-context.md` the single source of truth for "what the agent's prompts see about the catalog" — consistent with how 007 kept `004/contracts/code-generation.md` the single source of truth for "what the sandbox enforces."
