# Amendment 3 (024) to Contract: Discogs API Consumption (017)

Prior amendments: 022 (+`/database/search` read, +add-to-collection write),
023 (+`images[]` fields, +image binary GET). 024 adds **read-field and
request-shape deltas only**; §3's never-called-mutations list remains fully
in force.

## Delta 1 — §2 `/database/search`: field consumed + catno-rung page depth

| Change | Detail |
|---|---|
| New field consumed | per result: `master_id` — carried **verbatim** into the candidate payload (absent/`0` stays absent; never constructed). Used for eval same-master classification and available to the scan page. |
| Request shape | the **catno rung only** now sends `per_page = max(COLLECTION_AGENT_SCAN_CATNO_SEARCH_DEPTH (default 50), COLLECTION_AGENT_SCAN_CANDIDATES_MAX)`. Still page 1 only, still ONE request per rung — the rate budget per scan cycle is unchanged in request count. All other rungs keep `per_page = COLLECTION_AGENT_SCAN_CANDIDATES_MAX`. |

Rationale (measured, 2026-07-07 spot-check): Discogs catno search
substring-matches, so exact matches for short catalog numbers can rank
below the old `per_page=8` horizon (`SUB 15` behind `SUB 150/152`). The
deeper page is fetched solely so the client-side exact-catno re-rank
(amendment-022-scan-api) can surface them.

## Delta 2 — §2 `GET /releases/{id}`: field consumed

| Field | Use |
|---|---|
| `master_id` | recorded in the eval dataset manifest as truth ground truth (023's builder already fetches the payload — zero additional requests). Also fetched by the new owner-run `eval-dataset --backfill-masters` mode: one governed `get_release` per already-done manifest release lacking a master id (metadata only, no image downloads). |

## Delta 3 — §4 Rate-limit & failure policy: applies unchanged

Backfill traffic rides the same governed `_request` path as sync/build.
