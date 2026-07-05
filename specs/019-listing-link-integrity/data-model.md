# Data Model: Listing Link Integrity (019)

No snapshot schema change. No new entities. This feature adds one settings
field and one field to the per-record **display shapes** that read tools
return to the LLM.

## 1. Settings (VII(a))

| Field | Env alias | Default | Notes |
|---|---|---|---|
| `discogs_web_base_url: str` | `DISCOGS_WEB_BASE_URL` | `https://www.discogs.com` | Web (human-facing) base. Distinct from `discogs_base_url` / `DISCOGS_BASE_URL` (`https://api.discogs.com`, API). No trailing slash. |

## 2. Release-page URL (derived value)

```text
release_url = f"{settings.discogs_web_base_url}/release/{record.release_id}"
```

- Source id: `CollectionRecord.release_id` — populated by the sync
  **instance pass**, therefore present for every record in every snapshot
  state (complete / partial / pre-enrichment) and in every snapshot already
  on disk. Never `instance_id` (collection-instance id space).
- Built exclusively by `tools/common.py::release_page_url(settings, record)`.
  Tool code holds no URL literals.
- **Invariant (id spaces)**: for any record, `release_url` embeds
  `release_id`; `instance_id` never appears inside any URL the tools emit.
- **Invariant (copies)**: two instances of the same release share the same
  `release_url` but keep distinct `instance_id`s — the URL identifies the
  release page, the instance id identifies the copy (moves, ordinals).

## 3. Listing entry display shapes (per-record units returned to the LLM)

### 3.1 `filter_records` — `matches[]` and `fallback_matches[]` (browse.py `_display`)

| Key | Before | After |
|---|---|---|
| `instance_id` | int | int (unchanged — opaque follow-up reference) |
| `artist`, `title`, `year`, `format`, `folder` | unchanged | unchanged |
| `release_url` | — | **NEW** str, per §2 |

`fallback_matches` (018 FR-011) uses the same `_display`, so fallback
entries carry the link with zero extra code — required by the spec's
zero-match edge case.

### 3.2 `top_n` — ranking entries (analytics.py `_display`)

| Key | Before | After |
|---|---|---|
| `instance_id`, `artist`, `title`, `year` (+ basis fields) | unchanged | unchanged |
| `release_url` | — | **NEW** str, per §2 |

### 3.3 `media_links` — `per_record[]` (media.py)

| Key | Before | After |
|---|---|---|
| `instance_id`, `artist`, `title`, `year` | unchanged | unchanged |
| `links[] {uri, title, duration_s}` | unchanged (verbatim URIs) | unchanged |
| `none` | unchanged (explicit per-record flag) | unchanged |
| `release_url` | — | **NEW** str, per §2 |

Payload `note` updated: URIs remain verbatim/unmodified; `release_url` is
the record's Discogs **page**, not playable media — offer it as such, never
as a listening link.

## 4. Session state

Unchanged. `last_listing_instance_ids` keeps pointing at instance ids
(including the 018 fallback re-point). No URL is stored in session state —
it is recomputed per payload from the snapshot record.

## 5. Prompt content model (VII(b) analog)

Ground rule 1 gains link-sourcing sentences (procedural, not attribute
prose): page links only from `release_url`; music/video links only from
`media_links`; URL construction from any identifier forbidden — including
for records not in the collection (no link is fabricated for an absent
record). `{attribute_block}` rendering untouched.
