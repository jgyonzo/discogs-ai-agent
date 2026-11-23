# Amendment: 017 discogs-consumption contract — delta 5 (029-user-context-tenancy-seam)

Amends `specs/017-discogs-collection-agent/contracts/discogs-consumption.md`
§1 and §4. FIFTH amendment to this contract (after 022, 023, 024, 026).
**Zero new endpoints, zero new reads, zero new writes.** Every request the
component sends today is sent unchanged.

## §1 Authentication & identity — amended rows

| Aspect | Contract (amended) |
|---|---|
| Method | The `Authorization` header of every request is produced by the client's **credential strategy** (an `httpx.Auth`). One strategy ships: the personal access token, producing `Authorization: Discogs token=<DISCOGS_USER_TOKEN>` exactly as before. Query-string credentials remain forbidden. A client with no credential fails at construction with `DiscogsAuthError`; it never sends an unauthenticated request. |
| Identity | `GET /oauth/identity` → `username`, **once per user context activation** (for the one-shot terminal commands: once per process start, as before). `DISCOGS_USERNAME` remains an optional override for the implicit local user only; it is never applied to another user. |
| Secrets | `DISCOGS_USER_TOKEN` is the implicit local user's credential and is optional at configuration load; every command still requires it and exits with the configuration code when it is absent. A credential is never logged, echoed, traced, persisted, or placed in another user's effective settings. |

Unchanged: the User-Agent row.

Adding a credential strategy (for example the OAuth 1.0a signer planned for
per-user authorization) requires no change to any request-issuing code and
will be recorded as its own amendment.

## §4 Rate-limit policy — additions

The header-driven pacing and 429 backoff rules are unchanged. What changes is
where their state lives:

- **Rate budget.** The last reported limit and remaining allowance, the
  consecutive-429 counter and the active backoff deadline form a *rate
  budget*. A governor created without an explicit budget owns a private one
  (previous behavior).
- **Shared budget in the serving runtime.** Every Discogs client built
  through a user context shares one process-wide budget, because Discogs
  throttles per source IP. A header reported on any user's response updates
  the allowance every user is paced against.
- **Shared backoff.** A 429 received by one client makes requests from every
  client on the same budget wait for the remainder of that backoff.
- **Concurrency.** Budget state is consistent under concurrent use. No lock
  is held while sleeping.
- **Notices.** Pacing and throttling notices are still delivered to the
  `notify` callback of the client whose request is waiting.
- **Burst bound.** After a pacing delay, at most one request per concurrently
  waiting thread is released before the next header update. A resulting 429
  is absorbed by the shared backoff.

Not in this amendment: prioritization of interactive over background traffic
and queuing of syncs.
