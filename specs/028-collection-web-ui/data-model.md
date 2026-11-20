# Data Model: Collection-Agent Web UI (028)

All new state is **process-lived** (in memory, dies with the server) except
what existing machinery already persists (snapshot, enrichment journal,
scan session journal). No new persisted artifact, no journal schema change,
no snapshot schema change.

## New entities (web layer, `collection_agent/web/`)

### WebChat (`web/chat.py`)

The single server-held conversation wrapper. One instance per server
process (spec: accepted v1 limitation).

| Field | Type | Notes |
|---|---|---|
| `agent` | `Agent` | Built once at startup by the web agent factory (R4); owns the `AgentSession` (messages, last-listing, `pending_plan`) |
| `transcript` | `list[ChatEntry]` | UI-facing record of the conversation; source of truth for `GET /api/chat/history` |
| `lock` | `threading.Lock` | Non-blocking acquire; held for a whole turn AND for plan confirm/cancel. Busy ⇒ `409 chat_busy` |

Turn algorithm (FR-004/005/006/014, research R2/R3):

1. acquire lock non-blocking (fail ⇒ 409)
2. expire any `PROPOSED` pending plan (new turn cancels it; a
   `plan_cancelled` entry is appended)
3. `n = len(session.messages)`; append `user` entry
4. `reply = agent.run_turn(text)` — on ANY exception: truncate
   `session.messages` to `n`, append `error` entry, return
   `502 chat_error` (session stays usable)
5. append `assistant` entry; if `session.pending_plan` is `PROPOSED`,
   build `PendingPlanView` and include it in the response

### ChatEntry (transcript line)

| Field | Type | Notes |
|---|---|---|
| `kind` | `"user" \| "assistant" \| "error" \| "plan_result" \| "plan_cancelled"` | |
| `text` | `str` | user/assistant/error text; for `plan_result` a short heading (e.g. "Moved 3 record(s) to Tango") |
| `moves` | `list[MoveOutcomeView]` \| absent | `plan_result` only |

### PendingPlanView (over the existing `WritePlan` — no model change)

Built from `AgentSession.pending_plan`; the page renders ONLY this view
and echoes back ONLY `plan_id`.

| Field | Type | Source |
|---|---|---|
| `plan_id` | `str` | `WritePlan.plan_id` |
| `target_folder` | `str` | `TargetFolder.name` + `" (new)"` when `create` (same rendering as the CLI table) |
| `move_count` | `int` | `len(plan.moves)` |
| `moves` | `list[str]` | `PlannedMove.display` each |

### MoveOutcomeView

| Field | Type | Source |
|---|---|---|
| `display` | `str` | `PlannedMove.display` |
| `result` | `"ok" \| "failed"` | `PlannedMove.result` after `execute_plan` |
| `error` | `str \| null` | `PlannedMove.error` |

### SyncRunner (`web/syncrun.py`)

Single-occupancy background executor over the existing
`snapshot.sync.run_sync` (research R5).

| Field | Type | Notes |
|---|---|---|
| `state` | `"idle" \| "running" \| "complete" \| "partial" \| "failed"` | see state machine |
| `phase` | `str \| null` | verbatim from `on_progress` (e.g. "collection pages", "enriching releases") |
| `done`, `total` | `int \| null` | verbatim from `on_progress` |
| `warnings` | `list[str]` | `notify` messages (rate-limit notices etc.) |
| `error` | `str \| null` | `failed` only |
| `finished_at` | `str \| null` | ISO-8601 UTC of last terminal transition |

State machine:

```
idle ──start()──▶ running ──meta.completeness==complete──▶ complete
                   │  │
                   │  └──meta returned but not complete──▶ partial
                   └──exception──▶ failed
complete|partial|failed ──start()──▶ running   (journal resumes a partial)
running ──start()──▶ REFUSED (409 sync_already_running / already_running tool payload)
server killed while running ⇒ enrichment journal survives ⇒ next run resumes
```

`start()` always runs `full=False` (clarification 2026-07-12: web sync is
standard-sync only).

## Endpoint payloads (`web/models.py`, pydantic — full shapes in contracts/web-ui-api.md)

| Model | Used by | Fields |
|---|---|---|
| `ChatRequest` | `POST /api/chat` | `text: str` (non-empty after strip) |
| `ChatResponse` | `POST /api/chat` | `reply: str`, `pending_plan: PendingPlanView \| null` |
| `HistoryResponse` | `GET /api/chat/history` | `entries: list[ChatEntry]`, `pending_plan: PendingPlanView \| null`, `snapshot_state: str` |
| `PlanActionRequest` | confirm / cancel | `plan_id: str` |
| `PlanConfirmResponse` | confirm | `target_folder: str`, `moves: list[MoveOutcomeView]` |
| `CollectionStatusResponse` | `GET /api/collection/status` | `snapshot: dict \| null` (shape of `snapshot_status_payload`), `collection_url: str`, `sync: SyncStatusView` |
| `SyncStatusView` | inside status | `state, phase, done, total, warnings, error, finished_at` |

Error envelope: unchanged scan shape `{"error": {"code", "message"}}`.
New codes: `chat_busy`, `chat_error`, `empty_message`, `no_pending_plan`,
`plan_mismatch`, `sync_already_running`.

## Existing entities touched (and how)

| Entity | Change |
|---|---|
| `AgentSession` / `WritePlan` / `PlanState` | **None.** The web layer reads `pending_plan`, drives the same state transitions the CLI does (PROPOSED→CONFIRMED→EXECUTED / →CANCELLED / →EXPIRED) |
| `SnapshotStore` / `Snapshot` / `SnapshotMeta` | **None.** Freshness after sync is structural (`load()` re-reads per call — research R6, test-pinned) |
| `propose_moves` payload | `detail` string becomes runtime-neutral (research R3; contract delta 13) — same fields, no schema change |
| Scan models / journal / session | **None.** Scan endpoints byte-identical |
| `tools/common.py` | + `collection_page_url(settings, username)` (019 discipline, grep-guarded `/user/` shape) |
| `cli.py` | + `serve` alias parser; story-tool registration extracted to a shared helper (behavior identical) |
| `scan/static/index.html` | Content reshaped into the tabbed page; scan behavior and guard-tested invariants preserved |

## Validation rules

- `ChatRequest.text`: reject empty/whitespace-only with `400 empty_message`
  (never spends an LLM call on nothing).
- `PlanActionRequest.plan_id`: must equal the CURRENT pending plan's id and
  that plan must be `PROPOSED`; anything else is `409` (`no_pending_plan`
  when none is held, `plan_mismatch` when ids differ). Confirm/cancel of an
  executed, cancelled, expired, or restart-lost plan can therefore never
  write (FR-006).
- Confirm executes ONLY the server-held `WritePlan`; the request carries no
  move data (FR-005).
- `POST /api/sync` while `state == "running"` ⇒ `409 sync_already_running`
  (FR-009); the runner's internal mutex makes the check-and-start atomic.
