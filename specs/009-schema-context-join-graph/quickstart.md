# Quickstart: Schema-context join graph

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

This document is the executable companion to the spec: how to verify the bug pre-fix, how to verify the fix post-fix, and how to run the regression test.

---

## 1. Manual reproducer (live agent)

The bug surfaces against the published full catalog. Pre-fix, the agent generates SQL with the silent wrong join.

### 1.1 Setup

```bash
# Bring up the live agent stack (existing compose).
docker compose up agent-api postgres
# Confirm health.
curl -fs http://localhost:8000/health | jq .
```

### 1.2 Submit the canonical reproducer

```bash
curl -fs -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"message": "show the artist with more masters by decade, exclude Various and Unknown Artist"}' \
  | jq -r '.sql'
```

### 1.3 Verify (pre-fix vs. post-fix)

**Pre-fix expected output** (the bug):

```sql
... master_fact mf
JOIN release_artist_bridge rab ON mf.master_id = rab.release_id ...
```

The join `mf.master_id = rab.release_id` is the bug. Run completes with HTTP 200 and a populated `chart_artifact`, but the rows are wrong.

**Post-fix expected output**:

```sql
... master_fact mf
JOIN release_unique_view ruv ON ruv.master_id = mf.master_id
JOIN release_artist_bridge rab ON rab.release_id = ruv.release_id ...
```

(or an equivalent traversal through `release_fact`).

### 1.4 SC-001 / SC-002 manual gate

Run the reproducer 10 times against the live agent:

```bash
for i in $(seq 1 10); do
  curl -fs -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d '{"message": "show the artist with more masters by decade, exclude Various and Unknown Artist"}' \
    | jq -r '.sql' \
    | grep -q "master_fact.master_id\s*=\s*release_artist_bridge.release_id" \
    && echo "ATTEMPT $i: BUG PRESENT" \
    || echo "attempt $i: clean"
done
```

**Pass criteria** (post-fix): zero "BUG PRESENT" lines. SC-002 requires all 10 clean. SC-001 requires at least 9 of 10 to show the correct master ↔ release ↔ bridge traversal (small margin for cheap-model variance on incidental wording).

---

## 2. Inspect the rendered schema-context block locally

To eyeball what the LLM actually receives:

```bash
cd agent
.venv/bin/python -c "
from discogs_agent.duckdb_layer.schema import read_schema_context
from discogs_agent.config import settings
ctx = read_schema_context(settings.ANALYTICS_DUCKDB_PATH)
print(ctx['rendered_block'])
"
```

Post-fix the block contains a "Join graph" section between sample values and the domain glossary, with the edge list, traversal hints, and forbidden-joins line documented in `contracts/amendment-005-schema-context.md`.

---

## 3. Run the regression test

```bash
cd agent
.venv/bin/pytest tests/integration/test_schema_context_join_graph.py tests/unit/test_schema.py -v
```

Expected: all green post-fix.

To verify the test actually catches the bug, temporarily revert the change to `render_schema_block`:

```bash
git stash push -m "test reverting fix" agent/src/discogs_agent/duckdb_layer/schema.py
.venv/bin/pytest tests/integration/test_schema_context_join_graph.py -v
# Expected: assertion failure (the regression test fails on the pre-fix renderer).
git stash pop
.venv/bin/pytest tests/integration/test_schema_context_join_graph.py -v
# Expected: green again.
```

This sanity check is part of SC-003 ("the test is verified to fail on the pre-fix codebase").

---

## 4. Token budget verification

The 005 spec sized the rendered block at ~487 tokens for the full April 2026 catalog. Post-009 the block is ~727 tokens (still well under the 1200-token budget).

```bash
cd agent
.venv/bin/python -c "
from discogs_agent.duckdb_layer.schema import read_schema_context
from discogs_agent.config import settings
ctx = read_schema_context(settings.ANALYTICS_DUCKDB_PATH)
print(f'rendered_token_count: {ctx[\"rendered_token_count\"]}')
print(f'budget: 1200')
print(f'headroom: {1200 - ctx[\"rendered_token_count\"]}')
"
```

Pass criteria: `rendered_token_count <= 1200` (typically ~727 on the full catalog) and no `schema_context_truncated_for_token_budget` warning in the agent logs at startup.

---

## 5. What to inspect during PR review

- `agent/src/discogs_agent/duckdb_layer/schema.py` — the new `_render_join_graph` helper and its integration into `render_schema_block`. Confirm: (a) join-graph emitted unconditionally; (b) master-side edges/hints conditional on `has_master_fact`; (c) the new glossary entry appended to `_DOMAIN_GLOSSARY`.
- `agent/tests/integration/test_schema_context_join_graph.py` — verify the test asserts on (a) section header presence, (b) the master ↔ release edge when `has_master_fact = true`, (c) the explicit anti-pattern line, (d) absence of master-side content when `has_master_fact = false`.
- `agent/tests/integration/golden/schema_context_block.txt` — the golden snapshot. Verify it matches the proposed wording in `research.md` R1 and `contracts/amendment-005-schema-context.md`.
- `specs/005-agent-schema-context/contracts/schema-context.md` — confirm the verbatim insertions from `contracts/amendment-005-schema-context.md` landed.
- `agent/src/discogs_agent/prompts/*.md` — confirm NO new occurrences of table names or join prose. The `code_generator.md` "Critical rule for `release_fact`" line is the only allowed pre-existing occurrence (per `005/contracts/schema-context.md` "Consumer rules", invariant negative rules are permitted).

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Post-fix, the bug still reproduces | Schema-context cache not refreshed (process didn't restart) | Restart the agent: `docker compose restart agent-api`. The cache is process-local and only rebuilt at startup. |
| Token budget exceeded | New content is too large, OR catalog grew | Inspect via §4. If real catalog growth, the existing `_TRUNCATION_STEPS` will drop sample values first; join-graph content is not eligible for truncation. |
| Regression test fails on a clean checkout | Golden snapshot drift (e.g., column order changed in the published DuckDB) | Update the golden snapshot intentionally; document why in the PR description. The test's failure message links to this quickstart. |
| LLM still occasionally produces a wrong join post-fix | Cheap-model variance on edge cases | Confirm SC-001 (≥9/10 attempts clean) holds. If it doesn't, file a follow-up issue; the join graph is not the only failure surface. |
