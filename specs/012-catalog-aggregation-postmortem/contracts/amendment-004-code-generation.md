# Amendment to `004/contracts/code-generation.md` — Sandbox memory budget

**Source feature**: `012-catalog-aggregation-postmortem`
**Target file**: `specs/004-agent-v1/contracts/code-generation.md`
**Insert as**: a new subsection §3.1.2 "Sandbox memory budget", placed after the existing §3.1.1 "Sandbox file-size budget" (added by 007). Mirrors 007's amendment shape.

This is the exact prose to land in `004/contracts/code-generation.md` in the same change set as the agent code change (the prompt template includes `memory_limit=1GB` in the `duckdb.connect(...)` config, and the docker-compose `tmpfs:` entry for `/tmp/duckdb` is sized to 6 GiB). Mirrors 007's amendment to `004/contracts/code-generation.md §3.1.1`.

---

## Insertion: New subsection §3.1.2 "Sandbox memory budget"

```markdown
### 3.1.2 Sandbox memory budget

*Added 2026-05-09 by `012-catalog-aggregation-postmortem`. Closes
the silent-class failure where catalog-wide aggregations were
killed by the cgroup OOM-killer (`exit_code=-9`, empty stderr)
because DuckDB's default working memory was unbounded inside the
agent container. Named incident: thread
`1b932140-4c0d-4d0d-a092-dbb8b04d1e94`,
question "What are the top 15 countries by number of releases?"
on 2026-05-08.*

The generated-code template MUST include `memory_limit` in the
DuckDB connect-config:

```python
con = duckdb.connect(
    DB_PATH,
    read_only=True,
    config={"temp_directory": "/tmp/duckdb", "memory_limit": "1GB"},
)
```

#### What `memory_limit` does

`memory_limit` is DuckDB's working-memory budget. When DuckDB needs
more memory than the cap, it spills intermediate state to
`temp_directory`. Without `memory_limit`, DuckDB defaults to
"80% of visible memory" — inside the agent container that's
~6 GiB on a 7.75 GiB host. Allocating that aggressively triggers
the cgroup OOM-killer, which reaps the largest child of agent-api
(the sandbox subprocess) with SIGKILL. SIGKILL produces no Python
exception, no stderr, no traceback — just `exit_code=-9`. The
chart_validator records `nonzero_exit` but cannot recover useful
context for the repair prompt.

#### What `memory_limit=1GB` guarantees

- DuckDB allocates at most 1 GiB of working memory.
- Excess intermediate state spills to `temp_directory` (the tmpfs
  at `/tmp/duckdb`).
- Out-of-memory conditions surface as catchable `OutOfMemoryException`
  with informative messages — not opaque SIGKILL.
- The sandbox subprocess stays within the cgroup's effective
  budget; the kernel OOM-killer is not reached on the curated
  demo paths.

#### Why 1 GiB

The 1 GiB cap is sized against the **prompt-steered** query plans
in `005/contracts/schema-context.md` glossary entry #3 (post-012):
catalog-wide aggregations using
`SELECT X, COUNT(DISTINCT release_id) FROM release_fact GROUP BY X`
need <100 MB of working memory for ≤250 groups. 1 GiB is generous
headroom for the legitimate query class. A larger cap (e.g.,
4 GiB) would let DuckDB allocate aggressively before any
backstop, expanding the cgroup blast radius for marginal benefit.

#### Configuration source rationale (Constitution VII.a)

`memory_limit` is a **hardcoded constant** in the prompt template,
NOT operator-tunable via env var. Per Constitution VII.a,
security-critical sandbox invariants must not be silently
overridable. A misconfigured env var would weaken the budget
without surfacing the change. Same reasoning as 007's
`RLIMIT_FSIZE_BYTES`.

#### Sandbox tmpfs sizing

The agent-api container's `/tmp/duckdb` tmpfs MUST be sized to at
least 6 GiB:

```yaml
# docker-compose.yml
agent-api:
  ...
  tmpfs:
    - /tmp/duckdb:size=6g
```

The default tmpfs size (~half of host RAM, ~3.9 GiB on a 7.75 GiB
host) was insufficient for legitimate spill scenarios on the
April 2026 full catalog (observed: queries against
`release_unique_view` consumed >3 GiB temp before being capped).

The 6 GiB cap leaves ~1.75 GiB of host RAM for the agent process,
Postgres, frontend container, Python interpreters, etc. tmpfs
content is reclaimed when the container restarts.

#### What this clause does NOT do

- Does not bypass `RLIMIT_FSIZE` (007 §3.1.1) — it remains the
  process-wide file-size cap, shared by chart artifacts and DuckDB
  spill files.
- Does not introduce `RLIMIT_AS` (subprocess address-space cap).
  The combination of `memory_limit` + tmpfs cap + prompt steering
  (012 R3) is sufficient on the demo paths; `RLIMIT_AS` remains
  a defensible defense-in-depth addition for a future spec.
- Does not prevent legitimate memory-aggressive queries from
  failing — it makes them fail **legibly** with a real
  `OutOfMemoryException` instead of opaque SIGKILL. The repair
  prompt path can then propose a cheaper plan; if retries
  exhaust, the user sees a controlled-failure response.

#### Disciplinary analog (Constitution VII.c)

This invariant is the **memory-side counterpart** to 007's
file-size budget. Constitution VII.c says: "When a runtime
constraint declares a resource read-only, the constraint's
*consequences* MUST be documented alongside it." This subsection
applies the symmetric statement: when a sandbox declares a
working-memory cap, the consequences (queries that exceed the cap
must spill or fail; the spill destination must be sized for
realistic workloads) are documented alongside it.

#### Verification

Pinned by:

- The prompt templates `agent/src/discogs_agent/prompts/code_generator.md`
  and `agent/src/discogs_agent/prompts/repair_code.md` — both
  include `memory_limit=1GB` in the connect-config example.
- The LLM-stub canned responses in `agent/src/discogs_agent/llm/stub.py`
  + the golden-test helper in `agent/tests/golden/_helpers.py` —
  both kept in sync.
- The docker-compose `agent-api` service has `tmpfs:
  - /tmp/duckdb:size=6g`.
- Manual smoke against the live Postgres stack via
  `specs/012-catalog-aggregation-postmortem/quickstart.md`.
```

---

## Why amend `004` rather than create a new contract

Same reasoning as 007's amendment to `004/contracts/code-generation.md §3.1.1` and 010's amendment to `004/contracts/postgres-schema.md §7`:

- The agent's sandbox runtime is a single contract surface owned by `004`. Splitting it across multiple specs would force readers to chase resource invariants through the spec history.
- The "memory budget" is a property of the existing sandbox runtime, not a new sandbox.
- This pattern keeps `004/contracts/code-generation.md` the single source of truth for "what the sandbox enforces" — consistent with how 007 kept the file-size budget there.

## Implementation pointer

The amendment is a back-fill — the implementation is already deployed:

- `agent/src/discogs_agent/prompts/code_generator.md` (commit `0ae0662`) — the generated-code template's `duckdb.connect(...)` config includes `memory_limit=1GB`.
- `agent/src/discogs_agent/prompts/repair_code.md` (commit `0ae0662`) — the repair prompt's "Critical rules" mirror.
- `agent/src/discogs_agent/llm/stub.py` (2 occurrences, commit `0ae0662`) — stub canned responses kept in sync.
- `agent/tests/golden/_helpers.py` (commit `0ae0662`) — golden-test helper kept in sync.
- `docker-compose.yml` (commit `4143afd`) — agent-api `tmpfs:` for `/tmp/duckdb` sized to 6 GiB with a comment block explaining the why.

No new dependencies. No new tests in this back-fill (a synthetic-large-catalog regression test is recorded as deferred work in `spec.md` "Out-of-scope").
