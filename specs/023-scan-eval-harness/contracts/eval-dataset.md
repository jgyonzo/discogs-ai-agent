# Contract: Eval Dataset Layout & Ground Truth (023)

Governs the two labeled image sources the eval harness consumes. Both live
under the component's gitignored `data/` tree; nothing here is ever committed
or redistributed (uploader copyright — see amendment-017-discogs-consumption-2
licensing rule).

## 1. Discogs-image dataset (`COLLECTION_AGENT_EVAL_DATASET_DIR`, default `collection-agent/data/eval/discogs-images/`)

```text
discogs-images/
├── NOTICE.txt                       # licensing notice, written by the builder
├── manifest.jsonl                   # THE ground-truth source (append-only)
└── {release_id}_{kind}{ordinal}.{ext}   # e.g. 724223_secondary1.jpg
```

### 1.1 `manifest.jsonl` line types

Append-only; UTF-8; one JSON object per line; `type` discriminates. Readers
MUST tolerate and ignore a torn (unparseable) trailing line. Filenames are
never parsed for ground truth — only manifest lines are.

**`run_header`** — appended once per builder invocation:

```json
{"type": "run_header", "built_at": "2026-07-07T18:00:00Z",
 "snapshot_completeness": "complete", "snapshot_synced_at": "…",
 "images_per_release": 2}
```

**`release`** — appended once per processed release:

```json
{"type": "release", "release_id": 724223, "status": "downloaded",
 "fetched_at": "2026-07-07T18:00:05Z",
 "images": [
   {"kind": "secondary", "source_uri": "https://i.discogs.com/…",
    "file": "724223_secondary1.jpg", "status": "downloaded"},
   {"kind": "primary", "source_uri": "https://i.discogs.com/…",
    "file": null, "status": "failed", "detail": "HTTP 403 (expired URI)"}
 ]}
```

Release `status`: `downloaded` (≥1 image file on disk) · `no_images` (release
has an empty `images[]`; recorded, not silently skipped — spec US1/AS5) ·
`failed` (release fetch failed or every image download failed).

### 1.2 Builder rules

- Worklist = distinct `release_id`s of the local snapshot; missing snapshot →
  actionable error, exit code 2 (config-error convention).
- Selection: sort `secondary` before `primary`, take the first
  `images_per_release` (spec FR-003). Fewer available → take what exists.
- Resume: a release with a `downloaded` / `no_images` line is skipped;
  `failed` releases are retried (fresh `get_release` → fresh signed URIs).
  Image files are written atomically (tmp name + rename) so a crash never
  leaves a corrupt image beside a manifest claim.
- Every builder invocation appends its own `run_header` (multiple headers are
  normal; the newest header before a release line describes that line's run).

## 2. Ground truth semantics

For every manifest image with `status == "downloaded"`, the ground-truth label
is its enclosing release line's `release_id`. The harness scores a pipeline
answer as a **hit** iff that id appears in the returned candidate ids
(rank recorded; master/other-pressing near-misses are misses — spec
Assumptions).

## 3. Retained-photo source (`COLLECTION_AGENT_SCAN_RETENTION_DIR`, default `collection-agent/data/eval/scan-photos/`)

```text
scan-photos/
└── <session_id>/                    # 022 session id, e.g. 20260707-160209Z
    ├── <scan_id>.<ext>              # cycle reached a scan_id, e.g. 20260707-160209Z-3.jpg
    └── pending-<n>.<ext>            # upload that never got a scan_id
```

- Written only when `COLLECTION_AGENT_SCAN_RETAIN_PHOTOS=true` (default
  false). Flag off ⇒ this directory is never created or touched and the scan
  server's behavior is byte-identical to 022 (spec FR-007 / SC-003).
- Files hold the **original upload bytes** (no re-encoding); `<ext>` derives
  from the upload's content type.
- Saved under `pending-<n>.<ext>` immediately after the upload-size gate;
  atomically renamed to `<scan_id>.<ext>` when the cycle id is assigned.
  Files are never deleted or rewritten by the component.
- Retention I/O failure: one loud server-side warning; the scan cycle
  proceeds unaffected (deliberate contrast with the journal's loud-500 rule —
  the journal is the audit record, retention is diagnostics; spec FR-009).

### 3.1 Label join (harness-side, lazy)

For file `<scan_id>.<ext>` in `<session_id>/`: read the 022 journal
`<COLLECTION_AGENT_SCAN_JOURNAL_DIR>/<session_id>.jsonl`; if a line has that
`scan_id` and `outcome == "added"`, the label is that line's `release_id`.
Any other case — `skipped` / `no_match` / `failed` / auto-closed / missing
journal / `pending-*` file — is **unlabeled**: reported and counted, excluded
from accuracy denominators, and never sent to the vision model (no billable
call for an unscorable image). The journal schema itself is untouched by 023.

## 4. Containment guard (normative)

All three configured directories (dataset, retention, results) default under
`collection-agent/data/`, which the repo-root `.gitignore` ignores via its
`data/` rule. A unit test MUST fail if that rule disappears/negates for
collection-agent paths or if any of the three settings defaults moves outside
`collection-agent/data/`.
