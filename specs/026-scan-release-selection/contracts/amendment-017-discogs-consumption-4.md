# Amendment 4 (026) to Contract: Discogs API Consumption (017)

Prior amendments: 022 (+`/database/search` read, +add-to-collection write),
023 (+`images[]` fields, +image binary GET), 024 (+search `master_id`
field, +catno per_page depth, +backfill `get_release` use). 026 adds **one
new read endpoint**; §3's never-called-mutations list remains fully in
force — this amendment introduces ZERO new writes.

## Delta 1 — NEW read: `GET /masters/{master_id}/versions`

| Aspect | Contract |
|---|---|
| Caller | `DiscogsClient.get_master_versions(master_id, per_page)` — the scan server's `/api/master-versions` endpoint ONLY. Never called during scan identification, manual search, sync, eval runs, or replay. |
| When | Exclusively on an explicit owner tap of the "show other pressings" action on the scan page (spec FR-010). Never automatic — a scan/search cycle that the owner does not expand issues zero calls to this endpoint (spec SC-006). |
| Request shape | `page=1` and `per_page = COLLECTION_AGENT_SCAN_VERSIONS_MAX` (default 25). Exactly ONE request per tap; no pagination walking, no filter/sort params. |
| `master_id` provenance | Only a `master_id` the server itself received verbatim from a prior `/database/search` result in the SAME open scan cycle (024's consumed field) may be requested — client-supplied ids outside that set are rejected before any request is issued. |
| Fields consumed | per `versions[]` item: `id`, `title`, `released`, `country`, `format`, `label`, `catno`, `thumb` — each carried **verbatim** into the candidate payload (the only transformations: `str()` on `released`, list-wrapping of the single `format`/`label` strings). `pagination.items` consumed verbatim as the honest total-version count. All other item fields (`status`, `major_formats[]`, `stats`, `resource_url`) are ignored. |
| Failure policy | rides the same governed `_request` path (rate-limit headers honored, same retry/typed-error behavior). A failed fetch surfaces as a typed scan-page error and never aborts or mutates the scan cycle. |

## Delta 2 — §4 Rate-limit policy: applies unchanged

Versions traffic is governed identically to search/sync traffic. Worst-case
budget impact: +1 request per explicit owner tap.
