<!-- SPECKIT START -->
Repo identity: the GitHub origin is `jgyonzo/discogs-ai-agent`
(renamed from `discogs-analytics-agent` on 2026-07-05).

**Feature in flight: 019-listing-link-integrity** (branch
`019-listing-link-integrity`) — the scheduled follow-up to 018's
invented-URL candidate (see "Known follow-up" below). Every per-record
listing entry (`filter_records` matches + fallback_matches, `top_n`,
`media_links` per_record) gains a genuine tool-built `release_url`
(`{DISCOGS_WEB_BASE_URL}/release/{release_id}` — new settings field,
default `https://www.discogs.com`; helper in `tools/common.py`;
`release_id` comes from the sync instance pass so no re-sync needed);
`instance_id` stays unchanged as the opaque follow-up reference (id
obfuscation rejected — research R1); ground rule 1 in
`prompts/system.md` is extended (page links only from `release_url`,
media links only from `media_links`, URL construction from any id
forbidden). Contract deltas 6–8 in
`specs/019-listing-link-integrity/contracts/amendment-017-agent-tools.md`
amend 017's agent-tools §1/§5. Plan:
`specs/019-listing-link-integrity/plan.md` (spec, research, data-model,
quickstart alongside). Collection-agent only.

Most recently merged:
**018-title-locate-postmortem** (PR #5, merged to main 2026-07-05) —
postmortem fix for the same-day incident where the collection agent
falsely answered "not in your collection" for records it has synced
("Focus On Guido Schneider", "Gone Astray EP"). Root cause: no `title`
attribute in the declarative registry + the LLM passing `limit=1` on
locate-one-record listings, so the target title hid behind truncation.
Fix (collection-agent only), a five-layer escalation ladder — each
layer added after a live replay showed the previous one insufficient:
(1) one `title` text-kind `AttributeSpec` in `registry.py` (SC-003a
held — no tool-code edits for the attribute); (2) procedural "Locating
a specific record" guidance in `prompts/system.md` (artist +
title-contains on a short distinctive substring, strip format noise
like "2xLP", no small limits on presence checks, affirm near-matches
as THE record); (3) FR-009 retry-aware zero-match note in
`tools/browse.py` (the plain anti-hallucination note was steering the
LLM away from the retry at the decision point); (4) FR-010 `contains`
as the effective default op for text-kind criteria when the LLM omits
`op` (pydantic `model_fields_set` check; explicit `eq` honored) — the
biggest single win; (5) FR-011 deterministic `fallback_matches` +
`fallback_count`: on a zero-match with text + non-text criteria,
`filter_records` itself re-runs the non-text criteria so near-miss
titles land in the payload (013→014 precedent: prompt steering →
deterministic enforcement); session last-listing points at the
fallback. Fuzzy/edit-distance matching and `media_links` stayed out of
scope. 131 tests (`cd collection-agent && pytest`). Artifacts:
`specs/018-title-locate-postmortem/` (spec with two replay-postmortem
addenda, plan, research, data-model, quickstart, tasks T001–T021,
contract deltas 1–5 in `contracts/amendment-017-agent-tools.md`,
amending 017's agent-tools §3).
**Known follow-up (now in flight as 019, above):** during replays the
LLM invented Discogs URLs from listing `instance_id`s
(`discogs.com/release/<instance_id>` — wrong id space), violating
system-prompt ground rule 1 (links only from `media_links`). Fix
direction: make the listing payload's id non-linkable-looking or carry
a real tool-provided URL.

Prior feature: **017-discogs-collection-agent** (PR #3, merged to main
2026-07-05) — a terminal/CLI conversational agent
over the owner's **live Discogs collection** (personal access token),
grown inside the existing `collection-agent/` directory (promoted from
script experiment to a `src/` layout with its own `pyproject.toml` +
tests; the offline matcher scripts move mechanically to a sibling
package `src/collection_matcher/` as a separate commit — zero behavior
change, no imports between the two packages).
Architecture: OpenAI **tool-calling loop over deterministic tools** —
no LangGraph, no codegen, no sandbox, no DuckDB. Two-phase sync
(collection pages → per-release enrichment, journaled + resumable,
header-driven rate-limit governor) into a local JSON snapshot at
`collection-agent/data/snapshot.json` (gitignored;
complete/partial/stale states). Analytics/filter/link answers are
served from the snapshot at conversational speed; a **declarative
attribute registry** (`registry.py`) makes filters+aggregations
extensible by declaration and is rendered into the system prompt
dynamically (VII(b) analog — no static attribute prose). Writes
(move-to-folder, create-folder) are **live-only and runtime-gated**:
LLM can only `propose_moves`; the CLI itself prompts y/N and only
then executes with per-item live re-validation. Clarified decisions:
CLI surface; snapshot model; top-rated = community avg (vote count
shown); analytics count **instances**; scale target 300–1k records.
Key facts: Discogs 60 req/min authenticated; unique User-Agent
required; token via `.env` `DISCOGS_USER_TOKEN`. Spec + plan +
Phase-1 artifacts: `specs/017-discogs-collection-agent/` (`spec.md`,
`plan.md`, `research.md`, `data-model.md`, `quickstart.md`,
`contracts/discogs-consumption.md`, `contracts/snapshot-schema.md`,
`contracts/agent-tools.md`). API reference:
`docs/discogs_api_reference.md`. v2 (YouTube playlists/search) is
explicitly out of scope. Component runbook:
`collection-agent/README.md`; ~106 tests at merge — 131 after 018
(`cd collection-agent && pytest`), no live API calls.

Prior feature: **016-frontend-plot-layout** — frontend polish: widened
result/chart column in `frontend/src/App.tsx`, horizontal legend line
added to the canonical code shape in
`agent/src/discogs_agent/prompts/code_generator.md`, copy buttons for
run/thread id badges in `frontend/src/components/RunMetadata.tsx`.
Artifacts: `specs/016-frontend-plot-layout/`.

Prior feature: **008-agent-frontend-v1** — Demo Day frontend. A
React + Vite + TypeScript single-page app that turns the existing
agent into a demoable product: type or click a question, see a
chart inline, plus collapsible SQL, a small data preview, and
routing badges. The frontend ships as a **third** component in
this monorepo (alongside `etl/` and `agent/`), runs as a service
in the existing local docker-compose stack, and depends only on
the agent's already-shipped HTTP API plus a single CORS allowance
added to the agent. The frontend never touches DuckDB, Postgres,
ETL files, or local artifacts directly, and never executes
agent-generated Python or SQL. The chart artifact is rendered as
opaque HTML inside a sandboxed `<iframe>` (`sandbox="allow-scripts"`,
no `allow-same-origin`).

Read this feature's plan and its phase-1 artifacts:

- Plan: `specs/008-agent-frontend-v1/plan.md`
- Spec: `specs/008-agent-frontend-v1/spec.md`
- Research: `specs/008-agent-frontend-v1/research.md` (packaging,
  CORS, iframe sandbox, error mapping, state management)
- Data model: `specs/008-agent-frontend-v1/data-model.md`
  (frontend domain types + reducer state + localStorage shape)
- Contracts: `specs/008-agent-frontend-v1/contracts/`
  - `api-consumption.md` — which agent `/query` fields the frontend
    reads, ignores, or maps
  - `amendment-004-api-cors.md` — exact prose for a new §8
    "Cross-origin policy" in `004/contracts/api.md`
  - `curated-questions.md` — the V1 set of 7 demo questions and
    their spread coverage requirement
- Quickstart: `specs/008-agent-frontend-v1/quickstart.md`

Status: phases 1 through 7 are on `main` (the frontend runs as a
service in `docker-compose.yml`). Phase 8 (Polish) is unfinished:
tasks T054–T058 in `specs/008-agent-frontend-v1/tasks.md` remain
unchecked (typecheck/test gates, no-db-deps guard, no-unsafe-html
guard, empty-state copy).

Prior feature: **`015-classifier-carryover`** (merged to main
2026-05-11) — agent-side hardening
triggered by thread `9214f7fb-...` on 2026-05-11, where two
short follow-up questions ("and what is the second one?" and
"and the top 5?") were rejected as `clarification_needed`
because the classifier (router) sees only `{user_query}` +
`{schema_context_block}` — it doesn't receive the multi-turn
carryover preamble that the next node (`query_understanding`)
already consumes. Structural wiring bug: carryover is built and
consumed in `query_understanding`, AFTER the classifier
short-circuits to clarification_needed. Two work items: (US1)
extract `_load_carryover` from `query_understanding.py` to
`_carryover.py` as a public helper; call it in the router
BEFORE invoking `query_classifier`; populate state; pass
`carryover_preamble` into `ClassifierInput`; add
`{carryover_block}` placeholder + follow-up-resolution
instructions to `router.md`. (US2) Persist carryover at
run-start (falls out of US1's earlier state population) so
`metadata_json.carryover` is no longer `null` on 2nd+-turn
clarification_needed runs — operators can see what context
the classifier had. Plus an admin task: 013's pointer
`successor-015-pointer.md` is renumbered to
`successor-016-pointer.md` because 015 is now this spec
(second renumbering of the same pointer; 014 already did
014→015). See
`specs/015-classifier-carryover/plan.md`.

Prior 004-family work (still authoritative):

- `specs/004-agent-v1/` — V1 baseline (graph, API, sandbox, SQL
  safety, generated-code shape, persistence). The frontend's
  consumption shape is anchored against `004/contracts/api.md`.
  010 amended `004/contracts/postgres-schema.md` with the new §7
  JSONB input invariant.
- `specs/005-agent-schema-context/` — schema enrichment + sample
  values + glossary + the `succeeded_empty` zero-row guardrail.
  Amended by 009 with a new "Join graph" section.
- `specs/006-bugfix-postmortem/` — three-bug postmortem and
  Constitution v1.2.0 amendment (Principle VII: Implementation
  Discipline). 009 and 010 are both VII follow-throughs (009 =
  VII.b prompt-authoring; 010 = VII.c-analog write-side).
- `specs/007-sandbox-fsize-budget/` — sandbox `RLIMIT_FSIZE`
  raised to 2 GiB; `004/contracts/code-generation.md §3.1.1`
  amended.
- `specs/009-schema-context-join-graph/` — silent wrong-answer
  bugfix: extends `render_schema_block` with a join-graph section
  delivering FK relationships, cross-grain traversal hints, and
  forbidden-join anti-patterns. Closes the
  `master_fact.master_id = release_artist_bridge.release_id`
  class of LLM hallucination. Merged to main 2026-05-07.
- `specs/010-jsonb-nan-sanitization/` — silent persistence-500
  bugfix: SQLAlchemy `TypeDecorator` chokepoint sanitizes
  NaN/Infinity floats out of every JSONB column write before
  Postgres rejects them. Closes any agent run whose dataframe
  preview legitimately contains NULL cells. Merged to main
  2026-05-08.
- `specs/012-catalog-aggregation-postmortem/` — SDD back-fill of
  three hotfixes against catalog-wide OOM-kills:
  `memory_limit=1GB` in generated DuckDB connect-config, tmpfs
  bumped to 6 GiB, and glossary entry #3 first-round rewrite
  steering the LLM away from `release_unique_view` for catalog-
  wide aggregations.
- `specs/013-filtered-aggregation-postmortem/` — follow-on
  to 012. Observability fix (`oom_killed` named exception_type
  for external SIGKILL) + glossary entry #3 second-round
  rewrite (drops the "catalog-wide" qualifier; blanket ban on
  view-in-JOIN/GROUP-BY regardless of WHERE filters). Triggered
  by the Depeche Mode failure run (`b809ca52-...`). Merged to
  main 2026-05-11.
- `specs/014-cross-grain-join-postmortem/` — follow-on to 013
  + 009. Resolves the contradiction 013 introduced between
  009's cross-grain traversal hint and 013's glossary
  tightening; updates the hint to recommend `release_fact`
  instead of `release_unique_view`; promotes the forbidden-
  joins list to static enforcement in `sql_safety_checker`
  (`rule="forbidden_join"`). Triggered by run `2557c2ce-...`
  on 2026-05-10. Merged to main 2026-05-11.

The published DuckDB contract — produced by the ETL component —
remains authoritative for everything the agent reads:

- `specs/001-discogs-etl/contracts/duckdb-schema.md` — release side
  (`release_fact`, `release_unique_view`, `release_artist_bridge`,
  `release_label_bridge`).
- `specs/003-masters-artists/contracts/duckdb-schema.md` — optional
  `master_fact`. The "Counting / joining rules" section of this
  contract is the source of truth for the join graph 009 renders
  into the LLM-facing schema-context block. Both contracts are
  NULL-tolerant (release_fact.country, master_fact.year, etc.,
  are nullable) — that NULL-tolerance is what produces the NaN
  floats that 010 sanitizes at the persistence boundary.

The agent does NOT import code from `etl/` and does NOT read
non-published artifacts. Statically enforced by
`agent/tests/unit/test_no_etl_imports.py`. The frontend does NOT
import code from either `etl/` or `agent/`, and physically cannot
read `data/` because it never has the volume mounted.

Resolved scope decisions still in force:

- **LLM provider = OpenAI** (`gpt-4o-mini` cheap, `gpt-4o` strong).
- **Multi-turn = light contextual carry-over** — only prior
  user-query *text* (capped at 4 turns / 512 tokens) flows into
  `query_understanding`. No prior SQL/code carry-over.
- **Sandbox file-size budget = 2 GiB** (007 decision).
- **Schema-context join graph** (009 decision; merged to main).
  The rendered block delivers FK edges + cross-grain traversal
  hints + forbidden-join anti-patterns. The 005 contract is
  amended to make the section normative.
- **JSONB input invariant** (010 decision; merged to main). Every
  dict flowing into a JSONB column MUST be RFC-8259-compliant.
  Sanitization happens at the persistence-write boundary via a
  single chokepoint (`_SanitizedJSON` `TypeDecorator` in
  `agent/src/discogs_agent/persistence/models.py`) covering all
  five JSONB columns. The 004 contract gains §7 making this
  invariant normative.
- **Frontend stack = React 18 + Vite + TypeScript + Tailwind**
  (008 decision; matches the source brief at
  `docs/discogs_frontend_initial_spec.md`).
- **Frontend packaging = Vite dev-server in container** for V1
  (008 decision; nginx-served static build deferred to V1.1).
- **CORS allowlist** = settings-sourced env var
  `CORS_ALLOWED_ORIGINS`, defaulting to
  `["http://localhost:5173", "http://localhost:3000"]`,
  `allow_credentials = False`.

Constitution: `.specify/memory/constitution.md` (v1.2.1, amended
2026-07-05). The PATCH amendment recommended by 008's plan and
re-recommended by 017's plan **has landed**: Principle VI is now
"Components & Contracts" — "two or more independently deployable
components", listing all four (`etl/`, `agent/`, `frontend/`,
`collection-agent/`); its operational rules are unchanged.

The constitution prevails on any conflict.
<!-- SPECKIT END -->
