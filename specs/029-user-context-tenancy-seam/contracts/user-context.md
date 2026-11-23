# Contract: User context and context registry (029)

A NEW contract. It governs the in-process seam through which all per-user
state of the collection agent's serving runtime is reached. It is an internal
(Python-level) contract: this feature publishes no new command, endpoint or
file format. Later features (identity, per-user Discogs authorization, usage
metering) build on these guarantees and may amend this document.

Scope: the `serve`/`scan` runtime. The one-shot terminal commands (`chat`,
`sync`, `status`, `eval-dataset`, `eval-run`) are outside this contract and
unchanged.

## §1 User ids

- Grammar: `^[a-z0-9][a-z0-9-]{0,63}$`.
- `local` is reserved for the implicit local user and is never accepted as an
  argument.
- An id is validated before any filesystem or network effect. A rejected id
  raises `InvalidUserId` and leaves no trace on disk.
- A user's directory is `<users_root>/<user_id>`. After composition, the
  resolved directory MUST be strictly inside the resolved users root;
  otherwise `InvalidUserId`.

## §2 Context registry

| Operation | Contract |
|---|---|
| `local()` | Returns the implicit local user's context. The same object on every call. |
| `get(user_id)` | Validates the id (§1), resolves the user's profile through the user directory, and returns that user's context — the same object on every call for as long as it lives. Concurrent first calls build exactly one context. Raises `InvalidUserId` or `UnknownUser`. |
| `dispose(user_id)` | Removes the context and releases its resources. Other contexts are unaffected. A later `get` builds a fresh context with empty in-memory state. |
| `close()` | Disposes every context. |
| `budget` | The single process-wide rate budget (amendment-017-discogs-consumption-5 §4). |

- With no user directory configured — the only configuration this feature
  ships outside tests — every `get` raises `UnknownUser`.
- The registry defines no expiry, eviction or capacity limit.
- The registry is the only way to obtain a user context.

## §3 User context

A context exposes, for exactly one user:

| Member | Contract |
|---|---|
| `user_id`, `is_local` | Identity of the context. |
| `settings` | The user's effective settings (§4). |
| `store` | The snapshot store on the user's snapshot path. |
| `llm` | The user's LLM access handle. Every LLM call made for this user — chat turns and photo evidence extraction — goes through it. By default it is the process's LLM client, unchanged. |
| `new_discogs_client(notify=None)` | A Discogs client carrying this user's credential and the shared rate budget. The only sanctioned way to build a client for a user. |
| `activate()` | §5. |
| `web_app()` | Activates, then returns this user's web app: built once by the unchanged `create_web_app`, from this context's own scan session, chat, sync runner, store, client and `llm`. The same app object on every call. |
| `close()` | Releases the context's long-lived Discogs client. Does not wait for a running sync. |

Lifetime of in-memory state: the candidate allowlist, session adds, open scan
cycles, supersede state, chat transcript, pending write plan and sync status
live exactly as long as the context. Disposal or process exit ends them; the
on-disk snapshot, sync journal and scan journals remain.

## §4 Effective settings

A context's `settings` is the deployment settings with the per-user fields
overridden. The per-user fields are exactly:

| Field | Implicit local user | Any other user |
|---|---|---|
| `discogs_user_token` | deployment value | `None` |
| `discogs_username` | deployment value | `None` |
| `snapshot_path` | deployment value | `<users_root>/<user_id>/snapshot.json` |
| `scan_journal_dir` | deployment value | `<users_root>/<user_id>/scan-sessions` |
| `scan_target_folder_id` | deployment value | the profile's value |
| `scan_retain_photos` | deployment value | `False` |

- The implicit local user's effective settings are the deployment settings
  object itself.
- Effective settings are produced at one composition point. No other code
  overrides a per-user field.
- A non-implicit user's effective settings never contain a Discogs
  credential. Consequently a Discogs client built from them without the
  user's own credential fails at construction (`DiscogsAuthError`) — it can
  never fall back to the deployment's token.
- `users_root` is `COLLECTION_AGENT_USERS_DIR`, default
  `<component>/data/users`.

## §5 Activation

`activate()` performs, for its user, the checks the `serve` command performs
at startup:

1. resolve the Discogs identity and record the username;
2. list the user's collection folders;
3. verify the user's scan target folder is among them.

| Outcome | Contract |
|---|---|
| success | The context becomes active; `username` and `folders` are set. Further calls are no-ops. |
| credential missing or rejected (401) | `DiscogsAuthError`. |
| identity has no username | `UserActivationError` with code `no_username`. |
| target folder not found | `UserActivationError` with code `scan_folder_missing`, carrying the live folder list. |

A failed activation is not remembered: the context stays inactive and the next
call tries again. No web app — and therefore no add — exists for a user until
activation has succeeded.

The `serve` command activates the local context and maps these errors to its
existing messages and configuration exit code, in its existing order.

## §6 On-disk layout

Per non-implicit user, under `<users_root>/<user_id>/`: `snapshot.json` with
its sync journal and live-writes marker, and `scan-sessions/<session>.jsonl`.
Formats are those of 017's snapshot-schema and 022's scan-journal-schema,
unchanged. The directory is created by the user's first write.

The implicit local user's files stay at the deployment settings' paths
(default `collection-agent/data/snapshot.json` and
`collection-agent/data/scan-sessions/`). This feature never moves, copies or
rewrites them.

## §7 Invariants (normative)

1. **Data isolation.** An operation performed through user A's context reads
   and writes only A's snapshot, sync journal, live-writes marker and scan
   journals.
2. **Session isolation.** Candidate allowlists, session adds, open cycles,
   transcripts and pending plans are never shared between contexts.
3. **Occupancy is per user.** Chat busy, scan supersede and
   sync-already-running are decided per context; activity in one context
   never triggers them in another.
4. **Write gates are per user.** An add or a plan confirm/cancel that
   references another user's candidate or plan is refused exactly as an
   unknown candidate or unknown plan is refused today.
5. **Failure isolation.** An error raised for one user's context changes no
   other context and does not end the process.
6. **One rate budget.** Every Discogs client built through any context shares
   the registry's budget.
7. **One credential per client.** A client built through a context carries
   that user's credential and no other.
8. **LLM access through the handle.** No LLM call for a user bypasses
   `ctx.llm`.
9. **No user selector.** No request input of any route of any context's app
   selects a user. Choosing the context is the caller's responsibility and,
   in this feature, the only caller is the `serve` command choosing `local()`.
10. **Local invariance.** The local context's app returns, for the same
    inputs, the responses the directly composed `create_web_app` returns.

## §8 Guards

Automated, in the component's test suite:

- the two-user isolation suite (invariants 1–5, 8);
- the shared-budget concurrency tests (invariant 6);
- the entry-point guard: the CLI references `local()` only (invariant 9);
- the no-user-selector guard over the composed app's routes (invariant 9);
- the per-user-field guard: the set of source files reading a per-user
  settings field is pinned (§4);
- the client-construction guard: one construction site inside the tenancy
  package, always with budget and credential (invariants 6–7);
- the users-root guard: the default resolves under the component's `data/`
  directory;
- the byte-equality regression (invariant 10).
