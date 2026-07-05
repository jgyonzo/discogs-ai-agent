# Contract: Collection Snapshot Schema (017)

The snapshot is a **component-private cache** (not a cross-component
contract), but its shape is normative for the collection-agent package:
tools, tests, and the sync all program against this schema. Breaking changes
bump `schema_version` and require a migration or forced re-sync.

**Location**: `collection-agent/data/snapshot.json` (path settings-sourced:
`SNAPSHOT_PATH`). Gitignored — it is personal data.
**Write discipline**: atomic (`<path>.tmp` + `os.replace`). Sync-in-progress
enrichment results journal to `<path>.sync.tmp.json` (same record shape,
keyed by `release_id`) to make interrupted syncs resumable.

## Top level

```jsonc
{
  "meta": { /* SnapshotMeta */ },
  "folders": [ { "folder_id": 3, "name": "Techno", "count": 42 } ],
  "records": [ /* CollectionRecord, one per INSTANCE */ ]
}
```

## `meta` (SnapshotMeta)

```jsonc
{
  "schema_version": 1,
  "username": "example_user",
  "synced_at": "2026-07-05T14:32:11Z",
  "completeness": "complete",          // "complete" | "partial" | "stale"
  "instance_count": 512,               // MUST equal records.length when complete
  "unique_release_count": 498,
  "enriched_count": 498,               // == unique_release_count when complete
  "collection_value": {                // verbatim Discogs strings, basis = Discogs estimate
    "minimum": "US$1,340.12",
    "median":  "US$2,410.55",
    "maximum": "US$4,102.90"
  },
  "sync_stats": {
    "requests": 517,
    "duration_s": 612.4,
    "warnings": ["release 123456 returned 404; kept without enrichment"]
  }
}
```

### Completeness semantics (normative)

| State | Meaning | Serving rule |
|---|---|---|
| `complete` | last sync finished; every unique release enriched (404s excepted, warned) | serve freely; disclose age on request |
| `partial` | sync interrupted/failed mid-way | every answer MUST carry a partial-data warning, or the agent offers to finish the sync first; never presented as complete (FR-003c) |
| `stale` | a US4 write succeeded after `synced_at` (and wasn't patched in place) | serve with staleness disclosed; suggest refresh |

## `records[]` (CollectionRecord — one per instance)

```jsonc
{
  "instance_id": 987654321,       // unique within snapshot
  "release_id": 249504,
  "folder_id": 3,
  "date_added": "2024-11-02T09:12:44Z",
  "my_rating": null,              // 1–5; Discogs 0 (unrated) stored as null

  // instance pass (basic_information)
  "title": "Never Gonna Give You Up",
  "artists": ["Rick Astley"],
  "year": 1987,                   // Discogs 0 stored as null
  "labels": [ { "name": "RCA", "catno": "PB 41447" } ],
  "formats": ["Vinyl", "7\"", "Single", "45 RPM"],

  // enrichment pass (GET /releases/{id}); all null/[] until enriched
  "genres": ["Electronic", "Pop"],
  "styles": ["Synth-pop"],
  "country": "UK",
  "community_have": 252,
  "community_want": 42,
  "community_rating_avg": 3.42,
  "community_rating_count": 45,
  "num_for_sale": 58,
  "lowest_price": 0.63,
  "videos": [
    { "uri": "https://www.youtube.com/watch?v=te2jJncBVG4",
      "title": "Rick Astley - Never Gonna Give You Up (Extended)",
      "duration_s": 330 }
  ],
  "enriched_at": "2026-07-05T14:30:02Z"   // null ⇒ not yet enriched
}
```

## Invariants

1. `instance_id` unique across `records`; multiple records MAY share
   `release_id` (duplicate copies — each counts, clarification Q4).
2. When `meta.completeness == "complete"`:
   `meta.instance_count == len(records)` and every distinct `release_id` has
   `enriched_at != null` **or** a corresponding 404 warning in `sync_stats`.
3. Missing data is `null` / `[]` — never `0`, `""`, or a guessed value.
   Aggregations map nulls to explicit unknown buckets at read time.
4. Derived values (decade, scarcity, percentages) are **never persisted** —
   they are computed by the attribute registry so threshold/settings changes
   don't require a re-sync.
5. No credentials, no other users' identities, nothing beyond the fields
   above is persisted.
6. Media URIs stored and returned verbatim (signed URLs must not be edited).
