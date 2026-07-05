# Data Model: Discogs Collection Agent (017)

Phase 1 output. In-memory/pydantic models and the snapshot file shape. The
authoritative file schema lives in `contracts/snapshot-schema.md`; this
document adds relationships, validation rules, and state transitions.

## Entity overview

```text
SnapshotMeta 1──1 Snapshot ──* CollectionRecord (one per INSTANCE)
                                 │  embeds ReleaseDetail (enrichment fields)
                                 │  embeds MediaLink[*]
Folder *──1 Snapshot (folder list cached at sync time)
AttributeSpec (registry, code-level — not persisted)
WritePlan 1──* PlannedMove (session-scoped, never persisted to snapshot)
```

## 1. Snapshot (file: `collection-agent/data/snapshot.json`)

| Field | Type | Notes |
|---|---|---|
| `meta` | SnapshotMeta | see below |
| `folders` | Folder[] | as of sync time |
| `records` | CollectionRecord[] | **one entry per instance** (clarification Q4) |

### SnapshotMeta

| Field | Type | Rules |
|---|---|---|
| `schema_version` | int | starts at 1; bump on breaking shape change |
| `username` | str | resolved via `/oauth/identity` at sync |
| `synced_at` | ISO-8601 str | end of last successful sync |
| `completeness` | enum `complete\|partial\|stale` | see state machine |
| `instance_count` | int | MUST equal `len(records)` when `complete` |
| `unique_release_count` | int | distinct `release_id` |
| `enriched_count` | int | releases with enrichment present |
| `collection_value` | {`minimum`, `median`, `maximum`: str} | as returned by Discogs (currency-formatted strings), basis = "Discogs estimate" |
| `sync_stats` | {`requests`, `duration_s`, `warnings`: []} | Principle-III-style audit trail |

**Validation**: `completeness == "complete"` requires
`enriched_count == unique_release_count` and no fatal warnings. Analytics
tools MUST refuse to present a `partial` snapshot as complete (FR-003c) and
disclose `synced_at` age on request (FR-003b).

### Completeness state machine

```text
(no file) ──sync start──▶ partial ──all pages+enrichment ok──▶ complete
complete ──successful US4 write──▶ stale (or patched in place: stays complete)
complete/stale ──user "refresh"──▶ partial ──▶ complete
partial   ──interrupt/crash──▶ partial (journal preserved; resumable)
```

`stale` snapshots still serve analytics — with the age/staleness disclosed.
`partial` snapshots serve nothing silently: every answer carries the partial
warning, or the agent offers to finish the sync first.

## 2. CollectionRecord (one per instance)

Merges the **instance pass** (collection endpoint) with the **enrichment
pass** (`GET /releases/{id}`). Enrichment fields are nullable until enriched.

| Field | Type | Source | Notes |
|---|---|---|---|
| `instance_id` | int | instance pass | unique key within snapshot |
| `release_id` | int | instance pass | many instances may share it |
| `folder_id` | int | instance pass | FK → Folder |
| `date_added` | ISO str | instance pass | |
| `my_rating` | int 0–5 \| null | instance pass | 0 = unrated → treated as null |
| `title` | str | instance pass | |
| `artists` | str[] | instance pass | display names, ANV-resolved |
| `year` | int \| null | instance pass | 0 → null ("unknown") |
| `labels` | {`name`, `catno`}[] | instance pass | |
| `formats` | str[] | instance pass | e.g. `["Vinyl", "12\""]` |
| `genres` | str[] | enrichment (fallback: instance pass) | |
| `styles` | str[] | enrichment (fallback: instance pass) | |
| `country` | str \| null | **enrichment only** | null → "unknown" bucket |
| `community_have` | int \| null | enrichment | |
| `community_want` | int \| null | enrichment | |
| `community_rating_avg` | float \| null | enrichment | |
| `community_rating_count` | int \| null | enrichment | |
| `num_for_sale` | int \| null | enrichment | |
| `lowest_price` | float \| null | enrichment | null when none for sale |
| `videos` | MediaLink[] | enrichment | may be empty |
| `enriched_at` | ISO str \| null | enrichment | null ⇒ not yet enriched |

**Validation rules** (enforced by the store on load/save):
- `instance_id` unique across `records`.
- Multi-valued fields are lists, never comma-joined strings.
- Derived values are **not persisted** (decade, scarcity — computed by the
  registry at read time), so threshold changes never require a re-sync.

### MediaLink

| Field | Type | Notes |
|---|---|---|
| `uri` | str | as stored by Discogs (FR-014: verbatim) |
| `title` | str \| null | |
| `duration_s` | int \| null | |

## 3. Folder

| Field | Type | Notes |
|---|---|---|
| `folder_id` | int | 0 = "All" (virtual — **rejected** as a move target; guard in organize tools), 1 = "Uncategorized" (real built-in folder — **valid** move target). Per contracts/agent-tools.md §4 |
| `name` | str | |
| `count` | int | as of sync |

## 4. AttributeSpec (registry — code, not persisted)

The extensibility contract behind FR-013 (details in
`contracts/agent-tools.md`).

| Field | Type | Notes |
|---|---|---|
| `name` | str | canonical, e.g. `genre` |
| `aliases` | str[] | en+es, e.g. `["género", "genero", "genres"]` |
| `kind` | enum `categorical\|numeric\|text` | drives allowed filter ops |
| `multi` | bool | multi-valued per record (genre, label, format…) |
| `extract` | fn(CollectionRecord) → value \| values \| null | single source of truth for both aggregation and filtering |
| `unknown_label` | str | bucket name for nulls (e.g. "unknown country") |

**Derived attributes** are ordinary specs whose `extract` computes:
`decade` (from `year`), `scarcity` (from have/want/num_for_sale with
settings-sourced thresholds — R9).

**Invariant (VII(b) analog)**: the system prompt's attribute documentation is
rendered from this registry; no prompt file may enumerate attributes
statically.

## 5. WritePlan / PlannedMove (session-scoped, in-memory only)

| Field | Type | Notes |
|---|---|---|
| `plan_id` | str (uuid4) | issued by `propose_moves`, single-use |
| `target_folder` | {`folder_id` \| null, `name`, `create`: bool} | `create=true` ⇒ folder made at execute time |
| `moves` | PlannedMove[] | |
| `state` | enum `proposed\|confirmed\|executed\|cancelled\|expired` | |

PlannedMove: `instance_id`, `release_id`, `display` (artist – title),
`from_folder_id`, plus post-execution `result: ok|failed` and `error`.

**State transitions**: `proposed → confirmed` happens **only** via the CLI
runtime's y/n prompt (never via an LLM tool call — R8). `confirmed →
executed` re-validates each instance live before mutating; per-item failures
are recorded without aborting the rest (FR-020). Any new `propose_moves`
expires a prior unexecuted plan. Plans are never persisted to the snapshot.

## 6. Analytics result shapes (tool outputs)

Uniform shapes so the LLM narrates rather than computes (FR-022/024):

- **Aggregation** (`aggregate_by`): `{attribute, unit: "instances", total,
  buckets: [{value, count, pct}], unknown_bucket, note}` — `sum(count) ==
  total` when `multi=false`; when `multi=true` the note states counting is
  per-record-per-value and `pct` is of `total` records (FR-004 disclosure).
- **Listing** (`filter_records`): `{criteria_applied, unsupported_criteria,
  matches: [{artist, title, year, …}], count, truncated}` — `unsupported_criteria`
  non-empty implements FR-013a; `matches` capped (default 50) with
  `truncated=true` disclosed.
- **Ranking** (`top_n` for rated/expensive/rare): `{basis, thresholds?,
  excluded_missing_data: int, items: [...]}` — `basis` string satisfies the
  "criterion stated" requirements (FR-006/008/010).
- **Links** (`media_links`): `{per_record: [{record, links: MediaLink[],
  none: bool}]}` — explicit `none` flag per record (FR-016).
