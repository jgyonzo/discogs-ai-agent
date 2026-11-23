# Research: User-context tenancy seam (029)

Phase 0 of the plan. Each entry records a decision, why, and what was
rejected. Findings marked **verified** were checked against the code and the
test suite on 2026-11-23 (commit `e62225d`, 639 tests).

## R1 — Per-user scan and web state: one app instance per user context

**Decision.** Each user context owns its own web app instance, built by the
existing, unchanged `web.server.create_web_app(...)` from that user's
collaborators. Nothing is extracted from the scan server's closure.

**Why.** All per-run scan state — open cycles, the supersede generation
counter, the state lock, the photo retainer — already lives inside the closure
of `scan.server.create_app`, so it is already scoped to one app instance.
`WebChat`, `SyncRunner` and `ScanSession` are plain objects passed in. Building
one app per user therefore gives per-user chat busy-locks, per-user supersede
and per-user sync occupancy *by construction*, with a zero-line diff in
`scan/server.py` and `web/*.py`. The 022/026/028 HTTP contracts stay verbatim
because the code that implements them is untouched.

**Consequences for later features.**

- D3 (identity) adds an authenticating ASGI dispatcher: resolve the session to
  a user id, fetch the context, forward the request to `ctx.web_app()`.
- D2 (sectioned API) registers its new `/api/<section>/v1` routers in the same
  per-context app factory, so they inherit the scoping.
- About ten small FastAPI apps in memory is negligible.

**Rejected: extract a per-user "scan engine" and resolve it per request.**
It is the shape a single shared app would need, but in this feature there is
exactly one resolver (the implicit user), so the abstraction would be
speculative; it rewrites 500 lines of live-validated handlers for no observable
gain; and D2 replaces the legacy routes anyway. It remains available later if
one shared app ever becomes necessary — nothing here blocks it.

## R2 — Per-user values travel as an *effective settings view*

**Decision.** `Settings` keeps every field. A user context carries an
**effective settings** object: the deployment settings with the per-user
fields overridden for that user (`Settings.model_copy(update=…)`), produced at
exactly one composition point. The implicit local user's effective settings
*are* the deployment settings object, unmodified.

The per-user fields are declared once, as `PER_USER_FIELDS`:

| Field | Non-implicit user's value |
|---|---|
| `discogs_user_token` | `None` — never the owner's token |
| `discogs_username` | `None` — identity comes from `/oauth/identity` |
| `snapshot_path` | `<users_root>/<user_id>/snapshot.json` |
| `scan_journal_dir` | `<users_root>/<user_id>/scan-sessions` |
| `scan_target_folder_id` | from the user's profile |
| `scan_retain_photos` | `False` — retention is an owner diagnostic |

**Why.** Splitting `Settings` into two classes is ruled out by FR-007:
`tests/conftest.py` builds `Settings(DISCOGS_USER_TOKEN=…, SNAPSHOT_PATH=…,
COLLECTION_AGENT_SCAN_JOURNAL_DIR=…)` and dozens of tests read those attributes
(**verified**). Every factory in the component already takes `settings` as its
injection vehicle, so a per-user view reaches every existing read site —
`scan/server.py` (target folder, retention), `snapshot/sync.py` (username
fallback), the default client factories — with no edits.

**Fail-closed property.** A non-implicit view contains no token and no
username. Any code path that builds a Discogs client from the view without the
user's credential fails loudly (R4) instead of silently acting as the owner.
Without the view, a friend's sync would also emit the owner's
`DISCOGS_USERNAME` mismatch warning from `sync.py` — the view removes that too.

**Rejected: additive parameters on each call site** (`create_app(…,
target_folder_id=…)`, `run_sync(…, expected_username=…)`). More diff, and it
leaves the token and username in the settings object handed to a friend's
context.

## R3 — The Discogs token becomes optional in `Settings`, required by the CLI

**Decision.** `Settings.discogs_user_token` becomes `SecretStr | None`
(default `None`), so deployment settings load without a credential (FR-021).
`cli.main()` checks it right after `load_settings()` and returns `EXIT_CONFIG`
with today's message when it is absent.

**Why it is safe.** No test asserts a `ValidationError` for a missing token
(**verified**: the only `ValidationError` assertions are on request and scan
models). Today the failure comes from pydantic and is rendered by `main()` as
`configuration error: missing/invalid env: <names>. Set them in the repo-root
.env (see collection-agent/README.md).`, where `<names>` is whatever pydantic
reports for the missing field. The explicit gate reproduces that line; its
exact text is taken from the characterization test below, not assumed.

**Discipline.** A characterization test capturing today's exact output and exit
code for a token-less run of every subcommand is written and committed *before*
the field is changed, then must pass unmodified after.

## R4 — Discogs credential strategy is `httpx.Auth`; the secret stays in `client.py`

**Decision.** `DiscogsClient.__init__` gains an optional `auth: httpx.Auth |
None`. When given, it is the client's credential. When `None`, the client
builds the personal-token credential from `settings.discogs_user_token`, in
`discogs/client.py`, as today. With neither, construction raises
`DiscogsAuthError`.

**Why `httpx.Auth`.** It is the transport library's own extension point, it
runs per request (which the OAuth 1.0a signer of D5 needs for its nonce and
timestamp), and it adds no abstraction of ours. D5 ships one subclass; no call
site changes (FR-018).

**Why the unwrap stays put.** `test_secrets_hygiene.py` asserts exactly three
`get_secret_value()` sites, all in files named `client.py` or `cli.py`
(**verified**). Keeping the personal-token unwrap in `discogs/client.py` keeps
that audit passing unmodified, so FR-007 needs no exception at all.

**Wire equivalence.** The `Authorization: Discogs token=…` header moves from
the client's default headers to the auth flow; the request on the wire is the
same. A test compares the headers of a request built before and after.

## R5 — One shared rate budget, per-client governors

**Decision.** The mutable pacing state (`limit`, `remaining`, consecutive
429s, an active-backoff deadline, a lock) moves into a small `RateBudget`
object. `RateLimitGovernor` keeps its constructor and methods and gains an
optional `budget`; without one it creates a private budget, exactly as today.
`DiscogsClient` gains an optional `budget` that it hands to the governor it
creates. The context registry owns one `RateBudget` and gives it to every
client built for any user.

**Why split state from governor.** The governor also holds the *notify*
callback, which is per caller: today the serving client prints pacing notices
to the console and the background sync's client reports to nobody. One shared
governor would redirect those notices and change local console output. Sharing
only the budget keeps each client's notices where they go today, while the
numbers they act on are common.

**Concurrency rules.**

- State is read and written under the budget's lock. Sleeping happens outside
  the lock.
- A 429 sets a shared backoff deadline before sleeping. Other threads calling
  `before_request` during that window wait for the remainder. The thread that
  set the deadline clears it when its sleep returns. With an injected no-op
  sleep (every existing test), the deadline is cleared immediately, so
  single-thread sleep sequences are identical to today's — the two existing
  governor tests in `test_sync.py` pass unmodified.

**Rejected: optimistic reservation** (decrement `remaining` on each send).
It would tighten the burst bound, but the image CDN returns no rate-limit
headers, so reservations made for image downloads would never be corrected and
`eval-dataset` would pace spuriously. The accepted bound: after a pacing delay,
at most one request per concurrently waiting thread is released before the
next header update; a resulting 429 is absorbed by the shared backoff, which is
its designed role.

## R6 — Scope: the serving runtime goes through the context; one-shot commands do not

**Decision.** `serve`/`scan` is composed through the registry and the local
context. `chat` (terminal), `sync`, `status`, `eval-dataset` and `eval-run`
keep their current composition, untouched.

**Why.** The serving runtime is the only one that is multi-threaded and the
only one that will ever serve another user. The one-shot commands are
single-threaded, local-only owner tools; they already act for the implicit
local user by construction, because they read the same `.env`. Routing them
through the registry would add plumbing through lazily imported, test-patched
call sites for no behavior. The spec's FR-005 and FR-015 are refined to say
this (see spec, Clarifications).

## R7 — User ids, per-user layout, and the one new setting

**Decision.**

- Grammar: `^[a-z0-9][a-z0-9-]{0,63}$`. Lowercase only, so two ids can never
  collide on a case-insensitive filesystem (the owner's macOS). Accepts UUIDs,
  which D3 is free to use.
- Reserved: `local` (the implicit user's id). It is never accepted by
  `registry.get`.
- Layout: `<users_root>/<user_id>/snapshot.json` (plus its sync journal and
  live-writes marker, derived by `SnapshotStore` as today) and
  `<users_root>/<user_id>/scan-sessions/`.
- Defense in depth: after composing a user directory, verify the resolved path
  is strictly inside the resolved users root before any use.
- New setting: `COLLECTION_AGENT_USERS_DIR`, default
  `<component>/data/users`. Under `data/`, so it is gitignored, excluded from
  the image build context, and inside the 027 bind mount with no packaging
  change. A guard pins the default under `data/` (023 precedent).

Directories are created on first write, not at context creation, so a rejected
or never-used id leaves nothing on disk.

## R8 — Activation: the startup gates, per user

**Decision.** Building a context does no network I/O. `ctx.activate()`
performs what `_cmd_serve` does at startup today: resolve the identity
(username), list the folders, and check that the scan target folder exists. It
raises typed errors (`DiscogsAuthError`, `UserActivationError` with a code:
`no_username`, `scan_folder_missing`). `ctx.web_app()` activates first, so an
app — and therefore an add — can never exist for a user whose folder is
invalid (FR-014). A failed activation is not cached; the next call retries.

`_cmd_serve` calls the same activation for the local context and maps each
error to today's console message and `EXIT_CONFIG`, in today's order: OpenAI
key → Discogs identity → username → folder. The LLM client is built lazily by
the registry on first `web_app()`, so the optional tracing notice still prints
after the Discogs checks, as today.

## R9 — LLM access handle

**Decision.** The registry takes an optional `llm_handle_factory(user_id,
client) -> client`. A context's `llm` is the factory's result; the default
factory returns the same object (`is`-identical), so nothing changes on the
wire or in tracing. Both consumers — the web agent and the scan vision call —
receive `ctx.llm`. D6 supplies a metering factory; no call site changes.

## R10 — Registry lifecycle

**Decision.** One lock guards the id → context map; creation happens under
it, so concurrent first use yields one context. `dispose(user_id)` removes the
entry and closes the context's long-lived Discogs client. It does not join a
running sync: the thread is a daemon with its own client that it closes itself
(028 R5), and its journal makes the work resumable. No expiry, no eviction, no
size cap — ten users.

Unknown users: the registry resolves non-implicit ids through an injected
**user directory** (`profile(user_id) -> UserProfile | None`). This feature
ships no production directory, so outside tests `registry.get(…)` always raises
`UnknownUser`. That is FR-008 enforced by absence: there is nothing to select.

## R11 — Guards

| Guard | Pins |
|---|---|
| Entry-point guard (AST over `cli.py`) | The CLI reaches contexts only through `registry.local()`; `registry.get` is never referenced outside tests. |
| No-user-selector guard | No route of the composed app declares a path, query, header, cookie or body field naming a user; `tenancy` is not imported by `scan/` or `web/`. |
| Per-user-field guard (AST) | The set of source files that read a `PER_USER_FIELDS` attribute is pinned to today's list plus the composition module; a new read site fails the test. |
| Client-construction guard | Inside `tenancy/`, Discogs clients are built at one site, always with the shared budget and the context's credential. |
| Users-root guard | Default users root resolves under `collection-agent/data/`. |
| Existing guards | Secrets audit, cross-import guard, eval read-only guard, page guards, packaging guards — all must pass unmodified. |

## R12 — Proving "unchanged" (SC-003)

A regression test drives one scripted scan → add → chat → plan-confirm → sync
cycle through (a) an app composed directly with `create_web_app`, as 028's
tests do, and (b) the local context's `web_app()`, with identical fakes and a
fixed clock, and compares status codes and bodies byte for byte. This is the
028 `test_web_scan_regression.py` pattern, one level up.

## R13 — Explicitly left for later

| Left out | Lands in |
|---|---|
| OAuth 1.0a `httpx.Auth` implementation, encrypted credential storage, database-backed user directory | D5 (and D3 for the directory's identity half) |
| Authenticating dispatcher, hosted run mode | D3 |
| Interactive-versus-background scheduling and the sync queue on top of `RateBudget` | D5 |
| Metering LLM handle factory, per-user trace tags | D6 |
| Context expiry, multi-process coordination | Not planned at this scale |
