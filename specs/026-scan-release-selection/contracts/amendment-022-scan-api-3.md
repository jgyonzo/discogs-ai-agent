# Amendment 3 (026) to Contract: Scan HTTP API (022)

Prior amendments: 024 (Candidate +`master_id`, catno exact-match-first
ordering), 025 (barcode plausibility gate appended to FR-019/020
normalization). 026 adds **additive candidate fields, one documented
ordering semantic, and one new read endpoint**. All existing endpoints,
request/response shapes, error codes, the write gate, and the journal
schema are unchanged.

## Delta 1 — `Candidate`: two additive server-built link fields

| Field | Type | Semantics |
|---|---|---|
| `release_page_url` | `string \| null` | The release's Discogs **web page**, built server-side as `{DISCOGS_WEB_BASE_URL}/release/{release_id}`. Always populated on served candidates. |
| `master_page_url` | `string \| null` | The master's Discogs web page, `{DISCOGS_WEB_BASE_URL}/master/{master_id}`. Non-null **iff** `master_id` is non-null. Never fabricated for masterless releases. |

Link-integrity rules (019 discipline, now normative for the scan page):

- These two fields are the ONLY values the page may use for outbound
  Discogs navigation. The page MUST NOT construct a URL from `release_id`,
  `master_id`, `instance_id`, or any other identifier.
- Each URL shape exists in exactly one server-side code site per id space
  (grep-enforced, 020 precedent).
- Outbound links open in a new tab and are presented distinctly from add
  actions: activating a link never adds; activating add never navigates
  (spec FR-009).

## Delta 2 — `candidates[0]` is the selected release (documented semantic)

In every non-empty `candidates` list (from `/api/scan`, `/api/search`, or
`/api/master-versions`' source cycle), **position 0 is the selected
release** — the pipeline's top-ranked match. This documents the ordering
the ladder + 024 exact-catno re-rank already produce; it is NOT a ranking
change and introduces no new field. Clients render position 0 as the
designated match and positions 1..n as alternatives.

## Delta 3 — NEW endpoint: `GET /api/master-versions`

On-demand fetch of a displayed master's other pressings (spec FR-010–013).

**Request** (query params): `scan_id` (string, required), `master_id`
(int, required).

**Gates** (evaluated in order, before any Discogs request):

1. `scan_id` must name a known, still-open cycle → else `409 superseded`.
2. `master_id` must be a `master_id` carried by a candidate REGISTERED in
   that cycle → else `403 unknown_master` (mirror of the add gate's
   `unknown_candidate`: clients select only among server-offered values).
3. The fetch does **not** bump the supersede generation (it extends the
   current cycle); if a newer scan starts while the fetch is in flight,
   the result is discarded with `409 superseded` and no state effects.

**Success — `200 VersionsResponse`**:

```json
{
  "scan_id": "…",
  "master_id": 12345,
  "candidates": [ Candidate, … ],
  "total_versions": 31,
  "message": null
}
```

- `candidates`: versions mapped verbatim per the 026 data-model (§2),
  deduped against the cycle's already-registered release ids (the selected
  release itself is always dropped — it is a "version" of its own master);
  each carries the same `DuplicateStatus` overlay (explicit `unknown`
  degradation included) and both link fields. May be empty; then `message`
  states WHICH empty it is (spec replay addendum 1): versions fetched but
  all already displayed ("already shown above") vs. an empty versions page
  ("no other pressings found") — computed from the fetched page, never
  guessed. Clients surface the outcome at the point of interaction
  (FR-015): the invoking control and primary status reflect it; a
  no-change result never renders as success.
- `total_versions`: verbatim `pagination.items` — clients MUST use it for
  honest truncation display ("showing N of T") and MUST NOT imply the list
  is complete when `total_versions` exceeds what was returned.
- **Write-gate integration**: returned candidates are registered into the
  SAME session allowlist and cycle title map as scan candidates. `/api/add`
  accepts them with unchanged semantics — duplicate confirmation included —
  and journals a standard `added` line with the cycle's original `source`.
  No journal schema change.

**Errors** (022 error envelope): `409 superseded` (gate 1/3),
`403 unknown_master` (gate 2), `502 discogs_unavailable` (Discogs fetch
failed — cycle state untouched, previously served results remain valid),
`500 journal_error` is NOT possible here (the endpoint writes no journal
lines).

## Delta 4 — Settings

NEW: `COLLECTION_AGENT_SCAN_VERSIONS_MAX` (int, default `25`) — per_page
and display cap of the versions fetch. Existing `DISCOGS_WEB_BASE_URL`
(019) now also feeds the two link fields. No other settings change.
