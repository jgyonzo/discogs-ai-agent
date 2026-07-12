# Data Model: Scan Release & Master Selection (026)

All changes are additive to 022's scan models. No journal schema change
(research R7). No eval schema change (research R9).

## 1. `Candidate` (extended — `scan/models.py`)

Existing fields unchanged and still verbatim-from-payload. Two NEW
server-built fields (research R3):

| Field | Type | Source | Semantics |
|---|---|---|---|
| `release_page_url` | `str \| None` (default `None`) | built from `settings.discogs_web_base_url` + `release_id` | The release's Discogs web page. Always populated by candidate construction (`release_id` is required); the default exists only for model additivity. NEVER client-constructed. |
| `master_page_url` | `str \| None` (default `None`) | built from `settings.discogs_web_base_url` + `master_id` | The master's Discogs web page. Populated iff `master_id` is present; `None` means "this release has no master" — nothing is fabricated (FR-002/007). |

**Invariant**: `master_page_url` is non-None **iff** `master_id` is
non-None. `release_page_url`/`master_page_url` are the ONLY link values the
page may render; their URL shapes exist in exactly one code site per id
space (`tools/common.py`, grep-enforced).

**Selected-release semantics** (no new field): in every non-empty
`candidates` list, **position 0 is the selected release** — the ladder +
024 exact-catno re-rank already order best-first; this is now a documented
contract property (amendment-022-scan-api-3), not a ranking change.

## 2. Versions item → `Candidate` mapping (research R4)

Input: one `versions[]` item from `GET /masters/{master_id}/versions`
(fields per `docs/discogs_api_reference.md` §7.6).

| Candidate field | Versions item source | Rule |
|---|---|---|
| `release_id` | `id` | `int()`, required |
| `title` | `title` | verbatim (versions titles may omit the artist — never re-composed) |
| `year` | `released` | `str()` if present, else `None` |
| `country` | `country` | verbatim or `None` |
| `formats` | `format` | `[format]` — the whole descriptive string as a one-element list; never split/parsed |
| `labels` | `label` | `[label]` if present, else `[]` |
| `catno` | `catno` | verbatim or `None` |
| `thumb_url` | `thumb` | verbatim or `None` |
| `discogs_uri` | — | `None` (not in payload; the page link is `release_page_url`) |
| `master_id` | request context | the validated `master_id` of the fetch (genuine, server-checked) |
| `release_page_url` / `master_page_url` | built | same single-site builders as search candidates |
| `duplicate` | computed | same fresh `snapshot_duplicate_checker` overlay as scan results (explicit `unknown` degradation preserved, FR-011) |

**Dedup rule**: items whose `release_id` is already registered in the
requesting cycle (including the selected release itself — the versions
list contains it) are dropped before display; an all-dropped page is an
honest "no additional versions" result (FR-012).

## 3. `VersionsResponse` (NEW wire model — `scan/models.py`)

Response of `GET /api/master-versions`:

| Field | Type | Semantics |
|---|---|---|
| `scan_id` | `str` | the cycle these versions extend (echo of the validated request param) |
| `master_id` | `int` | the validated master these are versions of |
| `candidates` | `list[Candidate]` | mapped + deduped versions (§2); may be empty |
| `total_versions` | `int` | verbatim `pagination.items` from Discogs — the full version count for honest truncation messaging (FR-013) |
| `message` | `str \| None` | honest empty-result text when `candidates` is empty; `None` otherwise |

Truncation display rule: the page states "showing N of T" whenever
`total_versions` exceeds the number of items Discogs returned in the page
(cap = `scan_versions_max`); dedup-dropped items never count as "shown".

## 4. `_CycleContext` (extended — `scan/server.py`, in-memory only)

Gains `master_ids: set[int]` — the master ids of the cycle's registered
candidates, refreshed on every `_register`. This is the server-side gate
input for `/api/master-versions` (research R5): a requested `master_id`
not in the open cycle's set → 403 `unknown_master`. Versions-fetched
candidates register into the same context (`titles` map + session
allowlist), which is what makes `/api/add` and the journal work unchanged.

State lifecycle unchanged: cycles are superseded/auto-closed exactly as in
022 FR-022/023; a versions fetch does NOT bump the generation and adds no
new cycle states.

## 5. `Settings` (ONE new field — `settings.py`)

| Field | Env alias | Default | Purpose |
|---|---|---|---|
| `scan_versions_max` | `COLLECTION_AGENT_SCAN_VERSIONS_MAX` | `25` | `per_page` of the single master-versions request = display cap of the on-demand list (research R6). Deliberately distinct from `scan_candidates_max` (identification precision vs browse breadth). |

## 6. Unchanged surfaces (explicit)

- `ScanResponse`, `AddRequest`, `AddResponse`, `SkipRequest`,
  `SessionResponse`: byte-identical shapes (candidates inside
  `ScanResponse` carry the new additive fields).
- `ScanCycleOutcome` / journal schema: untouched (R7).
- `ScanEvidence`, vision prompt, ladder, normalization: untouched (R9).
- Eval dataset/results/replay schemas: untouched; link fields are not
  persisted in eval results.
