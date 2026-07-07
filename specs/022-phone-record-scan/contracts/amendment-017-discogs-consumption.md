# Amendment (022) to Contract: Discogs API Consumption (017)

017's `contracts/discogs-consumption.md` declares that any endpoint not
listed there is not consumed, and that adding one is a contract change
recorded in the same change set. Feature 022 (phone record scan) adds
one read endpoint and one write endpoint. The 017 file itself is left
untouched (repo convention: amendments live in the amending feature's
`contracts/`, cf. 018/019/020's `amendment-017-agent-tools.md`).

## Delta 1 — §2 Read endpoints: add database search

| Endpoint | When | Fields consumed |
|---|---|---|
| `GET /database/search?type=release&…` | scan cycles and manual searches (022): parameter rungs in precision order — `barcode=`; `catno=` (+`label=`); `artist=` + `release_title=`; free-text `q=` for manual search AND, per replay addendum 1 (FR-020), as the final photo-cycle fallback composed from partial evidence when every structured rung is absent or empty. `per_page` = `COLLECTION_AGENT_SCAN_CANDIDATES_MAX` (default 8), page 1 only | `pagination.items`; per result: `id`, `title`, `year`, `country`, `format[]`, `label[]`, `catno`, `thumb`, `cover_image`, `uri` |

Handling rules (unchanged in spirit from §5): all consumed fields are
displayed **verbatim** — `thumb`/`cover_image`/`uri` are never
rewritten or constructed; absent fields are shown as absent, never
backfilled from vision evidence (019 discipline).

## Delta 2 — §3 Write endpoints: add add-to-collection

| Endpoint | Purpose | Guard |
|---|---|---|
| `POST /users/{u}/collection/folders/{folder_id}/releases/{release_id}` | add a confirmed release to the collection (022 scan flow); `folder_id` = `COLLECTION_AGENT_SCAN_FOLDER_ID` (default 1, Uncategorized), validated live against `GET /users/{u}/collection/folders` at scan-server startup | executes only in direct response to an explicit owner confirmation tap on a server-served candidate (session allowlist); duplicate-marked releases require a second explicit confirmation, enforced server-side. The vision/LLM step has no path to this endpoint. Response field consumed: `instance_id`. After success, the local snapshot is marked stale. |

§3's closing list of never-called mutations remains in force otherwise
(no rating writes, wantlist writes, marketplace endpoints, folder
delete, instance delete, profile edits — and 022 adds none of them).

## Delta 3 — §4 Rate-limit & failure policy: applies unchanged

Both new endpoints go through the same client `_request` path: the
shared header-driven governor, 429 backoff, 401 abort, 5xx retry
policy all apply. One scan cycle costs at most 3 search requests (the
full ladder) + 1 add; the 60 req/min budget therefore supports the
target batch cadence with headroom.
