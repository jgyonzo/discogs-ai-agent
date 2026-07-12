# Research: Collection-Agent Web UI (028)

All decisions below were made against the actual code on `main` (post-027).
No NEEDS CLARIFICATION items remain.

## R1 — Where the web surface lives: grow the scan server app

**Decision**: The web UI is the existing scan FastAPI app
(`scan/server.py::create_app`) extended by a new `web/` package. A new
composition entry point `web/server.py::create_web_app(...)` calls the
untouched `scan.server.create_app(...)` and registers the chat/collection
routes on the SAME app object. The `/` route keeps serving
`scan/static/index.html`, whose CONTENT becomes the tabbed page (Scan |
Chat | Collection). Same process, same port (:8022), same compose service.

**Rationale**: Owner decision 2026-07-12 (recorded in the spec). The scan
server already carries every discipline the feature needs: injected
collaborators for fully-stubbed TestClient tests, sync-def handlers on the
threadpool (022 addendum 2), the `{error:{code,message}}` envelope, the
no-secrets page rule, and 027 container packaging with :8022 published.
Registering routes on the returned app keeps `scan/server.py` diff at or
near zero (FR-002's regression-safety intent).

**Alternatives considered**: a second FastAPI app/port (two banners, two
compose ports, no shared session state — rejected); extending the
demo-stack `frontend/` React component (different compose profile,
lifecycle, and audience; would couple demo stack to the collection
profile and add CORS for no product win — rejected by owner);
a new component (right for the AWS/multi-tenancy track, premature for a
single-user LAN tool — rejected by owner).

## R2 — Chat over HTTP: the `run_turn` seam, one lock, and error hygiene

**Decision**: `POST /api/chat` calls the existing
`Agent.run_turn(user_text) -> str` on a server-held `Agent` built at
startup. One `threading.Lock` guards the conversation: acquired
non-blocking; a turn (or plan confirm/cancel) arriving while it is held
returns `409 {code: "chat_busy"}` (FR-004). Handlers are sync `def`s so
the threadpool absorbs the long LLM turn (same mechanics as scan's
vision calls, FR-023 precedent).

**Error hygiene (load-bearing)**: `run_turn` appends the user message
FIRST and may append an assistant message carrying `tool_calls` BEFORE
the tool results exist. If the LLM call raises mid-loop, the session's
`messages` can be left in a state the OpenAI API rejects on the next
request (a `tool_calls` assistant message with no following `tool`
messages). The web turn wrapper therefore snapshots
`len(session.messages)` before `run_turn` and truncates back to it on
any exception, then records a typed error transcript entry and returns
`502 {code: "chat_error"}` (FR-014). The CLI never needed this (an
exception kills the REPL); the web server lives on.

**Rationale**: `run_turn` is already exactly request/response shaped;
tools, registry, system prompt, bilingual `LANGUAGE_REMINDER`, and
LangSmith tracing (`@traceable` root + tool spans) all live below the
seam and carry over with zero changes. The truncate-on-error rule is
what makes "the session survives a failed turn" true rather than
aspirational.

**Alternatives considered**: per-turn queueing instead of 409 (hidden
latency, surprise answers minutes later — rejected; the page disables
send while busy anyway); token streaming (v2 nicety; run_turn is
synchronous and multi-round — out of scope per spec assumption);
per-browser sessions (deferred to the AWS/multi-tenancy track — spec
records the single-shared-session limitation).

## R3 — The web write gate: 022-R9 pattern over the existing WritePlan

**Decision**: The plan stays parked on `AgentSession.pending_plan`
exactly as today. `POST /api/chat` responses carry a `pending_plan`
payload (plan_id, target folder display, move displays, move_count)
whenever a turn leaves a `PROPOSED` plan. Two new runtime-gate
endpoints, both guarded by the chat lock:

- `POST /api/chat/plan/confirm {plan_id}` — 409 unless a pending plan
  exists AND its `plan_id` matches AND its state is `PROPOSED`; then
  sets `CONFIRMED` and calls the existing runtime-only
  `tools/organize.py::execute_plan` (per-move live re-validation,
  per-item results, snapshot patch — all unchanged). Per-move outcomes
  are returned AND appended to the web transcript.
- `POST /api/chat/plan/cancel {plan_id}` — sets `CANCELLED`, clears
  the pending plan; 409 on plan mismatch / nothing pending.

A new user turn expires any pending plan BEFORE `run_turn` (the web
equivalent of the CLI's anything-but-y-cancels; `propose_moves` itself
already calls `expire_pending_plan` when proposing anew). The confirm
handler only ever executes the server-held plan — the request carries
an id, never move data (FR-005). Server restart loses the in-memory
plan; a confirm after restart hits "nothing pending" and executes
nothing (FR-006).

**Wording fix required**: `propose_moves`' payload `detail` currently
steers the LLM with "The terminal will ask the user to confirm (y/N)…
tell them to confirm there" — wrong for the web runtime. The string
becomes runtime-neutral ("the app will now ask the user to confirm —
tell them to use the confirmation prompt; never state the move already
happened"). `prompts/system.md` gets the same neutrality check.
Contract delta recorded (amendment-017-agent-tools delta 13).

**Rationale**: `execute_plan` is deliberately NOT a ToolDef; the HTTP
confirm handler becomes the second sanctioned runtime gate beside the
CLI's y/N — the same construction 022's research R9 used for
`/api/add` (server-side allowlist + explicit confirmation). Unconfirmed
writes stay unreachable by construction in both runtimes.

**Alternatives considered**: replaying the CLI gate by keeping writes
terminal-only (rejected by owner decision 3); journaling chat plan
executions in the scan journal (different journal, different contract;
the spec keeps chat process-lived and journal-free — no new journal).

## R4 — The LLM's `start_sync` tool must not run the sync inline

**Decision**: The web runtime does NOT register the CLI's `start_sync`
ToolDef (whose injected callable runs the sync synchronously inside the
turn and renders a rich terminal progress bar). Instead the web agent
factory registers a web-owned `start_sync` ToolDef with the same name
and args whose implementation delegates to the shared `SyncRunner`
(R5): non-blocking start returning
`{started: true, detail: "sync running in the background — progress on
the Collection tab"}` or `{already_running: true, ...}` — and, per the
spec clarification, it IGNORES `full=true` with an honest note (full
re-sync is terminal-only in v1). `snapshot_status` is reused verbatim
via the already-public `tools/base.py::snapshot_status_payload`. The
story-tool registration loop currently private to the CLI
(`cli._register_story_tools`) is extracted to a neutral shared helper
so both runtimes register analytics/browse/media/organize/playlist
tools identically.

**Rationale**: blocking a chat turn for a minutes-scale sync would
freeze the conversation, fight the single-occupancy rule, and time out
LLM tool budgets; the CLI variant's `Progress` bars would write to the
server console mid-request. Delegating to the one SyncRunner keeps
single-occupancy coherent whether the sync is started by button or by
chat ("sync my collection" in the Chat tab works, honestly).

**Alternatives considered**: registering no sync tool in the web agent
(the LLM would tell users to go press the button — needless friction
when the delegation is 10 lines); running it inline without progress
(freezes the turn — rejected).

## R5 — SyncRunner: one background thread, observable, journal-backed

**Decision**: `web/syncrun.py::SyncRunner` — a small object holding a
mutex and a status snapshot `{state, phase, done, total, warnings,
error, meta_summary}`. `start()` refuses if a run is active (the 409
for `POST /api/sync` and the `already_running` tool payload), else
spawns ONE daemon thread executing the existing
`snapshot.sync.run_sync(client, store, settings, full=False,
on_progress=..., notify=...)` with its OWN `DiscogsClient` (closed in
`finally`). `on_progress(phase, done, total)` writes the status under
the runner's lock; `notify` messages append to `warnings`. Terminal
states map from the returned meta: `complete` iff
`meta.completeness == COMPLETE`, else `partial`; any exception ⇒
`failed` with the message. Re-triggering after partial/failed simply
starts a new run — `run_sync`'s enrichment journal resumes it
(unchanged semantics; 027 SC-003 proved resume across runtimes).

**Daemon thread is deliberate**: killing the server mid-sync equals the
existing interrupted-sync case — the journal (flushed every 10
enrichments) survives, the next run resumes. A non-daemon thread would
hold the process hostage for minutes on Ctrl-C, which is worse than the
already-designed-for interruption.

**Rationale**: `run_sync` is already callback-driven and
journal-resumable; the runner adds only occupancy + observability.

**Alternatives considered**: subprocess (`python -m collection_agent
sync`) — real isolation but loses in-process progress and complicates
the container story (one process per compose service); asyncio task —
the codebase is sync-def/threadpool throughout, and `run_sync` is
blocking; both rejected.

## R6 — Post-sync freshness is structural (no reload mechanism needed)

**Decision**: FR-010 requires no new code path. `SnapshotStore` holds
no in-memory cache: `load()` reads and validates the file on every
call. Chat tools go through `tools/common.py::load_for_serving(store)`
per tool call; the scan duplicate checker is constructed fresh per
request from `store` ("reads the snapshot as it is NOW", server.py
comment). The sync writes the final snapshot once, atomically
(`tmp + os.replace`), so a request during the sync reads the old
snapshot and the first request after completion reads the new one —
never a torn file. FR-010 is therefore pinned by an integration test
(sync completes ⇒ next chat answer/duplicate check reflects the fresh
snapshot in the same process), not implemented by new machinery.

**Rationale**: verifying the property beats building a redundant
reload bus. The test guards against a future SnapshotStore cache
silently breaking the web contract.

## R7 — Status + sync surface: ONE polling endpoint, server-built Discogs link

**Decision**: `GET /api/collection/status` returns everything the
Collection tab and the stale banner need in one payload: the snapshot
block (shape of `tools/base.py::snapshot_status_payload` — username,
synced_at, age_hours, completeness, counts, collection value, warnings,
folders) or `null`, plus `collection_url`, plus the SyncRunner status.
`POST /api/sync` starts a run (`202 {status: "started"}` /
`409 {code: "sync_already_running"}`). The page polls the one GET while
a sync runs and on tab activation. `collection_url` is built ONLY by a
new `tools/common.py::collection_page_url(settings, username)` =
`{DISCOGS_WEB_BASE_URL}/user/{username}/collection` — the `/user/`
path shape grep-guarded to exactly one src site, same 019 discipline
(and same test style) as `release_page_url`/`master_page_url`. The
static page renders the field verbatim; anchors `target="_blank"
rel="noopener noreferrer"`.

**Rationale**: one GET keeps the page's polling loop trivial and the
stale banner (FR-011) free — the Chat tab reads the same payload. The
username comes from the live identity resolved at startup (scan already
resolves it for the add path).

**Alternatives considered**: separate `/api/sync/status` (a second
poller for no gain — folded in); linking to the release-list page shape
or client-side URL minting (forbidden by 019 — rejected).

## R8 — The page: one self-contained file, three tabs, server-side transcript

**Decision**: `scan/static/index.html` stays the single self-contained
file (no build step, no external assets, no secrets) and gains a
three-tab shell. The existing scan markup/JS moves inside the Scan tab
unmodified in behavior; its guard-tested invariants (server-built links
only, `target="_blank" rel="noopener noreferrer"`, link anchors
structurally separate from add buttons, no hardcoded Discogs host) keep
holding on the same file path so `test_scan_page_links.py` and the
no-secrets grep keep passing. Chat tab: transcript list, send box
(disabled while busy), plan confirmation card (Confirm / Cancel), stale
banner with a Sync action. Collection tab: status block, Sync button,
progress line, "View on Discogs" link. The TRANSCRIPT of record lives
server-side (`web/chat.py` keeps a process-lived entry list: user,
assistant, error, and plan-outcome entries); `GET /api/chat/history`
returns it plus any pending plan, so a page reload reconstructs the
conversation view (FR-016). Poll cadence while a sync runs is a small
client-side constant in the page (~2s) — UI pacing, not runtime
config, so VII(a) does not apply.

**Rationale**: 022's page discipline is a recorded contract; tabs are
show/hide sections, not a framework. Keeping the transcript server-side
makes reload-safety a server property instead of localStorage state.

**Alternatives considered**: localStorage transcript (lies after a
server restart — the server is the truth of the session); splitting
per-tab HTML files (three fetches, shared JS duplication — rejected).

## R9 — CLI surface: `serve` becomes the name, `scan` stays a working alias

**Decision**: A new `serve` subcommand ("serve the collection web page:
scan + chat + collection status/sync") dispatches to the same
implementation as `scan`, which remains a fully working alias with its
existing help text pointing at `serve`. The startup sequence is
`_cmd_scan`'s, extended: same OPENAI_API_KEY gate (chat needs it too —
the gate now guards both consumers), same live folder validation and
identity resolution, plus building the web Agent (R4 factory) and the
SyncRunner, and calling `create_web_app`. The 027 container is
untouched: `CMD ["scan"]` keeps working verbatim, compose service
unchanged, image contents unchanged (the new `web/` package rides
inside `src/`).

**Rationale**: FR-015. Renaming-with-alias records the surface's real
scope without breaking the container CMD, docs, or muscle memory.

**Alternatives considered**: keeping only `scan` (misleading name for a
chat+sync surface); hard rename (breaks 027's image contract — rejected).

## R10 — Zero new dependencies, ZERO new Settings fields, shared rate budget accepted

**Decision**: No new dependencies (FastAPI/uvicorn already serve scan;
the agent loop is already in the package). No new `Settings` fields:
host/port/folder-id reuse the scan fields; models reuse
`collection_agent_model` / vision fields; the collection URL reuses
`discogs_web_base_url`; sync uses existing snapshot/rate settings. The
sync's DiscogsClient and the scan/chat-write clients are separate
instances sharing the per-token 60 req/min budget; both already honor
the header-driven governor, so concurrent use degrades to slower —
accepted per spec FR-013, surfaced in the UI by the sync-running state
from `GET /api/collection/status`.

**Rationale**: 025 proved a feature can land with zero new knobs; every
tunable this feature touches already has one. Mutual exclusion between
sync and scan/chat would trade a soft slowdown for a hard usability
wall (the phone scan flow dying for minutes) — rejected per spec.
