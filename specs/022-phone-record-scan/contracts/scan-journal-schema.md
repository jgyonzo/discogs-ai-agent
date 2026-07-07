# Contract: Scan Session Journal (022)

Append-only JSONL journal of scan-cycle outcomes (FR-013, R5). One file
per server run:

```
<COLLECTION_AGENT_SCAN_JOURNAL_DIR>/<session_id>.jsonl
```

- Default dir: `collection-agent/data/scan-sessions/` (inside the
  gitignored `data/`; the directory is created on first use).
- `session_id`: server-start UTC stamp `YYYYMMDD-HHMMSSZ`.
- Encoding: UTF-8, one JSON object per line, LF-terminated.
- **Append-only**: lines are never rewritten or deleted; each append is
  flushed before the cycle's HTTP response is sent. A journal append
  failure fails the cycle loudly (reported `failed` to the page) —
  never a silent drop.

## Line schema (`ScanCycleOutcome`)

| Key | Type | Required | Meaning |
|---|---|---|---|
| `ts` | string | yes | ISO-8601 UTC, e.g. `2026-07-07T18:30:12Z` |
| `seq` | int | yes | 1-based, strictly increasing within the file |
| `scan_id` | string | yes | `"{session_id}-{seq of the producing cycle}"` |
| `outcome` | string | yes | `added` \| `skipped` \| `no_match` \| `failed` |
| `source` | string | yes | `photo` \| `manual_search` |
| `evidence_kinds` | array[string] | yes | subset of `barcode`, `catno`, `artist_title`, `text`; `[]` when nothing was extracted. For photo cycles these are the rungs actually attempted — `text` appears when the composed free-text fallback fired (addendum 1, FR-020) |
| `release_id` | int | when a release was involved | Discogs release id |
| `release_title` | string | when a release was involved | candidate `title`, verbatim |
| `instance_id` | int | `outcome=added` only | from the live add response |
| `duplicate_add` | bool | no (default `false`) | `true` when this add was a confirmed extra copy |
| `detail` | string | no | failure reason / skip context, human-readable |
| `evidence` | object | photo/manual cycles (addendum 1, FR-021) | extracted evidence field values, compact (no None/empty entries; never the image). Manual-search cycles carry `{"q": <query>}` |

Unknown keys MUST be ignored by readers (forward compatibility).

## Outcome semantics

- `added` — live write succeeded; `release_id`, `release_title`,
  `instance_id` present.
- `skipped` — owner saw candidates and moved on without adding
  (`release_id` present if a specific candidate was open). Includes
  auto-closed cycles (addendum 2, FR-022): a cycle abandoned by
  starting the next scan is journaled `skipped` with
  `detail="auto-closed: superseded by a new scan"`.
- `no_match` — identification/search produced no candidates and the
  owner acknowledged (or abandoned) the cycle.
- `failed` — a cycle that reached a definite failure (add rejected by
  Discogs, journal-adjacent I/O error surfaced elsewhere, etc.);
  `detail` says why. Transport errors on `/api/scan` before any
  candidate existed are NOT journaled (no completed cycle).

## Review guarantee

After an interruption at any point, replaying the file top-to-bottom
reconstructs the session: every completed cycle up to the interruption
appears exactly once, in order (SC-007). This file is for the owner's
review; no other component consumes it (it lives outside every
published contract surface).
