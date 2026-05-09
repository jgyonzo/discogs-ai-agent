# Research: Catalog-aggregation postmortem

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

This document records the empirical investigation that drove the three hotfixes. Numbers are from live production runs against the full April 2026 catalog (~19M unique releases, ~31.7M release_fact rows, 7.75 GiB host).

---

## R1 — The cgroup OOM-killer reaping the sandbox subprocess

### Symptom

Threads `1b932140-4c0d-4d0d-a092-dbb8b04d1e94` (2026-05-08): both runs of "What are the top 15 countries by number of releases?" ended `failed_validation`. The chart_validator output recorded `nonzero_exit` with `exit_code=-9`, empty stderr, empty stdout. Both retries hit the same wall.

`exit_code=-9` is Python's convention for "subprocess terminated by signal 9" = SIGKILL. The kernel killed the process before it could write a single byte to stderr.

### Investigation

The agent container at the time of the incident:

- 7.75 GiB host total RAM (Docker Desktop)
- `HostConfig.Memory = 0` on the agent-api container — no explicit memory cap, so the cgroup limit is the host's full RAM.
- The agent process was using 254 MiB at idle.
- The sandbox subprocess executed `con = duckdb.connect(...)` with `config={"temp_directory": "/tmp/duckdb"}` — **no `memory_limit`**. DuckDB defaults to "80% of visible memory," ~6.2 GiB inside this container.

The generated SQL was:

```sql
SELECT country, COUNT(DISTINCT release_id) AS number_of_releases
FROM release_unique_view
GROUP BY country
ORDER BY number_of_releases DESC
LIMIT 15
```

Per-country distinct sets across ~19M release_ids reach into the GB range for the largest countries (US, UK). DuckDB allocated aggressively to fit them in memory; the cgroup OOM-killer reaped the subprocess as the largest child of the agent process.

Sandbox restrictions in `agent/src/discogs_agent/sandbox/restrictions.py`:

- `RLIMIT_CPU = timeout + 5` (CPU-time, sends SIGXCPU not SIGKILL)
- `RLIMIT_NOFILE = 256`
- `RLIMIT_FSIZE = 2 GiB` (007 decision)
- `RLIMIT_NPROC = 64`
- **No `RLIMIT_AS`** — the sandbox does not bound the subprocess's address space.

### Decision

Add `"memory_limit": "1GB"` to the generated-code `duckdb.connect(...)` config. This forces DuckDB to spill rather than allocate unbounded; spilling stays within the configured `temp_directory` (`/tmp/duckdb` tmpfs).

### Why 1 GB (not 4 GB, not unbounded)

- **1 GiB is sufficient for the cheap query plans** the prompt steers toward (`COUNT(DISTINCT release_id) FROM release_fact GROUP BY X` needs <100 MB of working memory for ≤250 groups).
- **1 GiB is conservative for the cgroup blast radius**. The agent container has no explicit memory cap; bumping memory_limit to 4 GB would let DuckDB allocate up to 4 GB in working memory (and more in spill) before any backstop. With 7.75 GiB host RAM and other processes (Postgres, agent, Python interpreter), that pushes uncomfortably close to host OOM.
- **The cap stays a hardcoded constant, not an env var**. Per Constitution VII.a, security-critical sandbox invariants should not be operator-tunable (a misconfigured env var would silently weaken the budget). Same reasoning as 007's `RLIMIT_FSIZE_BYTES`.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Set `RLIMIT_AS` in `restrictions.py` to bound the subprocess address space | Defense-in-depth; not the primary fix. With `memory_limit` + prompt steering, the cgroup OOM path is no longer reached on the curated demos. RLIMIT_AS remains a defensible future addition. |
| Set explicit `HostConfig.Memory` on the agent-api container | Container-level cap. Same effect as RLIMIT_AS but at a coarser layer. Would require docker-compose changes for a benefit that's secondary to the prompt steering. |
| Make `memory_limit` operator-tunable via env var | Constitution VII.a. A safety-critical sandbox invariant should not be silently overridable. |
| Bump `memory_limit` to "4GB" | Bigger blast radius for marginal benefit on the cheap-path queries. |

### Outcome

After this fix (commit `0ae0662`), the SIGKILL failure mode disappeared. Subsequent failures surfaced as catchable `OutOfMemoryException` from DuckDB — visible to the validator and recorded in `agent_tool_calls.output_json`. The fix turned silent failures into legible failures, paving the way for R2 + R3 to address the residual issues.

---

## R2 — tmpfs default size insufficient for legitimate spill

### Symptom

Thread `91ef2ca2-003e-421a-862e-b7be8b1a27c9` (2026-05-09): "Show releases by decade" failed with DuckDB `OutOfMemoryException`:

```
Out of Memory Error: failed to offload data block of size 128.0 KiB
(1.7 GiB/1.7 GiB used).
This limit was set by the 'max_temp_directory_size' setting.
```

A second attempt within the same run reported `3.4 GiB / 3.4 GiB used`. The numbers varied because DuckDB calculates `max_temp_directory_size` from "available disk space at connection time."

### Investigation

The agent-api compose entry had:

```yaml
tmpfs:
  - /tmp/duckdb
```

Default tmpfs size is half of host RAM = ~3.9 GiB on a 7.75 GiB host. DuckDB used `available disk space` at connect time, which was ~3.4 GiB after subtracting agent-process memory pressure.

The query the LLM generated at this point:

```sql
SELECT decade, COUNT(*) AS release_count
FROM release_unique_view
GROUP BY decade
ORDER BY decade
```

Naïvely this is trivial (14 buckets). But `release_unique_view` is `SELECT DISTINCT (~33 cols) FROM release_fact` — DuckDB has to materialize the entire deduplicated 19M-row × 33-col set before any GROUP BY can stream. That materialization spills 3-4 GiB of intermediate state.

### Decision

Set tmpfs cap explicitly to `/tmp/duckdb:size=6g` in `docker-compose.yml`. Gives DuckDB ~6 GiB of spill room (vs ~3.4 GiB observed) while keeping ~1.75 GiB free for the rest of the host.

### Why 6 GiB (not 8, not unlimited)

- Host has 7.75 GiB total RAM.
- tmpfs eats RAM lazily (only consumes pages as content is written), but the cap protects against runaway growth.
- 6 GiB tmpfs + ~1 GiB agent process + Postgres + frontend container + Python interpreters = ~7.5 GiB peak, leaving a thin headroom margin.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| 8 GiB tmpfs | Exceeds host RAM (7.75 GiB). Risk of host OOM under stress. |
| Bind-mount a real disk-backed `/tmp/duckdb` directory | Slower (disk I/O vs RAM I/O); also requires the user to manage a directory. tmpfs with 6 GiB is faster and self-cleaning on container restart. |
| Increase `memory_limit` so DuckDB spills less | Bigger blast radius (R1 trade-off). And R3's prompt steering removes the need entirely. |

### Outcome

The 6 GiB tmpfs gave DuckDB more spill room, but R3's prompt steering meant queries stopped requiring it. Even on the heaviest legitimate query (Q4 "Top countries"), post-R3 the working set fits well under 1 GiB without any spill.

The 6 GiB cap remains as a safety net for unexpected query plans.

---

## R3 — Steer LLM away from `release_unique_view` for catalog-wide aggregations

### Symptom

Even with R1 + R2 in place, threads `91ef2ca2` and `8f99c83f` (2026-05-09) showed the LLM persistently choosing `SELECT ... FROM release_unique_view GROUP BY X` for catalog-wide aggregations. Both retries (per `MAX_RETRIES=2`) generated **byte-identical** code, indicating the repair-prompt path didn't shift the LLM's preference.

### Root cause

`release_unique_view`'s SQL definition (read directly from the published DuckDB):

```sql
CREATE VIEW release_unique_view AS
SELECT DISTINCT release_id, master_id, title, primary_artist_id, primary_artist_name,
       country, released_raw, "year", "month", "day", released_date,
       released_date_precision, "decade", data_quality, track_count, artist_count,
       label_count, genre_count, style_count, format_count, primary_label_id,
       primary_label_name, primary_format_raw, primary_format_group, format_quantity,
       format_description_summary, has_vinyl, has_cd, has_cassette, has_digital,
       has_box_set, primary_genre, run_id
FROM release_fact;
```

This is `SELECT DISTINCT` over **33 columns** of a 31.7M-row table. Every query against the view forces DuckDB to:

1. Scan all 31.7M rows of release_fact
2. Hash each 33-column tuple
3. Build a global distinct set (~19M unique rows)
4. Pass the deduplicated set downstream

The downstream `GROUP BY decade COUNT(*)` is trivial — but the upstream DISTINCT is pathological.

### Why the LLM picked it

The pre-fix glossary entry #3 said:

> "release_fact has grain release × style; counts of unique releases use COUNT(DISTINCT release_id) or query release_unique_view."

The LLM correctly read this as offering two alternatives, and picked `release_unique_view` (which it interpreted as "already-deduplicated, simpler to query"). The glossary's wording assumed the view was a cheap materialized table; in reality it's a cost-deferring SELECT DISTINCT.

### Decision

Rewrite the glossary entry #3 (and the matching prompt rules in `code_generator.md` + `repair_code.md`) to explicitly steer the LLM AWAY from `release_unique_view` for catalog-wide aggregations:

> *(new entry #3 — landed in commit `4143afd`)*
>
> "release_fact has grain release × style. For counts of unique releases, use `SELECT X, COUNT(DISTINCT release_id) FROM release_fact GROUP BY X` — this only tracks per-X distinct sets and is cheap. DO NOT use release_unique_view for catalog-wide aggregations: the view is defined as `SELECT DISTINCT (~33 columns) FROM release_fact` and forces DuckDB to materialize the entire deduplicated set (~19M rows × 33 cols), which spills GBs of temp even for trivial GROUP BYs. release_unique_view is fine for spot-check queries against a single release (e.g., `WHERE release_id = N`), but never for catalog-wide GROUP BYs. Never use `COUNT(*) FROM release_fact` for release counts (it counts release × style rows, not releases)."

### Why this works

For `SELECT decade, COUNT(DISTINCT release_id) FROM release_fact GROUP BY decade`:

- **Working memory**: 14 hash sets, one per decade. The largest decade (1990s/2000s/2010s) has ~5M release_ids × 8 bytes (BIGINT) ≈ 40 MB per group. Total: ≤100 MB across all groups.
- **Scan**: DuckDB streams release_fact (31.7M rows × 1 column needed: release_id + decade) — sequential read, no spill.
- **Result**: 14 rows.
- **Time**: <1s on warm cache.

Compare to `SELECT decade, COUNT(*) FROM release_unique_view GROUP BY decade`:

- **Working memory**: 19M unique 33-column tuples held in memory or spilled.
- **Scan**: 31.7M × 33 cols = ~1B cell reads.
- **Spill**: 3-4 GiB across the DISTINCT operator.
- **Time**: 10-30s when it succeeds; OOM otherwise.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Drop `release_unique_view` from the agent's allowlist entirely | Hammer where a scalpel works. The view is fine for single-release lookups (`WHERE release_id = N`); just not for catalog-wide aggregations. The prompt steering carves out the right exception. |
| Fix the view's definition in the ETL (use `DISTINCT ON (release_id)` or materialize as a real table) | Architecturally correct, but it's an ETL-side fix that requires re-running the ETL. Out of scope for the demo emergency. Recorded as deferred work in spec.md "Out-of-scope". |
| Tighten the glossary without removing the option | Tried earlier (intermediate version told LLM to PREFER release_unique_view). The LLM kept picking the heavyweight path. The current wording is more directive ("DO NOT use ... for catalog-wide aggregations") and explicitly carves out the legitimate use case. |

### Outcome

After commit `4143afd`, manual verification showed the LLM consistently generates the cheap path (`COUNT(DISTINCT release_id) FROM release_fact GROUP BY X`) for catalog-wide questions. Curated demo questions Q1 and Q4 succeed end-to-end in <15s. The earlier failure modes are gone.

---

## Cross-decision invariants

- **Memory budget is layered**: DuckDB `memory_limit=1GB` (working memory) → tmpfs `/tmp/duckdb:size=6g` (spill) → no `RLIMIT_AS` (subprocess address space) → no `HostConfig.Memory` (container cap) → host RAM.
- **The prompt is the load-bearing fix**. R1 + R2 turn silent failures into legible failures, but R3 makes the failures stop happening at all on the curated demo paths.
- **The view's pathological definition is an ETL-side issue**. Documented as out-of-scope deferred work in `spec.md`. The agent's contract amendments here are workarounds, not the structural fix.
- **All three fixes preserve the constitutional disciplines** — Principle VI (single component touched), VII.a (configuration sources — memory_limit is a hardcoded sandbox invariant), VII.b (prompt-authoring discipline — steering lives in the dynamically-rendered glossary), and the VII.c-analog write-side discipline.
