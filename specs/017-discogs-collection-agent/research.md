# Research: Discogs Collection Agent (017)

Phase 0 output. Each entry: **Decision / Rationale / Alternatives considered.**
Discogs API facts are sourced from `docs/discogs_api_reference.md` (compiled
from the official developer docs).

---

## R1. Component placement — grow `collection-agent/`

**Decision**: Implement inside the existing `collection-agent/` top-level
directory, promoting it from a script experiment to a packaged component
(`pyproject.toml`, `src/` layout, `tests/`). The existing matcher scripts
(`matcher.py`, `review_batch.py`, `export_batch.py`) move to a sibling
package `src/collection_matcher/` in a strictly mechanical, separately
committed refactor (zero behavior change; notebook/README references
updated); the new agent lives in `src/collection_agent/`. The two packages
never import each other.

**Rationale**: Same domain — the owner's personal collection. The matcher's
README explicitly defers "the write side (add-to-collection, create-folder)
and any streaming-link enrichment" — i.e., this feature is the anticipated
next step of that component, not a new domain. Avoids a fifth top-level
directory and a naming collision ("collection agent" already means this
directory in repo vocabulary). Constitution VI is satisfied: own manifest,
own tests, no cross-component imports, runs standalone.

**Alternatives considered**:
- *New top-level component* (e.g. `collection-chat/`) — rejected: duplicates
  the domain, worsens the Principle-VI component-count tension for no
  benefit, and leaves "collection-agent" ambiguous forever.
- *Inside `agent/`* — rejected: different data source (live API vs published
  DuckDB), runtime (laptop CLI vs AWS container), secrets, and deploy cycle;
  exactly the coupling Principle VI's rationale warns against.

## R2. Orchestration — OpenAI tool-calling loop over deterministic tools

**Decision**: A plain OpenAI chat-completions **tool-calling loop**: the LLM
routes natural language to a fixed set of deterministic tools (aggregate,
filter, links, value, sync, propose-moves); tools compute answers from the
snapshot in plain Python. No LangGraph, no code generation, no sandbox.
Models settings-driven (`COLLECTION_AGENT_MODEL`, default the repo's cheap
tier `gpt-4o-mini`; provider OpenAI per the repo-wide resolved decision).

**Rationale**: The data is one user's ≤ ~1,000-record snapshot — every US1/US2
question is a counter/filter over a small list, so generated SQL/Python (agent
v1's approach, built for a 19M-row DuckDB) buys nothing and reintroduces
sandboxing, OOM budgets, and hallucinated-join risk. Deterministic tools give
FR-022 grounding by construction: the LLM never fabricates numbers, it only
narrates tool output. Spanish/English handling (FR-021) is native to the LLM.

**Alternatives considered**:
- *Reuse agent v1's LangGraph codegen pipeline* — rejected: wrong data source,
  heavy machinery (sandbox, fsize budgets, SQL safety checker) for a
  1k-record in-memory list; slower and riskier.
- *LangGraph with tool nodes* — rejected: a linear tool loop needs no graph;
  fewer deps, less state to debug. Can be revisited for v2 (YouTube flows).
- *No LLM (command grammar)* — rejected: the spec's core promise is natural
  conversation in two languages.

## R3. Discogs access — thin custom httpx client, personal access token

**Decision**: A small `discogs/client.py` on `httpx` with:
- Auth: `Authorization: Discogs token=<DISCOGS_USER_TOKEN>` header (personal
  access token; single owner per spec assumption).
- Identity: `GET /oauth/identity` on startup to resolve the username (no
  hardcoded username; `DISCOGS_USERNAME` env only as override).
- A unique, settings-sourced User-Agent (e.g.
  `DiscogsCollectionAgent/0.1 +<repo-url>`), required by Discogs (missing UA
  ⇒ empty responses/blocking).

**Rationale**: Token auth is the documented high-tier single-user method —
unlocks 60 req/min and image URLs, no OAuth dance needed for a personal tool.
A thin client gives direct control over the rate-limit headers and backoff
(R4), which community wrappers abstract away.

**Alternatives considered**:
- *`python3-discogs-client` (joalla)* — rejected: extra dependency, less
  control over header-driven throttling/backoff and User-Agent policy; our
  needed surface is ~8 endpoints.
- *OAuth 1.0a flow* — rejected for v1: only needed to act on behalf of
  arbitrary users; spec fixes single-owner scope.

## R4. Rate limiting — header-driven governor with safety margin

**Decision**: Track `X-Discogs-Ratelimit`, `-Used`, `-Remaining` on every
response. Governor sleeps when `remaining` falls to a settings-sourced floor
(default 2), spreading requests inside the 60-second moving window; on 429,
exponential backoff with jitter and resume. All Discogs calls (sync and live
writes) pass through the governor.

**Rationale**: FR-003/SC-006 require staying inside limits while syncing
hundreds of records; the headers are the authoritative budget signal (docs:
moving average over a 60 s window). A fixed `sleep(1)` wastes ~40% of the
budget or overshoots under concurrent use.

**Alternatives considered**: fixed-delay pacing (rejected: wasteful/fragile);
optimistic fire-until-429 (rejected: spec requires graceful degradation, and
Discogs warns of silent blocking for misbehaving apps).

## R5. Snapshot storage — single JSON file, atomic writes, journal for resume

**Decision**: `collection-agent/data/snapshot.json` (gitignored): a `meta`
block (username, `synced_at`, counts, durations, warnings,
`completeness: complete|partial|stale`, collection value) plus a `records`
list (one entry per **instance**, per clarification Q4). Writes are atomic
(temp file + `os.replace`). During sync, per-release enrichment progress is
journaled to `snapshot.sync.tmp.json` so an interrupted sync resumes instead
of restarting (FR-003c); analytics load the whole file into memory.

**Rationale**: At ≤ ~1k records (single-digit MB) a JSON file is transparent,
diffable, dependency-free, and trivially atomic. Aggregations are
`collections.Counter` territory — no query engine needed.

**Alternatives considered**:
- *SQLite* — rejected: adds schema/migration ceremony for data that fits in
  memory; no query need beyond list comprehensions.
- *DuckDB* — rejected: invites confusion with the **published** DuckDB
  contract (Principle V/VI vocabulary); explicitly out of scope in the spec.
- *Postgres (agent's store)* — rejected: cross-component coupling.

## R6. Sync design — two phases, instances then per-release enrichment

**Decision**:
1. **Instance pass**: paginate
   `GET /users/{u}/collection/folders/0/releases?per_page=100` (folder 0 =
   "All"). Yields every instance with `instance_id`, `folder_id`, `date_added`,
   owner `rating`, and `basic_information` (title, artists, year, labels,
   formats, genres, styles, thumb). ~10 requests for 1k instances. Also fetch
   the folder list (`GET .../collection/folders`) and collection value
   (`GET .../collection/value` → min/median/max).
2. **Enrichment pass**: for each **unique release id**,
   `GET /releases/{id}` → `country`, `videos[]`, `community.have/want`,
   `community.rating.average/count`, `num_for_sale`, `lowest_price`,
   authoritative genres/styles. ~1 request per unique release (worst case
   ≈1,000 ⇒ ≲20 min at 60/min; typical 300–500 ⇒ 5–9 min). Progress bar via
   `rich`; enrichment results journaled incrementally (R5).

Sync age is stamped in `meta.synced_at`; answers disclose it; `refresh`
re-syncs (instance pass always full — it's cheap; enrichment reuses journaled
results for unchanged release ids unless `--full`).

**Rationale**: The collection endpoint alone lacks country, videos,
community stats, and market signals — exactly the fields US1's rarity/
country/links/value analytics need, so the per-release pass is unavoidable;
doing it once into a snapshot is what makes conversation-speed answers
possible (clarification Q2). Folder 0 guarantees instance-complete coverage
(SC-002 reconciliation).

**Alternatives considered**: enrich lazily per question (rejected: every
rarity/country question would still take minutes — clarification chose
snapshot); Discogs monthly dumps (rejected: not the user's collection, no
instance/folder/rating data).

## R7. Extensible filtering & aggregation — declarative attribute registry

**Decision**: A single `registry.py` module declaring each attribute once:
`name`, `aliases` (English + Spanish), `kind`
(categorical | numeric | text | multi-valued), an `extract(record)` function,
and optional derived logic (e.g. `decade` from `year`, `scarcity` from
have/want/for-sale). Two generic tools consume it: `aggregate_by(attribute)`
(counts + percentages incl. explicit *unknown* bucket, FR-004/007) and
`filter_records(criteria)` (AND-combined `{attribute, op, value}` triples,
FR-011/012). The system prompt's "what you can filter/aggregate on" section
is **rendered from the registry at runtime** — never hand-written prose
(Constitution VII(b) analog).

Launch registry: `genre`, `style`, `decade`/`year`, `label`, `country`,
`artist`, `format`, `my_rating`, `community_rating`, `have`, `want`,
`num_for_sale`, `lowest_price`, `folder`.

**Rationale**: FR-013/SC-003a make extensibility a requirement: one new
registry entry ⇒ new filter + new aggregation + prompt updated, no redesign.
A registry also gives FR-013a for free (unknown attribute ⇒ named error
listing what *is* supported).

**Alternatives considered**: per-attribute bespoke tools (rejected: N tools ×
M ops explosion, redesign per attribute — exactly what the spec forbids);
LLM-generated pandas/SQL (rejected: R2 grounds answers in deterministic code).

## R8. Write actions — runtime-enforced two-phase confirmation

**Decision**: Writes never execute from a single LLM tool call:
1. LLM calls `propose_moves(record_refs, target_folder, create_if_missing)` —
   a **dry-run** that resolves instances, validates folder names, and returns
   a human-readable plan + `plan_id` stored in CLI session state.
2. The **CLI runtime itself** renders the plan and prompts `y/n` directly at
   the terminal (outside the LLM conversation). Only an explicit `y` triggers
   `execute_plan(plan_id)`, which re-validates each instance's current state
   live against Discogs before mutating (stale-snapshot guard, FR-003d),
   creates the folder if planned (`POST .../collection/folders`), moves each
   instance
   (`POST .../folders/{fid}/releases/{rid}/instances/{iid}` to the target
   folder), reports per-item success/failure (FR-020), and marks the snapshot
   stale/patches it.

**Rationale**: FR-019's confirmation gate must not depend on the LLM
remembering to ask — a runtime gate makes unconfirmed writes *unreachable*,
which is also the Constitution VII(c)-style "document the mechanics"
posture for the only mutating path.

**Alternatives considered**: prompt-level "always ask first" instruction only
(rejected: probabilistic, not a gate); auto-execute with undo (rejected:
Discogs has no transactional undo; folder deletes only work on empty
folders).

## R9. Value & rarity semantics

**Decision**:
- **Collection value** (FR-009): `GET /users/{u}/collection/value` → report
  Discogs' own **minimum / median / maximum**, currency as returned; always
  labeled as Discogs' estimate (basis stated per spec).
- **Most expensive** (FR-010): rank by per-release `lowest_price` from
  enrichment (basis: "cheapest copy currently listed"), stating that records
  with no copies for sale have no price signal and are listed separately.
- **Rarity** (FR-008): composite, criterion always stated —
  `num_for_sale == 0` (or ≤ a small threshold, default 2, settings-sourced)
  OR `want/have` ratio high (default ≥ 2.0 with `have ≥ 10` to avoid
  small-sample noise); thresholds live in settings, the answer names them.
  Records missing community stats are excluded and reported as such (edge
  case: never falsely rare).

**Rationale**: Uses only signals Discogs actually exposes; avoids the
price-suggestions endpoint (requires seller settings). Defaults are
adjustable without code changes (VII(a)) and the spec only requires the
criterion be *stated*, which the tools do.

**Alternatives considered**: `marketplace/price_suggestions` (rejected:
seller-settings gated); scraping sold-history (rejected: not in the API,
against ToS).

## R10. CLI shape & UX

**Decision**: `python -m collection_agent <cmd>`:
- `chat` — the REPL (default): free-text conversation, `rich`-rendered
  tables/lists, sync-age banner, `/refresh`, `/status`, `/exit` meta-commands.
- `sync [--full]` — run/resume a sync non-interactively.
- `status` — snapshot meta: sync age, counts, completeness, last warnings.
First `chat` with no snapshot offers to sync (with time estimate from
collection size fetched via one cheap request).

**Rationale**: Mirrors the repo's "CLI as source of truth" norm; `sync` being
a first-class command keeps the long operation scriptable and testable
outside conversation.

**Alternatives considered**: chat-only (rejected: hides the long-running sync
inside a conversational turn); `typer`/`click` dependency (optional — stdlib
`argparse` suffices for three subcommands; decide at implementation, no
contract impact).

## R11. Responding in the user's language

**Decision**: System-prompt instruction: detect and mirror the user's
language per turn (Spanish/English expected); tool outputs are
language-neutral data structures the LLM narrates.

**Rationale**: FR-021; zero extra machinery. Registry aliases include Spanish
attribute names ("género", "sello", "país", "década") so filter parsing works
in both languages.

## R12. Testing strategy

**Decision**: No live Discogs calls in tests. Three layers:
- **Unit**: registry extraction/aliases, aggregation math (percentages sum,
  unknown buckets), filter ops, rarity/value ranking, snapshot store
  atomicity/staleness — against fixture snapshots.
- **Integration**: sync against a `FakeDiscogsClient` replaying recorded JSON
  fixtures (pagination, 429 injection, mid-sync interruption ⇒ resume,
  partial states); organize flow (propose → confirm → execute with a live
  re-validation failure injected); agent loop with a stubbed LLM verifying
  tool dispatch and that write tools are unreachable without runtime
  confirmation.
- **Static**: `test_no_cross_imports.py` (no `etl`/`discogs_agent` imports),
  mirroring `agent/tests/unit/test_no_etl_imports.py`.

**Rationale**: Deterministic CI, secrets never needed in tests, and the two
riskiest behaviors (rate-limit handling, confirmation gate) are exactly the
ones exercised by injected fixtures.
