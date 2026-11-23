# Data Model: User-context tenancy seam (029)

No persisted schema changes. This feature adds in-memory composition objects
and a per-user directory layout that reuses the existing file formats.

## Entities

### UserId

An opaque string identifying one user of the process.

| Rule | Value |
|---|---|
| Grammar | `^[a-z0-9][a-z0-9-]{0,63}$` |
| Reserved | `local` — the implicit local user; never accepted by `get` |
| Validation | Before any filesystem or network effect; failure raises `InvalidUserId` |

### UserProfile

What the user directory knows about a non-implicit user. Supplied by tests in
this feature; by the database in later features.

| Field | Type | Notes |
|---|---|---|
| `user_id` | UserId | |
| `discogs_auth` | `httpx.Auth` | The user's Discogs credential strategy. Never a settings field. |
| `scan_target_folder_id` | int | Validated live at activation. |

### UserContext

One user's slice of the running process.

| Member | Kind | Notes |
|---|---|---|
| `user_id` | UserId | `local` for the implicit user |
| `is_local` | bool | |
| `settings` | effective `Settings` | Deployment settings with `PER_USER_FIELDS` overridden (research R2). For the local user: the deployment object itself. |
| `store` | `SnapshotStore` | On `settings.snapshot_path` |
| `budget` | `RateBudget` | The registry's single shared instance |
| `llm` | LLM client handle | `llm_handle_factory(user_id, client)`; default returns the client unchanged |
| `username` | str | Set by activation |
| `folders` | `dict[int, str]` | Set by activation |
| `new_discogs_client(notify=None)` | factory | Credential = the user's; budget = shared. The only way a client is built for a user. |
| `activate()` | operation | Identity + scan-folder check. Idempotent once successful; a failure is not cached. |
| `web_app()` | operation | Activates, then builds — once — `ScanSession`, `SyncRunner`, the web agent, `WebChat` and the app via the unchanged `create_web_app`. Returns the same app thereafter. |
| `scan_session`, `web_chat`, `sync_runner` | objects | Exist after `web_app()`; exposed for tests and for the local CLI banner |
| `close()` | operation | Closes the long-lived Discogs client. |

**State machine**

```text
 created ──activate() succeeds──▶ active ──close() / dispose──▶ disposed
    │
    └──activate() raises──▶ created   (not cached; the next call retries)
```

`web_app()` is only reachable in `active`. In-memory session state (allowlist,
open cycles, transcript, pending plan, sync status) lives exactly as long as
the context.

### ContextRegistry

| Member | Notes |
|---|---|
| `local()` | The implicit local user's context. Built once. |
| `get(user_id)` | Validates the id, resolves the profile through the user directory, builds or returns the context. Raises `InvalidUserId` or `UnknownUser`. |
| `dispose(user_id)` | Removes and closes one context. No effect on others. |
| `close()` | Disposes every context. |
| `budget` | The process-wide `RateBudget`. |

Constructor collaborators, all injectable: deployment settings, an LLM client
factory (called lazily, once), a user directory (default: none — every `get`
raises `UnknownUser`), an LLM handle factory (default: identity), and the
Discogs-client and sync-function factories tests already inject today.

### RateBudget

The process-wide view of Discogs's per-IP allowance.

| Field | Notes |
|---|---|
| `limit`, `remaining` | Last values reported by any response, any user |
| `consecutive_429` | Drives the exponential backoff, reset by any header-bearing response as today |
| `blocked_until` | Shared backoff deadline; set by the thread that received the 429, cleared by that thread when its sleep returns |
| lock | Guards all of the above; never held while sleeping |

A `RateLimitGovernor` without an explicit budget owns a private one — today's
behavior, unchanged.

## Effective settings by user kind

| `Settings` field | Implicit local user | Any other user |
|---|---|---|
| `discogs_user_token` | from `.env` | `None` |
| `discogs_username` | from `.env` (optional) | `None` |
| `snapshot_path` | `data/snapshot.json` (or `SNAPSHOT_PATH`) | `<users_root>/<id>/snapshot.json` |
| `scan_journal_dir` | `data/scan-sessions` (or env) | `<users_root>/<id>/scan-sessions` |
| `scan_target_folder_id` | from `.env` (default 1) | from the profile |
| `scan_retain_photos` | from `.env` | `False` |
| every other field | deployment value | deployment value |

## On-disk layout

```text
collection-agent/data/
├── snapshot.json                  # implicit local user — unchanged
├── snapshot.json.sync.tmp.json
├── snapshot.json.live-writes
├── scan-sessions/<session>.jsonl  # implicit local user — unchanged
├── eval/…                         # owner tooling — unchanged, never per-user
└── users/                         # NEW root (COLLECTION_AGENT_USERS_DIR)
    └── <user_id>/
        ├── snapshot.json          # same schema (017 snapshot-schema)
        ├── snapshot.json.sync.tmp.json
        ├── snapshot.json.live-writes
        └── scan-sessions/<session>.jsonl   # same schema (022 journal schema)
```

A user directory is created by the first write for that user, never earlier.

## Errors

| Error | Raised when | Local CLI mapping |
|---|---|---|
| `InvalidUserId` | Id fails the grammar, is reserved, or resolves outside the users root | not reachable |
| `UnknownUser` | The user directory has no profile for the id | not reachable |
| `DiscogsAuthError` | No credential available, or Discogs returns 401 | today's message, exit 2 |
| `UserActivationError(no_username)` | Identity returns no username | today's message, exit 2 |
| `UserActivationError(scan_folder_missing)` | Target folder absent from the live folder list; carries the list | today's message, exit 2 |

Every error belongs to one user's context and never changes another context
or ends the process outside the local CLI's own startup.
