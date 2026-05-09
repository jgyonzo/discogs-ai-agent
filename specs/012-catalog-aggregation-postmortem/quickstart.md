# Quickstart: Catalog-aggregation postmortem

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

This is the executable companion to the spec back-fill. The fixes are already deployed (commits `0ae0662` + `4143afd`); this quickstart shows how to verify them.

---

## 1. Confirm the deployed configuration

```bash
# Verify memory_limit in the generated-code template
grep "memory_limit" agent/src/discogs_agent/prompts/code_generator.md
# Expected: config={{"temp_directory": "/tmp/duckdb", "memory_limit": "1GB"}}

# Verify the tmpfs cap
grep -A 1 "tmpfs:" docker-compose.yml | tail -3
# Expected: - /tmp/duckdb:size=6g

# Verify the rendered glossary entry #3
docker exec $(docker compose ps -q agent-api) python -c "
from discogs_agent.duckdb_layer.schema import _DOMAIN_GLOSSARY
print(_DOMAIN_GLOSSARY[2])
" | head -3
# Expected: starts with 'release_fact has grain release × style'
# and contains 'DO NOT use release_unique_view'
```

---

## 2. Verify the live agent

```bash
# Start the full stack (assumes .env has OPENAI_API_KEY + the published DuckDB)
docker compose up -d --build

until curl -fs http://localhost:8000/health | jq -e '.status == "ok"' > /dev/null
do sleep 2; done && echo "agent ready"

# Confirm the tmpfs is sized correctly
docker exec $(docker compose ps -q agent-api) df -h /tmp/duckdb | tail -1
# Expected: 6.0G total
```

---

## 3. Run the canonical reproducers

### 3.1 Curated Q1 — "Show releases by decade"

```bash
curl -fs -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"message": "Show releases by decade as a bar chart"}' \
  | jq '{status: .status, has_chart: (.chart_artifact != null), sql: .sql, latency_ms: .route.rationale}'
```

**Expected post-fix**:
- `status: "succeeded"`
- `has_chart: true`
- `sql` contains `release_fact` (NOT `release_unique_view`)
- End-to-end in <15s

### 3.2 Curated Q4 — "Top countries"

```bash
curl -fs -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"message": "What are the top 15 countries by number of releases?"}' \
  | jq '{status: .status, has_chart: (.chart_artifact != null), sql: .sql}'
```

**Expected post-fix**:
- `status: "succeeded"`
- `has_chart: true`
- `sql` contains `COUNT(DISTINCT release_id) FROM release_fact GROUP BY country`
- End-to-end in <15s

---

## 4. Inspect what changed for a recent run

To see the agent's per-attempt code and any validator output:

```bash
docker exec $(docker compose ps -q postgres) psql -U agent -d agent -c "
SELECT row_number() OVER (ORDER BY tc.created_at) AS step, tc.node_name, tc.status,
       LEFT(tc.input_json->>'generated_code', 200) AS code_preview
FROM agent_tool_calls tc
JOIN agent_runs r ON r.run_id = tc.run_id
WHERE r.user_query LIKE 'Show releases by decade%'
ORDER BY r.started_at DESC, tc.created_at LIMIT 5;
"
```

The first sandbox_executor row's `code_preview` should reference `release_fact` (not `release_unique_view`).

---

## 5. Browser frontend smoke

If you're already running the frontend (`docker compose up frontend`):

1. Open `http://localhost:5173`.
2. Click the **Releases by decade** card → **Run**. The chart should appear within ~10s.
3. Expand the SQL panel — you should see `... FROM release_fact GROUP BY decade`.
4. Click the **Top countries** card → **Run**. Chart appears with top-15 countries by release count.
5. Switch to a complex question (e.g., **Label diversity**) — the prompt steering doesn't affect those (they query bridges, not the unique-view).

---

## 6. Troubleshooting

| Symptom | Likely cause | Remediation |
|---------|-------------|-------------|
| Q1 or Q4 still fails with `failed_validation` | The agent image is from before commit `4143afd` | Rebuild: `docker compose up -d --build agent-api` |
| `exit_code=-9` reappears | The prompt template doesn't include `memory_limit` | Check `code_generator.md` line near `duckdb.connect`; ensure `memory_limit=1GB` is present |
| Tmpfs only shows ~3.9 GiB | docker-compose lacks the `:size=6g` suffix | Inspect `docker-compose.yml` agent-api `tmpfs` block; recreate with `docker compose up -d agent-api` |
| LLM still picks `release_unique_view` | The agent image is from before the `_DOMAIN_GLOSSARY` rewrite | `docker compose up -d --build agent-api`; restart so the in-process cache rebuilds the rendered block from the new wording |
| `OutOfMemoryException` reports a tmpfs limit < 6 GiB | DuckDB's `max_temp_directory_size` calculation is from "available disk at connect time"; if previous runs left orphan files, available is reduced | The agent restarts the subprocess per run, so this should self-clear; if not, restart the agent container |

---

## 7. Manual gates for full SC closure

These mirror what was done at commit time:

- **SC-001** — Q1 succeeds end-to-end (manual; per §3.1)
- **SC-002** — Q4 succeeds end-to-end (manual; per §3.2)
- **SC-003** — generated SQL queries `release_fact` directly, not `release_unique_view` (manual inspection per §4)
- **SC-004** — `pytest tests/` → 179 passed, 2 skipped (CI gate)
- **SC-005** — `read_schema_context` returns `rendered_token_count <= 1600` (CI gate via `test_rendered_block_within_token_budget`)
- **SC-006** — no `agent_runs` row with `status: "failed_validation"` AND validator `exit_code: -9` for the seven curated demo questions on this codebase (manual; per §3 and the run-history query in §4)

---

## 8. What this back-fill does NOT do

- Does not add a synthetic-large-catalog regression test. The seed fixture is too small to expose budget pressure; building a "wide catalog" fixture is meaningful work and is recorded as deferred in `spec.md` "Out-of-scope".
- Does not fix `release_unique_view`'s definition in the published DuckDB. That is an ETL-side fix (use `DISTINCT ON (release_id)` or materialize as a real table) and is captured as out-of-scope deferred work.
- Does not change the constitution. Principle VII.b and VII.c are the disciplinary analogs; both already cover this class of fix.
