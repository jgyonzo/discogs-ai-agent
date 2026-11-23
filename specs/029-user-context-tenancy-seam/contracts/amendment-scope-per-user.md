# Amendment: scope of process-wide singletons becomes "per user context" (029-user-context-tenancy-seam)

One wording amendment applied to four contracts. **No endpoint, payload,
status code, error code, file format or schema changes.** In every place
these contracts say "the process", "the server run" or "the session" to scope
a piece of state, the scope is now **one user context**
(`contracts/user-context.md`). The `serve` command serves exactly one context
— the implicit local user — so everything observable through it is unchanged.

## 028 `web-ui-api.md` — delta 1 (FIRST amendment to this contract)

| Section | Previous scope | Amended scope |
|---|---|---|
| §2 Chat — "One shared conversation per server process", `409 chat_busy` | process | One conversation per user context. `chat_busy` reflects only that context's in-flight turn. |
| §2 `GET /api/chat/history` — "The transcript is process-lived" | process | Lives as long as the user context; a restart or disposal starts it empty. |
| §2 Plan confirm / cancel — `no_pending_plan`, `plan_mismatch` | process | Evaluated against that context's pending plan only. Another context's plan id is an unknown id. |
| §3 `POST /api/sync` — `409 sync_already_running`, "single occupancy"; "Occupancy is therefore global across button and chat" | process | One running sync per user context, shared by that context's button and chat. Syncs of different contexts may run concurrently and share the rate budget. |
| §3 `GET /api/collection/status` | the snapshot | That context's snapshot and sync status; `collection_url` is built from that context's username. |
| §4 Interplay invariants (freshness, live-write during sync) | process | Hold within one user context. A live write in one context never affects another context's snapshot or sync outcome. |

## 022 `scan-api.md` — delta 5 (after 024, 025, 026, 028)

| Section | Previous scope | Amended scope |
|---|---|---|
| "this session", `session_id` (`GET /api/health`, `GET /api/session`) | server run | One scan session per user context, created when that context's app is built. |
| Candidate allowlist, `403 unknown_candidate`, `403 unknown_master` | session | That context's session. A release or master served to another context is unknown. |
| Supersede (FR-022/023), `409 superseded`, auto-closed cycles | server | That context only. A scan in one context never supersedes or closes cycles in another. |
| Duplicate overlay (`added_this_session`, snapshot counts) | session + the snapshot | That context's session and snapshot. |
| Add target folder | `COLLECTION_AGENT_SCAN_FOLDER_ID`, validated at startup | The context's effective `scan_target_folder_id`, validated at that context's activation. For the implicit local user this is the same setting, validated at startup as before. |
| Photo retention | flag-gated | Flag-gated **and** implicit local user only. |

## 022 `scan-journal-schema.md` — delta 1 (FIRST amendment)

Line schema unchanged. Location: `<scan_journal_dir>/<session>.jsonl`, where
`scan_journal_dir` is the context's effective value — for the implicit local
user, the existing `COLLECTION_AGENT_SCAN_JOURNAL_DIR`; for any other user,
`<users_root>/<user_id>/scan-sessions`.

## 017 `snapshot-schema.md` — delta 2 (after 028's delta 1)

Snapshot schema, sync journal and live-writes marker unchanged. Location:
the context's effective `snapshot_path` — for the implicit local user, the
existing `SNAPSHOT_PATH`; for any other user,
`<users_root>/<user_id>/snapshot.json`, with the journal and marker derived
from it as before. The per-path write lock of delta 1 is unchanged and, with
one path per user, is therefore per user.
