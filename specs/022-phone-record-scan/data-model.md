# Data Model: Phone Record Scan (022)

All models are pydantic v2 `BaseModel`s in
`collection_agent/scan/models.py` unless noted. Nothing here is
persisted except the journal line (see
[contracts/scan-journal-schema.md](contracts/scan-journal-schema.md));
the snapshot's own model is 017's and is not modified.

## ScanEvidence

Best-effort structured reading of one photo (R2). Produced by the
vision step, consumed only by the search ladder — never displayed as
fact (FR-003).

| Field | Type | Notes |
|---|---|---|
| `artist` | `str \| None` | as printed; None if not legible |
| `title` | `str \| None` | release title |
| `label` | `str \| None` | label name |
| `catno` | `str \| None` | catalog number as printed |
| `barcode` | `str \| None` | digits only (normalized: strip spaces/hyphens) |
| `format_hints` | `list[str]` = `[]` | e.g. `"2xLP"`, `"45 RPM"` |
| `notes` | `str \| None` | anything else legible the model flags (not searched) |

Validation: all-None is legal (`is_empty` property → no-match path,
FR-012). Barcode normalized by a model validator; a barcode of
non-digit garbage is dropped to None rather than searched.

`evidence_kinds` (derived): subset of
`{barcode, catno, artist_title, text}` actually present — logged in the
journal and shown in the UI as "matched by …".

## Candidate

One release offered to the owner. Every display field is copied
verbatim from a Discogs search-result item (FR-005; 019 discipline).

| Field | Type | Source (search-result key) |
|---|---|---|
| `release_id` | `int` | `id` |
| `title` | `str` | `title` (Discogs "Artist - Title" string, shown as-is) |
| `year` | `str \| None` | `year` |
| `country` | `str \| None` | `country` |
| `formats` | `list[str]` = `[]` | `format` |
| `labels` | `list[str]` = `[]` | `label` |
| `catno` | `str \| None` | `catno` |
| `thumb_url` | `str \| None` | `thumb` (fallback `cover_image`) — URL verbatim, never constructed |
| `discogs_uri` | `str \| None` | `uri` — verbatim; page renders it as the "view on Discogs" link |
| `duplicate` | `DuplicateStatus` | computed locally (below) |

Constraint: absent source keys stay `None`/`[]` and render as absent —
no backfilling from evidence or any other source.

## DuplicateStatus

Computed per candidate at response time (FR-009/010, R4).

| Field | Type | Notes |
|---|---|---|
| `state` | `Literal["in_collection", "not_in_collection", "unknown"]` | |
| `copies` | `int` = `0` | snapshot instance count + session adds; meaningful when `in_collection` |
| `added_this_session` | `bool` = `false` | true if the session-added set contains the release |
| `reason` | `str \| None` | set when `unknown`: `"no snapshot"` / `"snapshot stale"` … |

Rules:
- snapshot record(s) with this `release_id` → `in_collection`,
  `copies` = instance count (+ session adds).
- no snapshot file / unloadable → `unknown` (`reason="no snapshot"`).
- snapshot `completeness != complete` → counts still shown but state
  stays `in_collection`/`unknown` per presence; presence-absence from a
  partial/stale snapshot is NEVER reported as `not_in_collection` —
  it degrades to `unknown` (`reason="snapshot stale"` /
  `"snapshot partial"`), except a session-added release which is
  always `in_collection` with `added_this_session=true`.
- complete snapshot, no record, no session add → `not_in_collection`.

## ScanCycleOutcome (journal line)

One completed cycle; append-only (FR-013). Full schema in
[contracts/scan-journal-schema.md](contracts/scan-journal-schema.md).

| Field | Type | Notes |
|---|---|---|
| `ts` | `str` | ISO-8601 UTC |
| `seq` | `int` | 1-based, monotonic within session |
| `outcome` | `Literal["added","skipped","no_match","failed"]` | |
| `source` | `Literal["photo","manual_search"]` | |
| `evidence_kinds` | `list[str]` | which evidence drove the search (photo cycles) |
| `release_id` | `int \| None` | when a specific release was involved |
| `release_title` | `str \| None` | verbatim candidate title for human review |
| `instance_id` | `int \| None` | from the add response, `added` only |
| `duplicate_add` | `bool` = `false` | true when this was a confirmed second copy |
| `detail` | `str \| None` | failure reason / skip context |

## ScanSession (in-memory, `scan/session.py`)

One per server run (R5/R9). Not persisted beyond its journal file.

| Field | Type | Notes |
|---|---|---|
| `session_id` | `str` | UTC start stamp `YYYYMMDD-HHMMSSZ`; names the journal file |
| `seq` | `int` | last issued cycle seq |
| `seen_release_ids` | `set[int]` | every release_id served as a candidate this session — the add-endpoint allowlist (R9) |
| `added_release_ids` | `dict[int, int]` | release_id → copies added this session (duplicate overlay) |
| `log` | `list[ScanCycleOutcome]` | mirror of journal lines for `GET /api/session` |

State rules: `seen_release_ids` only grows; an `/api/add` for an id
not in it is rejected without any Discogs call. Appends to `log` and
the journal happen together; journal append failures fail the cycle
loudly (the outcome is reported to the page as `failed`).

## API request/response models

Defined in `scan/models.py`, wire shapes normative in
[contracts/scan-api.md](contracts/scan-api.md):
`ScanResponse` (`scan_id`, `evidence_summary`, `candidates`,
`more_matches`, `message`), `AddRequest` (`scan_id`, `release_id`,
`confirm_duplicate=false`), `AddResponse` (`status`:
`added | needs_duplicate_confirmation | rejected | failed`, `detail`,
`instance_id?`, `duplicate?`), `SkipRequest`, `SessionResponse`
(entries newest-first). `scan_id` is `"{session_id}-{seq}"`, issued per
scan/search cycle.

## State transitions (page ⇄ server)

```
camera-ready ──photo──▶ identifying ──candidates──▶ choosing
choosing ──tap candidate (not dup)──▶ confirm ──POST /api/add──▶ added ─▶ camera-ready
choosing ──tap candidate (dup)──▶ confirm ×2 ──add(confirm_duplicate)──▶ added ─▶ camera-ready
choosing ──none of these──▶ manual-search ──text──▶ choosing
identifying ──no evidence / no results──▶ no-match ──▶ manual-search | camera-ready (logs no_match)
any server failure ──▶ error shown ──▶ camera-ready (logs failed when a cycle completed)
skip at any choosing point ──▶ camera-ready (logs skipped)
```

## Relationships to existing (017) models

- Reads `Snapshot.records[*].release_id`/`instance_id` for duplicate
  counts; reads `meta.completeness` for degradation.
- Calls `SnapshotStore.mark_stale()` after successful adds — the only
  snapshot mutation this feature performs (R4).
- `Folder` (id 1 default) validated live at startup via
  `client.get_folders()` (R9); the snapshot's folder list is never
  trusted for writes.
