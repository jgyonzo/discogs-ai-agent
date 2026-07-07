# Contract: Scan Server HTTP API (022)

The HTTP surface served by `collection-agent`'s `scan` subcommand.
Consumed ONLY by the feature's own static page; it is not a public API
and is not consumed by any other component (Constitution VI — the
`frontend` component must not couple to it). Breaking changes require
amending this contract.

Server: FastAPI app from `collection_agent.scan.server.create_app(...)`,
bound to `COLLECTION_AGENT_SCAN_HOST:COLLECTION_AGENT_SCAN_PORT`
(default `0.0.0.0:8022`), plain HTTP, home LAN only.

Global rules:

- **No secrets on the wire**: no response, header, or the page itself
  ever contains the Discogs token or the OpenAI key (FR-017).
- **Verbatim candidate data**: every candidate field including
  `thumb_url` and `discogs_uri` is copied verbatim from the Discogs
  search response; the server never constructs URLs or fills gaps
  (FR-005; 019 precedent).
- **Write gate**: the only writing route is `POST /api/add`; it demands
  a `release_id` previously served as a candidate in this session and
  explicit duplicate confirmation where required (FR-007/009; R9).
- Errors use a typed JSON body `{"error": {"code": str, "message": str}}`
  with an appropriate HTTP status; messages are honest and user-readable
  (FR-012). Codes below.

## `GET /`

Returns the self-contained scan page (`text/html`). No templating of
secrets or config beyond what the page needs (nothing — it discovers
everything via the API).

## `GET /api/health`

`200 {"status": "ok", "session_id": str, "snapshot": "complete"|"partial"|"stale"|"missing"}`.
Used by the page footer and the quickstart smoke check.

## `POST /api/scan`

Multipart form, field `photo`: image file (JPEG/PNG/WebP/HEIC as sent
by phones).

- `413 {"error":{"code":"image_too_large", ...}}` when the upload
  exceeds `COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES` (default 10 MiB) —
  checked before any vision work (FR-016).
- `415 {"error":{"code":"unsupported_media_type", ...}}` for non-image
  uploads.
- `502 {"error":{"code":"vision_unavailable", ...}}` when the vision
  call fails after client-side retry policy; `502
  {"error":{"code":"discogs_unavailable", ...}}` when search fails.
  Neither is journaled as a completed cycle; the page returns to
  camera-ready with the message shown.

`200` response (`ScanResponse`):

```json
{
  "scan_id": "20260707-183000Z-4",
  "source": "photo",
  "evidence_summary": {
    "kinds": ["barcode", "artist_title"],
    "fields": {"artist": "…", "title": "…", "label": null,
                "catno": null, "barcode": "5011166123457",
                "format_hints": ["2xLP"]}
  },
  "candidates": [
    {
      "release_id": 123456,
      "title": "Artist - Title",
      "year": "1997",
      "country": "UK",
      "formats": ["Vinyl", "LP"],
      "labels": ["Some Label"],
      "catno": "SL-001",
      "thumb_url": "https://…discogs…/thumb.jpg",
      "discogs_uri": "/Artist-Title/release/123456",
      "duplicate": {"state": "not_in_collection", "copies": 0,
                     "added_this_session": false, "reason": null}
    }
  ],
  "more_matches": false,
  "message": null
}
```

Semantics:

- Search ladder per FR-004: barcode → catno(+label) → artist+title;
  a rung runs only if the previous produced nothing. `evidence_summary.kinds`
  reflects what was extracted; the UI may show "matched by barcode".
- Addendum 1 (FR-019/020): a `catno` whose separator-stripped value is
  10+ digits is normalized to barcode evidence before the ladder runs;
  when every structured rung is absent or empty, one final free-text
  rung searches `q=` composed from the available evidence (artist,
  title or lead track, label). `ScanEvidence` carries a `tracks` field
  (lead track doubles as the 12″-single title); it appears in
  `evidence_summary.fields` like any other field.
- Candidates de-duplicated by `release_id`, capped at
  `COLLECTION_AGENT_SCAN_CANDIDATES_MAX` (default 8); `more_matches`
  true when Discogs pagination reports more items than shown (FR-006).
- **No-match is not an error**: `200` with `candidates: []` and a
  plain-language `message` ("Couldn't identify this record — try manual
  search"). The cycle is journaled `no_match` (FR-012/013).
- Empty evidence (nothing legible) short-circuits to the same no-match
  shape WITHOUT calling Discogs.
- Every `release_id` returned is added to the session's seen-candidates
  allowlist.

## `GET /api/search?q=<free text>`

Manual fallback (FR-012). Same response shape and semantics as
`/api/scan` with `source: "manual_search"` and
`evidence_summary.kinds = ["text"]`; queries Discogs `q=` free-text
search. `400 {"error":{"code":"empty_query",...}}` on blank `q`.
A zero-result manual search is journaled `no_match` only if the owner
then returns to camera (i.e., the page sends `/api/skip` with no
release; see below) — the search itself is side-effect-free apart from
the allowlist.

## `POST /api/add`

```json
{"scan_id": "20260707-183000Z-4", "release_id": 123456,
 "confirm_duplicate": false}
```

Gate order (all server-side):

1. `release_id` not in the session allowlist →
   `403 {"error":{"code":"unknown_candidate", ...}}` — no Discogs call
   (R9: nothing the vision/LLM step produced can reach the write path;
   only server-served candidates can).
2. Candidate's current duplicate state is `in_collection` or
   `added_this_session`, and `confirm_duplicate` is `false` →
   `200 {"status": "needs_duplicate_confirmation", "duplicate": {…},
   "detail": "Already in your collection (N copies)…"}` — **no write**
   (FR-009).
3. Otherwise: live
   `POST /users/{username}/collection/folders/{folder_id}/releases/{release_id}`
   through the rate-governed client to
   `COLLECTION_AGENT_SCAN_FOLDER_ID` (default 1).

Outcomes:

- Success → `200 {"status": "added", "instance_id": <int>,
  "release_id": 123456, "detail": "Added to Uncategorized"}`; journal
  `added` (with `duplicate_add` when it was a confirmed duplicate);
  `SnapshotStore.mark_stale()`; session-added set updated (FR-008/011).
- Discogs failure → `200 {"status": "failed", "detail": "<honest
  reason>"}` (or `502` on transport-level failure); journal `failed`;
  snapshot NOT touched; the page offers retry (edge case: add fails
  midway).

## `POST /api/skip`

```json
{"scan_id": "20260707-183000Z-4", "release_id": 123456}
```

`release_id` optional (absent = abandoned cycle / no-match
acknowledged). `200 {"status":"skipped"}`. Journals `skipped` (or
`no_match` when no candidates had been produced for that scan_id).
Idempotent per `scan_id`: a second skip for the same cycle is a no-op
(`200`, no duplicate journal line).

## `GET /api/session`

`200 {"session_id": str, "entries": [ScanCycleOutcome, …]}` —
newest-first, the full in-memory session log (FR-013). Entries match
[scan-journal-schema.md](scan-journal-schema.md).

## Page behavior (normative for the static page)

- Single self-contained HTML file; no external resources fetched at
  runtime except this API and the verbatim Discogs `thumb_url` images.
- Camera capture via `<input type="file" accept="image/*"
  capture="environment">`.
- State machine per data-model.md; after `added`/`skipped` the page is
  back at camera-ready in one step (FR-014, SC-003).
- Duplicate-marked candidates render the marker text and require the
  extra confirmation tap driven by the `needs_duplicate_confirmation`
  response — the page never sends `confirm_duplicate: true` on the
  first tap.
- The session log panel renders `GET /api/session` and refreshes after
  every completed cycle.
