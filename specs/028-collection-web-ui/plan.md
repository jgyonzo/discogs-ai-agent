# Implementation Plan: Collection-Agent Web UI

**Branch**: `028-collection-web-ui` | **Date**: 2026-07-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/028-collection-web-ui/spec.md`

## Summary

Grow the existing scan server into the collection-agent's single web
surface: one self-contained tabbed page (Scan | Chat | Collection) served
by the same FastAPI app on :8022. Chat rides the existing
`Agent.run_turn` seam with a server-held conversation, a busy lock, and
the 022-R9 write-gate pattern (server-held `WritePlan`, explicit
confirm/cancel endpoints, `execute_plan` unchanged and never
LLM-reachable). Collection status and a standard-sync trigger ride the
existing `run_sync` in a single-occupancy background thread with polled
progress; post-sync freshness is structural (`SnapshotStore.load()`
re-reads per call) and gets test-pinned. Zero new dependencies, ZERO new
Settings fields, scan behavior and the 027 container contract preserved
byte-for-byte in function (`serve` becomes the subcommand name, `scan`
stays a working alias).

**Component(s) touched**: `collection-agent` only. `etl/`, `agent/`,
`frontend/` untouched; eval pipeline and vision prompt untouched.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI + uvicorn (already in the component for 022), openai SDK, langsmith (observe-only), pydantic/pydantic-settings — **zero new dependencies**
**Storage**: existing component-local artifacts only — `data/snapshot.json` (+ enrichment journal) and `data/scan-sessions/*.jsonl`; all new web state is process-lived in memory (no new persisted artifact)
**Testing**: pytest, `cd collection-agent && pytest`; FastAPI TestClient with stubbed LLM/Discogs clients; no live API calls (545 tests today; ~+45 expected)
**Target Platform**: owner's machine or the 027 container, trusted home LAN, phone + desktop browsers
**Project Type**: single component — CLI-launched LAN web service inside `collection-agent/`
**Performance Goals**: single user; chat turn = LLM latency (seconds to ~a minute, threadpool keeps other endpoints live); status GET instant; sync progress visible within one poll interval (~2s)
**Constraints**: no page auth / plain HTTP (recorded trust model); self-contained static page; no secrets on the wire; server-enforced write gates; ZERO new Settings fields; 027 image/compose contract unchanged
**Scale/Scope**: 300–1k records (017 target); one conversation, one sync at a time; 6 new endpoints + 1 reshaped page

## Constitution Check

*Constitution v1.2.1.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Layered contract-first data | N/A–PASS | No ETL layer touched. New HTTP surface is contract-first: NEW `contracts/web-ui-api.md` + amendments to 017 agent-tools (deltas 12–14) and 022 scan-api (delta 4) written at plan time |
| II. Streaming/bounded memory | N/A | No XML/pipeline work |
| III. Reproducible runs | N/A–PASS | ETL-scoped; the reused sync keeps its journaled/resumable semantics unchanged |
| IV. Data quality gates | N/A | No layer outputs changed |
| V. Agent-friendly surface | N/A | Published DuckDB untouched |
| VI. Components & contracts | PASS | `collection-agent` only; no cross-component imports; `frontend/` explicitly not touched (owner decision); coupling surfaces documented in contracts |
| VII(a) Config sources | PASS | ZERO new Settings fields; every knob reused (scan host/port/folder, models, web base URLs, snapshot path). Page poll cadence is a client-side UI constant, not runtime config |
| VII(b) Prompt authoring | PASS | `prompts/system.md` change is limited to runtime-neutral confirmation *procedure* wording (018/020 precedent); no schema/catalog prose added |
| VII(c) Read-only mechanics | PASS | Sync thread is daemon by design; consequence documented (kill mid-sync = existing interrupted case, journal resumes — research R5) |
| Secrets constraint | PASS | Static page grep-guard extends to the tabbed page; error bodies carry no token/key (022 discipline) |
| Workflow gates | PASS | Spec→clarify→plan artifacts committed per phase; component named above |

**Post-design re-check**: PASS — design added no violations; Complexity
Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/028-collection-web-ui/
├── spec.md              # + clarification session 2026-07-12
├── plan.md              # this file
├── research.md          # R1–R10
├── data-model.md        # web entities, payloads, state machines
├── quickstart.md        # run + owner live-validation checklist
├── contracts/
│   ├── web-ui-api.md                    # NEW contract
│   ├── amendment-017-agent-tools.md     # deltas 12–14
│   └── amendment-022-scan-api-4.md      # tabbed page delta
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks output (next phase)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── web/                      # NEW package
│   │   ├── __init__.py
│   │   ├── server.py             # create_web_app(): scan create_app + web routes
│   │   ├── chat.py               # WebChat: turn lock, transcript, plan confirm/cancel
│   │   ├── syncrun.py            # SyncRunner: background thread + status
│   │   ├── agent_factory.py      # build_web_agent(): web start_sync tool + shared registration
│   │   └── models.py             # ChatRequest/ChatResponse/History/PlanAction/CollectionStatus…
│   ├── scan/
│   │   ├── server.py             # UNCHANGED (or near-zero diff)
│   │   └── static/index.html     # reshaped: tab shell; scan behavior preserved
│   ├── tools/
│   │   ├── common.py             # + collection_page_url() (019 discipline)
│   │   ├── organize.py           # propose_moves detail → runtime-neutral wording
│   │   └── registration.py       # NEW: story-tool registration extracted from cli.py
│   ├── prompts/system.md         # runtime-neutral confirmation wording
│   └── cli.py                    # + serve alias; registration helper extraction; _cmd_scan → builds web app
└── tests/
    ├── unit/                     # syncrun state machine, chat lock/rewind, models,
    │   │                         #   collection_page_url + grep guards, page guards
    └── integration/              # TestClient: chat flow, plan gate, sync trigger/status,
                                  #   post-sync freshness (R6 pin), scan regression on tabbed page
```

**Structure Decision**: new `web/` package composes over the untouched
`scan/` package (research R1); the static page stays at its guard-tested
path. CLI keeps single-file dispatch with one extracted helper.

## Design highlights (what tasks will encode)

1. **Chat turn wrapper** (research R2): non-blocking lock → 409
   `chat_busy`; expire pending plan pre-turn; message-list rewind on
   exception → 502 `chat_error` + transcript error entry; pending plan
   view in the response.
2. **Write gate endpoints** (R3): confirm/cancel validate
   `plan_id` + `PROPOSED` under the chat lock; confirm calls the
   unchanged `execute_plan`; outcomes → transcript + response;
   runtime-neutral `propose_moves.detail` + system.md wording.
3. **Web `start_sync` tool** (R4): same name/schema, delegates to the
   SyncRunner, `full` ignored honestly; `snapshot_status` reused via
   `snapshot_status_payload`; story-tool registration shared via the
   extracted helper.
4. **SyncRunner** (R5): daemon thread over `run_sync(full=False)` with
   own DiscogsClient; states idle/running/complete/partial/failed;
   atomic check-and-start; warnings from `notify`.
5. **One polling endpoint** (R7): `GET /api/collection/status` =
   snapshot payload + `collection_url` (new grep-guarded
   `collection_page_url`) + sync status; `POST /api/sync` 202/409.
6. **Freshness pin** (R6): integration test proving a completed sync is
   visible to chat + duplicate checker in-process (guards against a
   future SnapshotStore cache).
7. **Page reshape** (R8): tab shell in the same static file; scan
   markup/JS functionally preserved; chat transcript + plan card + stale
   banner; collection status + sync progress + Discogs link; existing
   page guard tests must keep passing unmodified where they pin
   invariants (link shapes, no secrets), updated only where they pin
   incidental markup.
8. **CLI** (R9): `serve` subcommand + `scan` alias; startup builds
   agent + runner + `create_web_app`; OPENAI_API_KEY gate unchanged;
   027 container CMD/compose untouched (packaging guard tests must pass
   unmodified).

## Complexity Tracking

*No constitution violations — table intentionally empty.*
