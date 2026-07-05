# Contract: Discogs API Consumption (017)

Normative list of everything the collection agent reads from and writes to
the live Discogs API. Any endpoint or field not listed here is **not
consumed**; adding one is a contract change (update this file in the same
change set). Endpoint shapes per `docs/discogs_api_reference.md`.

## 1. Authentication & identity

| Aspect | Contract |
|---|---|
| Method | Personal access token — `Authorization: Discogs token=<DISCOGS_USER_TOKEN>` header. Query-string credentials are forbidden (they leak into logs). |
| Identity | `GET /oauth/identity` once per process start → `username`. `DISCOGS_USERNAME` env is an optional override; on mismatch, identity wins and a warning is shown. |
| User-Agent | Every request sends the settings-sourced UA, default `DiscogsCollectionAgent/0.1 +https://github.com/jgyonzo/genai-pathway-final-project-yonzo`. Never a generic/browser UA. |
| Secrets | Token only via `pydantic-settings` from env/`.env` (gitignored). Never logged, echoed, persisted to the snapshot, or committed. |

## 2. Read endpoints (sync)

| Endpoint | When | Fields consumed |
|---|---|---|
| `GET /users/{u}/collection/folders` | each sync | `folders[].id,name,count` |
| `GET /users/{u}/collection/folders/0/releases?per_page=100&page=N` | each sync (instance pass; folder 0 = All) | `pagination.pages,items`; per item: `instance_id`, `folder_id`, `date_added`, `rating`, `basic_information.{id,title,year,artists[].name,labels[].{name,catno},formats[].{name,descriptions}, genres,styles}` |
| `GET /releases/{release_id}` | enrichment pass, once per unique release; results journaled and reused across syncs (unless `--full`) | `country`, `genres`, `styles`, `videos[].{uri,title,duration}`, `community.{have,want,rating.average,rating.count}`, `num_for_sale`, `lowest_price` |
| `GET /users/{u}/collection/value` | each sync | `minimum`, `median`, `maximum` (currency strings, reported verbatim with basis "Discogs estimate") |

## 3. Write endpoints (US4 only — live, confirmation-gated)

| Endpoint | Purpose | Guard |
|---|---|---|
| `POST /users/{u}/collection/folders` (body: `name`) | create target folder | only when the confirmed WritePlan has `create=true`; name-collision checked live first |
| `POST /users/{u}/collection/folders/{folder_id}/releases/{release_id}/instances/{instance_id}` (body: `folder_id=<target>`) | move an instance to the target folder | per-instance live re-validation before the call; executes only after CLI runtime confirmation (see `agent-tools.md` §4) |

No other mutations exist. Explicitly **never called**: rating writes,
wantlist writes, marketplace endpoints, folder delete, instance delete,
profile edits.

## 4. Rate-limit & failure policy

- Every response's `X-Discogs-Ratelimit`, `X-Discogs-Ratelimit-Used`,
  `X-Discogs-Ratelimit-Remaining` headers feed a shared governor; when
  `remaining ≤ RATE_LIMIT_FLOOR` (settings, default 2) the client sleeps
  until the 60 s moving window frees budget.
- `429` ⇒ exponential backoff with jitter (base 2 s, cap 60 s), then resume.
  The user sees a "throttled by Discogs, continuing…" notice, not a failure.
- `401` ⇒ abort with a clear "token invalid/expired" message (no retry).
- `404` on a release during enrichment ⇒ record kept with enrichment nulls +
  warning in `meta.sync_stats.warnings` (never fabricated data).
- 5xx ⇒ up to 3 retries with backoff, then the item is journaled as failed
  and the sync continues; sync ends `partial` if any item failed.
- Network loss / Ctrl-C mid-sync ⇒ journal preserved; next `sync` resumes.

## 5. Data-handling rules

- Image/video URIs are used **verbatim** (signed URLs; never rewritten).
- The snapshot stores no credentials and no other users' personal data
  (contributor/submitter usernames from release pages are not persisted).
- All timestamps stored in ISO-8601 UTC.
