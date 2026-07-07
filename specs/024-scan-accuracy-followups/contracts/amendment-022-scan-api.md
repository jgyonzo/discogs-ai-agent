# Amendment (024) to Contract: Scan API (022)

022's `contracts/scan-api.md` defines the candidate payload and the
identification pipeline's observable behavior. 024 makes one additive field
change and one ordering-rule change; everything else (endpoints, write gate,
error shapes, supersession) is untouched.

## Delta 1 — Candidate object: `master_id` (additive)

Every candidate MAY carry `master_id` (integer), **verbatim** from the
Discogs search result (019 discipline: absent stays absent, never
constructed or backfilled). Existing clients that ignore unknown keys are
unaffected.

## Delta 2 — Catno-rung candidate ordering (exact-match-first)

On the catno rung only:

1. The search fetches a deeper single page (see
   amendment-017-discogs-consumption-3 delta 1).
2. Results whose catalog number is an **exact normalized match** of the
   searched catalog number are ordered before all others. Normalization =
   remove spaces/hyphens/dots/slashes/underscores + casefold; a result with
   multiple comma-joined catnos is exact if ANY part matches; a result with
   no catno is never exact.
3. The re-rank is **stable**: within the exact group and within the
   non-exact group, Discogs' source order is preserved.
4. The list is then deduplicated and truncated to
   `COLLECTION_AGENT_SCAN_CANDIDATES_MAX` exactly as before.
5. `more_matches` continues to mean: Discogs' true total (`pagination.items`)
   exceeds the number of candidates served.

When no exact match exists in the fetched page, the served list is
byte-identical to pre-024 behavior. Barcode, artist+title, and free-text
rungs are wholly unaffected.

Every candidate FIELD remains verbatim from the search payload — this
amendment changes ordering and fetch depth only.
