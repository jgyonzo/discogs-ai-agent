# Contract: Collection Web UI API (028)

**Status**: NEW contract (028-collection-web-ui). Sits beside — never
replaces — `specs/022-phone-record-scan/contracts/scan-api.md`; every scan
endpoint keeps its 022/026 contract verbatim. This document covers the
endpoints and page surface 028 adds to the SAME FastAPI app/process/port.

Trust model: plain HTTP, no auth, trusted home LAN (022's recorded v1
risk, explicitly extended by owner decision 2026-07-12 to cover
folder-move execution). Secrets never appear in any response or in the
page (static file; grep-guarded).

Error envelope (shared with scan-api): `{"error": {"code": "<slug>",
"message": "<human text>"}}`.

## §1 Page

- `GET /` serves the single self-contained tabbed page (Scan | Chat |
  Collection) from `scan/static/index.html`. No external assets, no build
  step, no client-side URL minting (019). All outbound links use
  `target="_blank" rel="noopener noreferrer"`.

## §2 Chat

### `POST /api/chat`

Request: `{"text": "<user message>"}`.

- `400 empty_message` — text empty/whitespace-only; no LLM call made.
- `409 chat_busy` — another turn or plan action holds the conversation
  lock. Never queued, never interleaved.
- `502 chat_error` — the turn failed (provider error/timeout). The
  session is REWOUND to its pre-turn message state (research R2) and an
  `error` entry is appended to the transcript; the conversation remains
  usable.
- `200` → `{"reply": "<assistant text>", "pending_plan": PendingPlan|null}`

`PendingPlan = {"plan_id", "target_folder", "move_count", "moves": [str]}`
— display strings only; the client can echo back ONLY `plan_id`.

Semantics:
- The turn runs the production `Agent.run_turn` — same tools, registry,
  system prompt, bilingual reminder, tracing as terminal chat.
- A new turn EXPIRES any still-pending plan before running (the web
  analogue of the CLI's anything-but-y cancels); a `plan_cancelled`
  transcript entry records it.
- One shared conversation per server process.

### `GET /api/chat/history`

`200` → `{"entries": [ChatEntry], "pending_plan": PendingPlan|null,
"snapshot_state": "complete"|"partial"|"stale"|"missing"}`

`ChatEntry.kind ∈ {user, assistant, error, plan_result, plan_cancelled}`;
`plan_result` entries carry `moves: [{display, result, error|null}]`.
The transcript is process-lived; a server restart starts it empty.
`snapshot_state` drives the Chat tab's stale/absent banner (FR-011).

### `POST /api/chat/plan/confirm`

Request: `{"plan_id": "<id>"}`.

- `409 chat_busy` — lock held (a turn is running).
- `409 no_pending_plan` — nothing pending (incl. after cancel,
  expiry, execution, or server restart). Nothing executed.
- `409 plan_mismatch` — a plan is pending but its id differs. Nothing
  executed.
- `200` → `{"target_folder": str, "moves": [{display, result: "ok"|"failed",
  "error": str|null}]}`

Semantics (the second sanctioned runtime write gate; see
amendment-017-agent-tools delta 12):
- Confirms and executes ONLY the server-held `WritePlan` via the existing
  runtime-only `execute_plan`: folder created if planned (live collision
  re-check), per-move LIVE re-validation, per-item results, snapshot
  patched in place. The request can never supply move data.
- Outcomes are appended to the transcript as a `plan_result` entry and
  the pending plan is cleared.

### `POST /api/chat/plan/cancel`

Request: `{"plan_id": "<id>"}`. Same 409s as confirm; `200 →
{"status": "cancelled"}`. Sets the plan `CANCELLED`, clears it, appends a
`plan_cancelled` entry. Executes nothing, ever.

## §3 Collection status + sync

### `GET /api/collection/status`

`200` → `{
  "snapshot": <snapshot_status_payload shape> | null,
  "collection_url": "<server-built owner collection page URL>",
  "sync": {"state": "idle"|"running"|"complete"|"stale"|"partial"|"failed",
            "phase": str|null, "done": int|null, "total": int|null,
            "warnings": [str], "error": str|null, "finished_at": str|null}
}`

- `snapshot` is exactly the shape of `tools/base.py::
  snapshot_status_payload(store)["snapshot"]` (username, synced_at,
  age_hours, completeness, counts, collection_value, warnings, folders);
  `null` when no snapshot exists.
- `collection_url` is built ONLY by
  `tools/common.py::collection_page_url(settings, username)` =
  `{DISCOGS_WEB_BASE_URL}/user/{username}/collection` — the `/user/`
  path shape exists at exactly one src site (grep-guarded, 019
  discipline).
- This is the ONE polling endpoint: the page polls it while
  `sync.state == "running"` and on tab activation; the Chat tab's stale
  banner reads the same payload.

### `POST /api/sync`

No body.

- `202` → `{"status": "started"}` — a background run began. Web sync is
  ALWAYS the standard sync (`full=False`; resume-if-interrupted,
  refresh otherwise — clarification 2026-07-12). Full re-sync is not
  reachable over HTTP.
- `409 sync_already_running` — single occupancy; check-and-start is
  atomic.

Failure posture: a failed/interrupted run leaves `sync.state`
`failed`/`partial` with honest detail; re-POST resumes via the existing
enrichment journal. Killing the server mid-run equals the existing
interrupted-sync case (journal survives; next run resumes).

`sync.state == "stale"` (replay addendum 4, FR-017): the run finished
every enrichment but a live write (scan add / confirmed move) landed
while it ran, so the persisted snapshot is `stale`, not `complete`
(rule in `amendment-017-snapshot-schema.md`). The warning naming the
cause is in `sync.warnings`; the page tells the owner to Sync again
(quick — the kept journal means only new releases are enriched).

### Chat-initiated sync

The web agent's `start_sync` tool (amendment-017-agent-tools delta 13)
delegates to the SAME runner: `{started: true, ...}` /
`{already_running: true, ...}`, `full` ignored with an honest note.
Occupancy is therefore global across button and chat.

## §4 Interplay invariants

1. Scan endpoints remain available and contract-identical during a chat
   turn and during a sync (threadpool handlers; shared Discogs rate
   budget may slow them — accepted, FR-013).
2. A completed sync is visible to the NEXT chat answer, duplicate check,
   and status read in the same process, with no restart (structural —
   `SnapshotStore.load()` reads per call; test-pinned).
3. `vision`/eval/scan pipelines are untouched by every endpoint in this
   contract; none of them is ever called by the chat/collection routes.
4. Nothing in this contract adds a Discogs API consumption shape: chat
   writes reuse 017 §4's already-contracted folder/move/create calls via
   `execute_plan`; the sync reuses 017's sync consumption. Zero new
   Discogs reads or writes ⇒ no amendment to the discogs-consumption
   contract.
