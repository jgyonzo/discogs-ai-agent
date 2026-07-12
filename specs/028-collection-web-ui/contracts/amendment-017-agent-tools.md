# Amendment: 017 agent-tools contract — deltas 12–14 (028-collection-web-ui)

Amends `specs/017-discogs-collection-agent/contracts/agent-tools.md`.
Fourth amendment to that contract; continues the delta numbering after
018's deltas 1–5, 019's 6–8, and 020's 9–11.

## Delta 12 — §4 write gate: a second sanctioned runtime gate (HTTP confirm)

§4's invariant is UNCHANGED: `execute_plan` is not a ToolDef; the LLM can
only `propose_moves`, which parks a `WritePlan` on the session; an
unconfirmed write is unreachable by construction.

What changes: the set of sanctioned RUNTIME gates grows from one to two.

1. **Terminal gate (017, unchanged)** — the CLI renders the plan and
   prompts y/N; only an interactive "y" executes.
2. **Web gate (028, new)** — the web server holds the plan and returns a
   display-only view (`plan_id`, target folder, move displays); only an
   explicit `POST /api/chat/plan/confirm` whose `plan_id` matches the
   CURRENT `PROPOSED` plan executes, via the same `execute_plan` with the
   same per-move live re-validation and per-item results. The request
   carries no move data. A new user turn, an explicit cancel, supersession
   by a newer plan, or a server restart all make the plan unexecutable
   (409, nothing written). See
   `specs/028-collection-web-ui/contracts/web-ui-api.md` §2.

Both gates drive the same `PlanState` transitions
(PROPOSED→CONFIRMED→EXECUTED / →CANCELLED / →EXPIRED).

## Delta 13 — §1/§2 runtime-conditional `start_sync` + runtime-neutral confirmation wording

- **`start_sync` (web runtime variant)**: in the web server, the
  registered `start_sync` ToolDef (same name, same args schema) delegates
  to the server's single-occupancy background SyncRunner instead of
  running the sync inline: it returns `{started: true, detail: ...}` or
  `{already_running: true, detail: ...}` immediately, and `full=true` is
  ignored with an honest note (web sync is standard-only —
  028 clarification 2026-07-12). The terminal runtime keeps 017's inline
  behavior verbatim. `snapshot_status` is identical in both runtimes
  (shared `snapshot_status_payload`).
- **Runtime-neutral wording**: `propose_moves`' payload `detail` no longer
  says "the terminal will ask… confirm there"; it now says the app will
  ask the user to confirm, without naming a runtime, and still forbids the
  LLM from claiming the move already happened. `prompts/system.md`'s
  procedural prose about write confirmation is neutralized the same way.
  Payload FIELDS are unchanged — this is a wording delta only.

## Delta 14 — §6 CLI surface: `serve` subcommand, `scan` alias

The CLI gains a `serve` subcommand — "serve the collection web page
(scan + chat + collection status/sync) on the LAN" — with the same
`--host`/`--port` options and startup sequence as `scan` (token/identity
validation, live folder check, OPENAI_API_KEY gate), extended to build
the web chat agent and the SyncRunner. `scan` remains a fully working
alias with identical behavior (the 027 container `CMD ["scan"]` is
unaffected). Exit codes unchanged (0/1/2/3).
