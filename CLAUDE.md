<!-- SPECKIT START -->
Repo identity: the GitHub origin is `jgyonzo/discogs-ai-agent`
(renamed from `discogs-analytics-agent` on 2026-07-05).

**No feature is currently in flight.** Most recently merged:
**022-phone-record-scan** (PR #TBD, merged to main TBD — implemented
2026-07-07 on branch `022-phone-record-scan`; owner-only live
validation T038–T041 still open) — scan physical records with the
phone: a `scan` HTTP subcommand inside `collection-agent` (FastAPI +
uvicorn + python-multipart — the component's first HTTP surface) serves
a self-contained phone page (`scan/static/index.html`, native-camera
`capture` input, NOT the `frontend` component) on the home LAN (plain
HTTP, no page auth — recorded v1 risk; default `0.0.0.0:8022`).
Pipeline: photo → `scan/vision.py::extract_evidence` (one
`chat.completions` call w/ `json_object`, model from NEW
`COLLECTION_AGENT_VISION_MODEL` default `gpt-4o-mini`, via 017/021's
`_build_llm_client` seam so LangSmith wraps it; one retry then typed
502) → `scan/search.py` precision ladder over NEW
`DiscogsClient.search_releases` (`GET /database/search`, `type=release`
forced): barcode → catno(+label) → artist+title, lower rung only on
zero results; free-text rung for manual search; dedup, cap 8
(`COLLECTION_AGENT_SCAN_CANDIDATES_MAX`), `more_matches` flag; every
candidate field VERBATIM from the search payload (019 discipline,
audited by unit test). Duplicate overlay
(`snapshot_duplicate_checker`): snapshot counts + session adds;
partial/stale-snapshot absence degrades to explicit `unknown`, never
"not in collection" (FR-010). Write gate (017's y/N translated to
HTTP, research R9): `POST /api/add` requires a session-allowlisted
release_id (LLM output can never reach the write), duplicates need
`confirm_duplicate=true` enforced server-side; add = NEW
`DiscogsClient.add_to_collection` (`POST .../folders/{fid}/releases/
{rid}`, folder `COLLECTION_AGENT_SCAN_FOLDER_ID` default 1, validated
LIVE at startup) → journal `added` → `SnapshotStore.mark_stale()`
(R4: never append sync-shaped records). Append-only fsync'd JSONL
session journal at `data/scan-sessions/<session>.jsonl`
(`COLLECTION_AGENT_SCAN_JOURNAL_DIR`); journal write failure = loud
500, never silent. Uploads capped 10 MiB
(`COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES`) before any vision work.
Seven new `Settings` fields total (VII(a)); secrets never on the wire
(page is static — grep-guarded test). **Replay addendum 1**
(2026-07-07, live session `20260707-130810Z`: 0/4 identified on two
Crosstown Rebels 12″ singles — diagnosed via the journal + 021's
LangSmith traces): vision put barcode digits in `catno` twice, read
the label as the artist, and parked lead tracks in `notes` (12″
singles print no title); the ladder discarded partial evidence.
Fixes: FR-003 prompt hardening (barcode-vs-catno, label≠artist,
lead-track-is-title, new `tracks` field), FR-019 normalization
(10+-digit separator-stripped catno ⇒ barcode), FR-020 final
free-text rung composed from artist+title/lead-track+label when
structured rungs are absent/empty (journal `evidence_kinds` = rungs
actually TRIED, `text` incl.), FR-021 journal lines carry the compact
extracted evidence values (photo) / query (manual) — LangSmith no
longer needed to debug identification. Owner independently repointed
`COLLECTION_AGENT_VISION_MODEL` to `gpt-5.4-mini`. Live session 2
(`20260707-160209Z`): 2/2 identified via the barcode rung and added
(releases 724223, 297060); SC-004/005/007 + stale→sync→complete
reconciliation validated same day (note in quickstart.md); still
open: SC-002 10-record batch, SC-003 taps, SC-006 dup marker
(T038/T039); one 80s vision-latency provider outlier on record. 339 tests
(`cd collection-agent && pytest`), no live API calls; live replay
tests use the verbatim failing vision replies; `FakeDiscogsClient`
grew scriptable search/add. Artifacts: `specs/022-phone-record-scan/`
(spec + replay addendum 1, plan, research R1–R10, data-model,
quickstart + owner live-validation checklist, tasks T001–T037 +
T042–T046 complete / T038–T041 owner-only, contracts: `scan-api.md`,
`scan-journal-schema.md`, `amendment-017-discogs-consumption.md` —
FIRST amendment to 017's discogs-consumption contract:
+`/database/search` read, +add-to-collection write). Out of scope
kept: OAuth/YouTube, cover-art fingerprints, HTTPS/auth (owner
decision T041).

Prior feature:
**021-langsmith-tracing** (PR #11, merged to main 2026-07-07) —
LangSmith observability for the collection-agent via the `langsmith`
SDK's plain-OpenAI integration, explicitly NOT a LangChain migration
(017 research R2's plain-SDK loop stays the architecture of record).
One trace tree per user turn in the dedicated LangSmith project
`discogs-collection-agent`: `run_turn` chain root (`@traceable` in
`agent.py`); client-level `llm` runs carrying the **as-sent** payload
— incl. the transient `LANGUAGE_REMINDER` (wire truth, never the
persisted session) — plus provider token usage; one tool span per
`_dispatch` (now a traced shell over `_dispatch_impl`) recording the
exact returned payload incl. all four error-dict shapes.
`wrap_openai` happens ONLY at `cli.py::_build_llm_client` (017's
injectable seam — test stubs are never wrapped). Config: four
`Settings` fields reusing the repo `.env`'s existing
`LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_ENDPOINT` names +
dedicated `COLLECTION_AGENT_LANGSMITH_PROJECT` (default
`discogs-collection-agent`; deliberately never inherits `agent/`'s
`LANGSMITH_PROJECT` — separate projects, same org), bridged
settings→`os.environ` at that one site (VII(a); the SDK incl. the
`@traceable` gate reads only `os.environ` — same mismatch+fix as the
OpenAI-key pass-through). Strict no-op when unconfigured: plain
unwrapped client, zero LangSmith traffic; flag-without-key ⇒ one dim
notice + untraced chat, never `EXIT_CONFIG`; autouse `LANGSMITH_*`
env-scrub in conftest keeps the suite offline regardless of the
shell; secrets-hygiene static audit now sanctions 3
`get_secret_value` sites (the env bridge is the third). Single new
dependency `langsmith>=0.3` (resolved 0.9.8). 223 tests
(`cd collection-agent && pytest`), no live API calls; live
SC-001..006 owner-validated same day (note in quickstart.md).
Artifacts: `specs/021-langsmith-tracing/` (spec, plan, research
R1–R6, data-model, quickstart + live-validation note, tasks
T001–T018 all complete, `contracts/tracing.md` — a NEW contract;
017's agent-tools contract and its 018/019/020 amendment deltas are
untouched). Workflow note: single-PR flow — feature + post-merge
CLAUDE.md state land in ONE PR (owner decision 2026-07-07, replaces
the previous two-PR convention).

Prior feature:
**020-youtube-playlist-integration** (PR #9, merged to main
2026-07-06) — closes the deferred "v2 YouTube playlists" scope with a
**read-only** capability, re-scoped mid-flight (2026-07-06, owner
decision) from OAuth account writes to **anonymous play links**; the
OAuth path is preserved in research R6 as the documented follow-up
candidate. New read tool `playlist_links` (`tools/playlist.py`) emits
`{YOUTUBE_WEB_BASE_URL}/watch_videos?video_ids=…` click-to-play links
over the resolved records' stored videos: one click opens a temporary
playlist the owner saves/names **on the YouTube site** — the agent
never touches a YouTube account (no OAuth, no credentials, no new
deps, no write gate — 017's §4 untouched). Video ids come only from
deterministic parsing of `MediaLink.uri`
(`youtube_links.py::video_id_from_uri`; never LLM-supplied — 019
precedent); the URL shape exists only in `build_watch_videos_url`
(grep-enforced). Links chunk record-aligned at
`YOUTUBE_PLAYLIST_MAX_IDS` (default 50) with per-link labels, no
silent truncation; `videos_per_record` `all` (default) | `first`.
Five owner replay rounds hardened it same-day (findings 1–8, spec
replay addenda 1–5): CLI `soft_wrap` (rich's hard-wrap broke cmd+click
mid-URL), honest "play links, never playlists I created" phrasing,
**decision-point language reminder** (`agent.py::LANGUAGE_REMINDER`,
transient system message appended last to every LLM request, never
persisted — standing-prompt rule 4 kept losing to the registry's
Spanish aliases), **lean listing entries** (`filter_records` defaults
to artist/title/year/country/`release_url`; new `include` arg for
user-named extras; non-eq criteria auto-include their attribute;
titles capped at `LISTING_TITLE_MAX_CHARS` 70 — delta 11, supersedes
019 delta 6's entry shape), and a rows-vs-columns arg-schema guardrail
("show all records" = `limit`, not `include`). Live SC-002 audit:
128/128 emitted ids verbatim from the snapshot. YouTube *search* stays
out of scope. 213 tests (`cd collection-agent && pytest`), no live API
calls in tests. Artifacts: `specs/020-youtube-playlist-integration/`
(spec with 5 replay addenda, plan, research R1–R6, data-model,
quickstart, tasks T001–T019, contracts: `youtube-playlists.md` +
deltas 9–11 in `amendment-017-agent-tools.md` — the third amendment to
017's agent-tools contract, after 018's 1–5 and 019's 6–8).

Prior feature:
**019-listing-link-integrity** (PR #7, merged to main 2026-07-05) —
same-day follow-up closing 018's invented-URL candidate: during 018
replays the LLM fabricated `discogs.com/release/<instance_id>` links
(instance_id is a collection-instance id, not a release id — wrong id
space), violating ground rule 1. Fix (collection-agent only, 013→014
precedent — deterministic enforcement over prompt steering): every
per-record listing entry (`filter_records` matches + fallback_matches,
`top_n` all bases, `media_links` per_record) carries a genuine
tool-built `release_url` =
`{DISCOGS_WEB_BASE_URL}/release/{release_id}` (new settings field,
default `https://www.discogs.com`, distinct from the API base;
shared helper `tools/common.py::release_page_url`; `release_id` comes
from the sync instance pass so every existing snapshot works — no
re-sync). `instance_id` stays byte-identical as the opaque follow-up
reference (id obfuscation rejected, research R1: it would break
`media_links` ref resolution and move/ordinal follow-ups). Ground
rule 1 in `prompts/system.md` extended: page links only from
`release_url`, media links only from `media_links`, URL construction
from any identifier forbidden (absent records get no fabricated
link). `media_links` verbatim-URI + explicit-`none` shape preserved;
its note now distinguishes the release *page* from playable media.
Live replay of the 018 incident prompts passed (zero invented URLs,
SC-001); link spot-checked in browser (SC-002). 146 tests
(`cd collection-agent && pytest`), no live API calls;
`collection-agent/uv.lock` is now tracked. Artifacts:
`specs/019-listing-link-integrity/` (spec, plan, research R1–R5,
data-model, quickstart, tasks T001–T018, contract deltas 6–8 in
`contracts/amendment-017-agent-tools.md`, amending 017's agent-tools
§1/§5 — the second amendment to that contract, after 018's deltas
1–5 against §3).

Prior feature:
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
Its known follow-up (the invented-URL 019 candidate) is **resolved by
019** (above).

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
`collection-agent/README.md`; ~106 tests at merge — 146 after 019,
213 after 020, 223 after 021 (`cd collection-agent && pytest`), no
live API calls.

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
