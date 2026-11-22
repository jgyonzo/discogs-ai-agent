# Feature Specification: Collection-Agent Web UI

**Feature Branch**: `028-collection-web-ui`
**Created**: 2026-07-12
**Status**: Draft
**Input**: User description: "Grow the existing scan server and its self-contained static page into a single multi-tab web frontend for the collection-agent, serving Scan, Chat, and Collection (status + sync) on the trusted home LAN. Owner decisions (2026-07-12): grow the scan page — do not touch the demo-stack frontend component, do not create a new component; v1 surface = scan + chat + status + sync-trigger; browsing the full collection is out of scope (a link to the owner's collection page on the Discogs website suffices); folder-move execution via web chat IS allowed behind the existing no-auth trusted-LAN surface — explicit owner decision extending 022's recorded v1 risk."

## Clarifications

### Session 2026-07-12

- Q: What should the web Sync button do — and should full re-sync (the terminal's `sync --full`) be reachable from the page? → A: Standard sync only. The button runs exactly what terminal `sync` (no flags) does: resume if interrupted, refresh otherwise. Full re-sync stays terminal-only in v1.

## Replay Addenda

### Addendum 1 — header snapshot badge went stale (2026-07-12, live validation)

During owner live validation (SC-003 flow), a completed sync updated the
Collection tab correctly but the page header kept reading
"snapshot: stale": the badge was rendered once at page load (from the
health check) and never refreshed. FR-011 is sharpened accordingly:
**every on-page indication of snapshot state** — the Chat banner AND the
header badge — must reflect the current state after any state-changing
event in the same page session (sync completion, scan add marking the
snapshot stale, chat-initiated sync), without a page reload. Fix: the
Collection status loader re-renders the header badge on every load
(including each progress poll), and the chat-turn and scan-add paths
trigger a status refresh; wiring guard-pinned in
`test_web_page_guards.py`.

### Addendum 2 — markdown answers + no in-flight feedback (2026-07-12, live validation)

Two owner findings from the first live chat session: (1) answers arrived
as markdown (asterisks, headings) rendered raw in the chat bubbles — the
shared system prompt and the LLM's habits assume a terminal/markdown
consumer; (2) after submitting a prompt the page gave no feedback until
the reply landed (a turn can take tens of seconds).

FR-003 is sharpened: the web runtime MUST present answers readable in its
own medium — it appends a transient plain-text-format instruction to
every LLM request (the 020 `LANGUAGE_REMINDER` decision-point pattern:
sent after the language reminder, never persisted, terminal requests
byte-identical), and the page renders bare URLs in assistant bubbles as
tappable new-tab links (rendering LLM-relayed tool-built URLs — the page
still never constructs one). FR-014/UX: the page MUST show a visible
working indicator from submit until the reply, error, or plan-execution
outcome arrives. Wiring guard-pinned in `test_web_page_guards.py`; the
reminder's wire placement pinned in `test_web_agent_factory.py`;
recorded as agent-tools delta 15.

### Addendum 3 — plan appeared "duplicated" at confirm time (2026-07-13, live validation)

During the owner's first live folder-move via web chat (moves found and
executed correctly), the plan appeared twice on screen. Code analysis:
the confirm-card slot renders at most one card (cleared before every
render), so the duplication is presentational — the `propose_moves`
payload hands the LLM the full move list and the model echoes it in its
reply bubble, immediately above the card rendering the same list. The
terminal duplicates identically (LLM narration + the CLI's own plan
table). Fix: the shared `propose_moves` payload `detail` now instructs
the LLM to summarize (count + folder) and NOT re-list the moves — the
app's rendering (card / CLI table) is the single presentation of the
plan. Steering-level fix; if the duplication recurs, escalate per the
018 ladder (e.g., withholding the display list from the LLM payload).

**Round 2 (2026-07-13, owner re-observation)**: the steering helped but
the owner pinned the real remaining cause — tapping Confirm showed the
"Executing moves" indicator while the confirm card STAYED on screen
(buttons live) for the seconds the per-move live re-validation takes;
the card was only cleared when the response arrived. Fix: the card is
removed synchronously at tap time (confirm AND cancel), before the
request; on failure the card is re-rendered from server truth
(`/api/chat/history`'s pending plan) so it returns exactly when the plan
is genuinely still pending. Ordering guard-pinned in
`test_web_page_guards.py`. (Server-side, a double-tap was always safe —
lock + spent-plan 409 — this was purely a presentation bug.)

### Addendum 4 — scan add during a sync lost; snapshot claimed complete (2026-11-20, live validation)

During the owner's block-C validation (SC-005/SC-006, server session
`20261120-214751Z`), a record was scanned and added while a page sync
was running. Timeline: the sync started ~21:58:18Z (406.2 s run) and
finished its instance pass within seconds; the add (release `29147545`,
journaled `added` at 22:00:29Z) succeeded on Discogs and flipped the
on-disk snapshot to `stale`; at 22:05:04Z the sync wrote ITS snapshot —
built from the pre-add instance listing — as `complete`, overwriting the
stale mark. Result: the record exists on Discogs, is absent from the
local snapshot, and the snapshot claimed `complete` (verified: 400
instances, `29147545` absent).

Root cause — a lost update: the only "a live write happened" signal
(`SnapshotStore.mark_stale`, and implicitly `patch_moved_instances` for
chat moves) lives inside the very file the running sync replaces
unconditionally at its end; the sync never learns a write landed after
its instance pass. Consequences: the 018-class confident wrong answer
(chat: "not in your collection" while status reads complete), and after
a restart the scan duplicate overlay would treat the record as not owned
— letting a second copy be added WITHOUT the duplicate double-confirm.
A chat-confirmed move during a sync is lost the same way (the snapshot
reverts to the pre-move folder while claiming complete). The race
existed in principle since 022 (terminal `sync` in one process, scan
server in another), but 028's FR-013 made scan/chat-during-sync a
supported, advertised flow; the original edge case only considered the
shared rate budget.

New **FR-017** (below). Fix shape (owner-approved 2026-11-21 — mutual
exclusion rejected, it contradicts FR-013): a durable live-write marker
beside the snapshot, bumped by every snapshot-affecting live write
(`mark_stale`, `patch_moved_instances` — the only two writers; both
record the marker even when no snapshot exists yet); `run_sync` reads it
before its first Discogs request and again under the store's write lock
right before its final save — a changed marker downgrades a would-be
`complete` result to `stale` (with a warning), and the enrichment
journal is KEPT so the follow-up standard sync re-lists instances and
enriches only the new releases (seconds, not a full re-enrichment). The
store's read-modify-write paths and the sync's final compare-and-save
are serialized by a per-path in-process lock, closing the
milliseconds-wide window where a patch could overwrite the sync's fresh
snapshot with an older one. `scan/server.py` diff stays zero (R1
composition rule preserved — the fix lives in the shared snapshot core,
so the terminal sync benefits identically: cross-process detection via
the on-disk marker). The SyncRunner gains a `stale` terminal state; the
page tells the owner to Sync again. Recorded as
`contracts/amendment-017-snapshot-schema.md` (FIRST amendment to 017's
snapshot-schema contract) + web-ui-api §3 sync-state delta. Known
trade-off: a kept journal is reused by the next standard sync whenever
it runs (pre-existing interrupted-sync semantics; `sync --full` ignores
it).

### Addendum 5 — duplicate badge double-counted a synced session add (2026-11-21, live validation)

During SC-004 (block B, same server run as the SC-003 re-validation),
scanning a record added earlier in that run showed "already in your
collection — 2 copies (incl. this session)" — the owner has ONE copy.
Cause: the 022 duplicate overlay computes `copies = snapshot instances +
session adds`; that sum is right only while the session's adds are NOT
yet in the snapshot. A same-process page sync (SC-003's standard flow:
add → Sync → scan again) absorbs the add into the snapshot, and the
session counted it a second time. Latent since 022 (only reachable with
a terminal sync while the scan server kept running); 028 made it the
normal path — the same session↔snapshot reconciliation family as
addendum 4. Errs high only (never lets a duplicate through without the
double-confirm), but displays a false count.

New **FR-018** (below). Fix: the overlay subtracts session adds already
absorbed by the snapshot, matched exactly by the `instance_id` Discogs
returned for each add (already on the session's in-memory log/journal
lines since 022). An add whose `instance_id` is unknown stays counted
(conservative, pre-fix behavior); `added_this_session` and the
`in_collection` state are unchanged, so the duplicate double-confirm
gate behaves exactly as before. Confined to
`scan/search.py::snapshot_duplicate_checker` — `scan/server.py` diff
stays zero; recorded as a delta in `amendment-022-scan-api-4.md`.
Owner-deferred UX follow-up observed in the same session (NOT fixed
here): "Show other pressings" results render as a second list under
"Other possibilities" with rows that look repeated — they are distinct
releases (the endpoint dedupes by release_id against everything shown
in the cycle) whose versions-payload fields make sibling pressings look
alike; candidate future UX = one list grouped by master with the
distinguishing fields (country/catno/format) emphasized.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chat with the collection from any LAN device (Priority: P1)

The owner opens the collection page on a phone or laptop on the home network, switches to the Chat tab, and converses with the collection agent exactly as they would in the terminal: analytics questions, locating records, play links, and organization proposals — in English or Spanish. When the agent proposes folder moves, the page shows the proposed plan as an explicit confirmation card; nothing is written to Discogs unless the owner taps Confirm. Declining (or simply asking something else) cancels the plan.

**Why this priority**: Chat is the headline capability being brought to the web — everything else (status, sync) supports it. It is also the only part with a write path, so its safety gate is the feature's most important behavior.

**Independent Test**: With a synced snapshot present, open the page from a second device, ask a collection question in the Chat tab, and receive a correct answer; then ask for an organization change, see a confirmation card, decline it, and verify nothing changed on Discogs.

**Acceptance Scenarios**:

1. **Given** a complete snapshot and a running server, **When** the owner sends "how many records do I have from Germany?" in the Chat tab, **Then** the answer appears in the conversation and matches what the terminal chat answers for the same snapshot.
2. **Given** an ongoing web conversation, **When** the agent proposes folder moves, **Then** the page shows a confirmation card listing every proposed move, and no write occurs until the owner explicitly confirms on that card.
3. **Given** a visible confirmation card, **When** the owner declines it (or sends a new message instead), **Then** the plan is cancelled, no write occurs, and the conversation continues normally.
4. **Given** a visible confirmation card, **When** the owner confirms it, **Then** each move is re-validated against the live collection before execution, the outcome (moved / skipped with reason) is reported in the conversation, and successful moves are patched into the local snapshot in place (it stays complete — matching terminal semantics).
5. **Given** a turn already being processed, **When** the owner tries to send another message, **Then** the page prevents the second send until the current turn completes (one shared conversation, one turn at a time).
6. **Given** the language the owner writes in (English or Spanish), **When** the agent replies, **Then** the reply is in the owner's language, matching the terminal chat's existing bilingual behavior.

---

### User Story 2 - See collection status and trigger a sync from the page (Priority: P2)

The owner opens the Collection tab and sees the local snapshot's state at a glance: complete/partial/stale, record counts, and when it was last synced. If the snapshot is stale or partial, a Sync button starts the existing journaled sync in the background; the page shows live progress (phase, done/total) until completion. When the snapshot is stale, the Chat tab shows a banner with the same Sync action — the web equivalent of the terminal chat's "Sync now?" prompt.

**Why this priority**: Status and sync close the loop that makes web chat trustworthy — after scanning-and-adding records from the phone, the owner can refresh the snapshot from the same page instead of returning to a terminal.

**Independent Test**: With a stale snapshot (e.g., after a scan add), open the Collection tab, see the stale state, tap Sync, watch progress reach completion, and verify the status now reads complete with updated counts — all without restarting the server.

**Acceptance Scenarios**:

1. **Given** any snapshot state, **When** the owner opens the Collection tab, **Then** it shows the snapshot state (complete/partial/stale/absent), record counts, and last-sync time, matching what the terminal `status` command reports.
2. **Given** a stale or partial snapshot, **When** the owner taps Sync, **Then** the existing journaled, resumable sync runs in the background and the page shows live progress (phase and done/total counts) until it finishes.
3. **Given** a sync already running, **When** the owner taps Sync again (from any device), **Then** the request is refused with a clear "sync already running" message and no second sync starts.
4. **Given** a sync that just completed, **When** the owner asks a chat question or scans a record, **Then** answers and duplicate warnings reflect the fresh snapshot without a server restart.
5. **Given** a stale snapshot, **When** the owner opens the Chat tab, **Then** a stale-snapshot banner with a Sync action is visible; syncing clears the banner once complete.
6. **Given** a sync that fails or is interrupted partway, **When** the owner views the Collection tab, **Then** the partial state is shown honestly and tapping Sync again resumes from where it left off (existing journal semantics).

---

### User Story 3 - One page for everything, scan preserved (Priority: P3)

The owner navigates one page with three tabs — Scan, Chat, Collection. The Scan tab behaves exactly as the existing scan page does today (photo scan, manual search, selected match with alternatives, other pressings, duplicate warnings, add with confirmation). The Collection tab offers a link that opens the owner's collection on the Discogs website for full browsing.

**Why this priority**: Navigation glue and continuity. Scan already works; this story only guarantees it survives the reshape intact and that the page is a single coherent surface.

**Independent Test**: Run the existing scan quickstart flow (photo → candidates → add) inside the new tabbed page and verify identical behavior; switch tabs mid-session and verify scan state handling is sane; tap the Discogs collection link and land on the owner's collection page.

**Acceptance Scenarios**:

1. **Given** the new tabbed page, **When** the owner performs the full scan flow (photo scan, manual search, other pressings, duplicate confirm, add, skip), **Then** behavior is functionally identical to the pre-028 scan page.
2. **Given** the Collection tab, **When** the owner taps the "View on Discogs" link, **Then** the owner's collection page on the Discogs website opens in a new browser tab, and the link was built by the server (never assembled client-side).
3. **Given** any tab, **When** the owner switches tabs and returns, **Then** the page does not lose an in-flight scan cycle or chat conversation view.

---

### Edge Cases

- **No snapshot at all (first run)**: Chat tools cannot answer collection questions. The Chat tab must surface the absent-snapshot state (banner pointing to Sync) rather than failing opaquely; the Collection tab shows "absent" and offers Sync.
- **Concurrent chat turns from two devices**: One shared conversation per server process (accepted v1 limitation). A turn arriving while another is processing is refused with a clear busy signal (per FR-004) — never interleaved into a corrupted conversation.
- **Pending move plan superseded**: A new user message while a plan is pending cancels the plan (mirrors the terminal behavior where anything but "y" cancels, and the session expires pending plans on the next turn). A confirm arriving for an already-expired/cancelled plan is refused with a clear message and executes nothing.
- **Server restart with a pending plan**: The pending plan is in-memory and lost; a confirm after restart is refused. No write can occur without a live, server-held plan.
- **Sync and scan at the same time**: Both consume the same Discogs per-token rate budget. Accepted for v1: scanning during a sync stays functional but slower; the UI notes that a sync is running. No mutual exclusion.
- **Live write during a sync** (addendum 4): A scan add or chat-confirmed move that succeeds while a sync is running may be missing from that sync's snapshot (its instance pass already ran). The sync MUST NOT then claim `complete`: it ends `stale` and the page asks for another Sync, which is quick (enrichment reused) and includes the write (FR-017).
- **Chat turn fails (LLM/provider error, missing key)**: The failure is reported in the conversation as an error message; the session and page remain usable. A missing OpenAI key is surfaced when chat is used, not by crashing the server (scan startup validation semantics are unchanged).
- **Sync fails mid-run (network, rate-limit exhaustion, Discogs error)**: Progress stops, the failure is reported on the page, snapshot state shows partial, and re-triggering resumes (existing journal/resume semantics).
- **Move confirm partially fails**: Per-item live re-validation means some moves may execute and others be skipped; the per-item outcome is reported honestly (matching terminal behavior).
- **Long turns**: A chat turn may take tens of seconds (multi-tool turns). The page shows a busy indicator and other endpoints (scan, status) remain responsive.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The collection-agent's existing web server MUST serve one self-contained page with three views — Scan, Chat, Collection — reachable from every device on the LAN that can reach the current scan page. No new component, no build step, no secrets ever delivered to the browser (022 discipline).
- **FR-002**: All existing scan behavior (photo scan, manual search, selected match + alternatives, on-demand pressings, duplicate double-confirmation, add, skip, session log, supersede semantics, journal semantics) MUST be preserved functionally unchanged inside the Scan view. Existing scan API behavior is not modified by this feature.
- **FR-003**: The Chat view MUST send user turns to the server and render agent replies from the same conversational agent the terminal uses — same tools, same attribute registry, same system prompt, same bilingual behavior, same observability (tracing when configured).
- **FR-004**: The server MUST hold exactly one shared conversation session per server process (accepted single-user v1 limitation). Turns MUST be processed one at a time; a turn arriving while another is in flight MUST be refused with a clear busy signal, never interleaved.
- **FR-005**: The web write gate MUST mirror the terminal gate's guarantees: when the agent proposes folder moves, the server holds the proposed plan; the page renders it as an explicit confirmation card; only an explicit confirm action from the owner executes it, with per-item live re-validation before each write. Agent/LLM output MUST NOT be able to trigger a write directly, and a confirm MUST only execute the exact server-held plan (never client-supplied move data).
- **FR-006**: A pending plan MUST be cancellable: an explicit decline, or any new user turn, cancels it. A confirm referencing a plan that is no longer pending (cancelled, superseded, already executed, or lost to restart) MUST be refused with a clear message and MUST execute nothing.
- **FR-007**: After a confirmed plan executes, the outcome per move (moved / skipped with reason) MUST be reported in the conversation, and successful moves MUST be patched into the local snapshot in place so it stays complete (matching terminal semantics — folder moves patch, only scan adds mark stale).
- **FR-008**: The Collection view MUST show the local snapshot's status — state (complete/partial/stale/absent), record and folder counts, and last-sync time — equivalent in content to the terminal `status` command, via a read-only request.
- **FR-009**: The owner MUST be able to trigger the existing journaled, resumable collection sync from the page, with the exact semantics of the terminal `sync` command without flags (resume if interrupted, refresh otherwise); full re-sync (`--full`) is NOT reachable from the page in v1 and stays terminal-only. The sync runs in the background; at most one sync runs at a time — a trigger while one is running MUST be refused with a clear conflict message. Progress (phase, done/total) MUST be observable from the page while the sync runs, and completion or failure MUST be reported honestly. A failed/interrupted sync MUST be resumable by triggering again (existing journal semantics).
- **FR-010**: When a sync completes, the server's in-memory view of the snapshot — used by chat answers and by the scan duplicate checker — MUST reflect the fresh snapshot without a server restart.
- **FR-011**: When the snapshot is stale, partial, or absent, the Chat view MUST show a banner stating the snapshot condition with a direct Sync action (the web translation of the terminal chat's "Sync now?" prompt). The banner clears once the snapshot is complete.
- **FR-012**: The Collection view MUST include a link to the owner's collection page on the Discogs website, opening in a new browser tab. The link MUST be built by the server from configuration (019 link discipline — the page never assembles Discogs URLs client-side).
- **FR-013**: Running a sync MUST NOT block scanning or chat: both remain functional during a sync (slower is acceptable — shared Discogs rate budget), and the page MUST indicate that a sync is in progress. No mutual exclusion between sync and scan/chat in v1.
- **FR-014**: Chat turn failures (provider errors, timeouts, missing credentials for chat) MUST surface as readable error messages in the conversation without crashing the server, the session, or the other views. Server startup semantics for the existing scan validation are unchanged.
- **FR-015**: The way the owner launches the server today — the existing subcommand, the container image, and the compose service from 027 — MUST keep working unchanged. If the launch command gains a new name, the existing name MUST remain a working alias (the 027 container default command must not break).
- **FR-016**: The web conversation transcript lives for the duration of the server process (parity with a terminal chat session); persistence of chat history across restarts is out of scope. Reloading the page MUST NOT wipe the server-side conversation; the page reflects the current server-side conversation state on load.
- **FR-017** (addendum 4): A sync during which any snapshot-affecting live write succeeded (scan add, chat-confirmed folder move — from this process or another) MUST NOT persist its result as `complete`: it persists `stale` with a warning naming the cause, keeps its enrichment journal so the next standard sync only enriches new releases, and reports a distinct `stale` terminal state so the page tells the owner to Sync again. A sync with no concurrent write behaves exactly as before. No live write is ever lost from the snapshot's honesty: either it is in the snapshot, or the snapshot is not `complete`.
- **FR-018** (addendum 5): The scan duplicate overlay's copy count MUST count each owned copy once: a release added in the current server run MUST NOT be counted again once the snapshot already contains that add's instance (matched by the `instance_id` Discogs returned). Adds not (yet) in the snapshot, or whose `instance_id` is unknown, stay counted. The `in_collection` state, `added_this_session` flag, and the duplicate double-confirmation gate are unchanged.

### Key Entities

- **Conversation session**: The single server-held chat context — message history, last-listing state, pending move plan. One per server process; shared by all LAN devices.
- **Pending move plan**: The server-held set of proposed folder moves awaiting explicit owner confirmation. Exists only in memory; cancelled by decline, a new turn, supersession, or restart. The only path to a folder-move write.
- **Sync run**: A background execution of the existing two-phase journaled sync, with observable progress (phase, done, total), a terminal outcome (complete / failed / interrupted), and a single-occupancy rule (at most one at a time).
- **Snapshot status**: The read-only view of the local snapshot's state (complete/partial/stale/absent), counts, and last-sync time that drives the Collection view and the stale banner.
- **Page views (tabs)**: Scan (existing behavior), Chat (conversation + confirm cards + stale banner), Collection (status + sync + Discogs link).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a phone on the home LAN, the owner asks a collection question in the Chat tab and receives an answer that matches the terminal chat's answer for the same snapshot — with no terminal involved.
- **SC-002**: A folder-move request made through web chat produces a confirmation card; declining results in zero changes on Discogs (verified live), and confirming executes exactly the listed moves with per-item outcomes reported. At no point can a write occur without the owner's explicit confirm action.
- **SC-003**: After adding a record via the Scan tab (snapshot goes stale), the owner triggers a sync from the page, watches progress to completion, and the Collection tab reads complete with updated counts — all in one server run, no restart. A chat question asked immediately after reflects the newly added record.
- **SC-004**: The full pre-028 scan quickstart flow (photo scan → candidates → add; manual search; other pressings; duplicate double-confirm) passes unchanged inside the new tabbed page.
- **SC-005**: Tapping Sync while a sync is already running is refused with a clear message 100% of the time, and never starts a second concurrent sync.
- **SC-006**: With a sync running, a photo scan on the Scan tab still completes successfully, and the page indicates a sync is in progress.
- **SC-007**: The 027 container and compose service run the new server without any change to how they are invoked, and the whole existing test suite plus the new feature's tests pass with no live API calls.

## Assumptions

- **Trust model unchanged and explicitly extended**: plain HTTP, no page auth, trusted home LAN only — 022's recorded v1 risk, now explicitly extended by owner decision (2026-07-12) to cover folder-move execution from the web page. TLS/auth remain out of scope (022 T041 stance).
- **Single user**: one shared conversation session per server process is acceptable; multi-user/session isolation is deferred to the future AWS/multi-tenancy track.
- **No streaming**: a chat turn is one request/response with a busy indicator; token streaming is a possible future refinement, not v1.
- **Chat history is process-lived**: no persistence of the web conversation across server restarts (terminal parity). The scan session journal remains the only durable journal; no new journal is introduced for chat.
- **Collection browsing stays on Discogs**: the v1 Collection view is status + sync + a link to the owner's Discogs collection page; no in-page record table.
- **Full re-sync stays in the terminal**: the page exposes only the standard sync (clarified 2026-07-12); `--full` remains a terminal-only recovery action.
- **Component scope**: `collection-agent` only. The demo-stack `frontend/`, `agent/`, and `etl/` components are untouched. Eval pipeline and vision prompt untouched. Target zero new dependencies.
- **Existing machinery is reused, not rebuilt**: the journaled resumable sync, the snapshot store, the agent tool loop, the scan pipeline, and the rate-limit governor are consumed as-is; this feature adds a web surface over them. Sole exception (addendum 4): the snapshot store and `run_sync` gain the live-write marker + write lock (FR-017), because concurrent writes during a sync — newly a supported flow — exposed a lost update in the shared core.
- **Rate-budget sharing accepted**: sync and scan/chat may compete for the Discogs per-token rate budget; v1 accepts slower responses during a sync with a visible hint rather than mutual exclusion.
