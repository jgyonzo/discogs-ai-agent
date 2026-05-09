# Amendment to `005/contracts/schema-context.md` — glossary entry #3 rewrite

**Source feature**: `012-catalog-aggregation-postmortem`
**Target file**: `specs/005-agent-schema-context/contracts/schema-context.md`
**Update**: replace the existing glossary entry #3 in the example block under "## Rendered block format" with the new wording. The schema-context renderer in `agent/src/discogs_agent/duckdb_layer/schema.py` `_DOMAIN_GLOSSARY` is already updated (commit `4143afd`); this amendment makes the contract document match the deployed code.

---

## Replacement: glossary entry #3 in the example block

The existing entry #3 (lines around 136-138 of `005/contracts/schema-context.md`'s example block) reads:

```markdown
3) release_fact has grain release × style; counts of unique
   releases use COUNT(DISTINCT release_id) or
   release_unique_view.
```

Replace it with:

```markdown
3) release_fact has grain release × style. For counts of unique
   releases, use `SELECT X, COUNT(DISTINCT release_id) FROM
   release_fact GROUP BY X` — this only tracks per-X distinct
   sets and is cheap. DO NOT use release_unique_view for
   catalog-wide aggregations: the view is defined as
   `SELECT DISTINCT (~33 columns) FROM release_fact` and forces
   DuckDB to materialize the entire deduplicated set (~19M rows
   × 33 cols), which spills GBs of temp even for trivial
   GROUP BYs. release_unique_view is fine for spot-check queries
   against a single release (e.g., `WHERE release_id = N`),
   but never for catalog-wide GROUP BYs. Never use `COUNT(*)
   FROM release_fact` for release counts (it counts release ×
   style rows, not releases).
```

The wording in the renderer is byte-equivalent to this; the contract example is the human-facing canonical form.

---

## Why this matters

The pre-012 wording offered `release_unique_view` as an alternative path on equal footing with `COUNT(DISTINCT release_id)` on `release_fact`. The LLM consistently chose `release_unique_view` (interpreting it as a cheaper, already-deduplicated table). In reality, `release_unique_view` is a `SELECT DISTINCT` over 33 columns of `release_fact` — pathologically expensive at full-catalog scale.

The replacement wording:

1. **Names the cheap pattern explicitly** with the SQL skeleton: `SELECT X, COUNT(DISTINCT release_id) FROM release_fact GROUP BY X`.
2. **Names the failure mode of the alternative**: "spills GBs of temp even for trivial GROUP BYs".
3. **Carves out the legitimate use case**: spot-check single-release queries on `release_unique_view` are still fine.
4. **Preserves the existing negative rule** about `COUNT(*) FROM release_fact`.

## Constitution VII.b compliance

The replacement entry lives in the dynamically-rendered `{schema_context_block}`. Per Constitution VII.b ("schema info comes ONLY via the rendered block"), this is the legitimate channel for steering the LLM's query-shape preferences. No static schema prose was added to any prompt template.

The mirroring "Critical rule" in `code_generator.md` and the matching reminder in `repair_code.md` are **rules-of-thumb tied to the prompts' roles** (per VII.b's "What prompts MAY contain" carve-out), not catalog-fact descriptions. They reinforce the glossary without duplicating its schema content.

## Verification

The deployed renderer at `agent/src/discogs_agent/duckdb_layer/schema.py` (commit `4143afd`) emits this exact wording. The golden snapshot at `agent/tests/integration/golden/schema_context_block.txt` was regenerated on the same commit. The integration test `test_rendered_block_matches_golden` locks the deployed wording.

The unit test `test_schema_context_glossary_contains_style_vs_genre_rule` asserts the glossary contains specific keywords (`primary_genre`, `style`, `decade`, `year`) — all of which remain present across the four entries. The regenerated entry #3 still contains `style` (in "release × style" and "release × style rows") and the four-entry shape is unchanged.

## Implementation pointer

This is a contract back-fill — the renderer change is already deployed:

- `agent/src/discogs_agent/duckdb_layer/schema.py` `_DOMAIN_GLOSSARY` entry #3 (commit `4143afd`) — production wording.
- `agent/tests/integration/golden/schema_context_block.txt` (commit `4143afd`) — regenerated golden.

The contract example block in `005/contracts/schema-context.md` is what changes in this back-fill commit.
