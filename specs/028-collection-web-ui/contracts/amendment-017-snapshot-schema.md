# Amendment: 017 snapshot-schema contract — delta 1 (028-collection-web-ui, replay addendum 4)

Amends `specs/017-discogs-collection-agent/contracts/snapshot-schema.md`
(and the completeness state machine in 017's `data-model.md`). FIRST
amendment to this contract. Snapshot JSON schema: **unchanged** — no new
fields in `meta`, `folders[]`, or `records[]`; every existing snapshot
file stays valid.

## Delta 1 — live writes during a sync never yield `complete` (FR-017)

### New sidecar: the live-write marker

- Path: `<snapshot_path>.live-writes` (default
  `collection-agent/data/snapshot.json.live-writes`, inside the
  gitignored `data/` dir and the 027 bind mount).
- Content: an opaque token (UTF-8 text), rewritten atomically
  (`tmp + os.replace`) on every snapshot-affecting live write. Only
  equality matters; readers MUST NOT parse it. Absent file = no live
  write recorded yet.
- Writers (exhaustive): `SnapshotStore.mark_stale()` (scan add — 022 R4)
  and `SnapshotStore.patch_moved_instances()` (confirmed folder moves —
  017 §4). Both bump the marker FIRST, unconditionally — including when
  no snapshot exists yet (an add during the very first sync).
- Never part of the snapshot; never served to the LLM or the page.

### Sync rule (normative)

`run_sync` captures the marker before its first Discogs request and
compares it again right before persisting, inside the store's write
lock:

| Sync outcome | Marker unchanged | Marker changed (live write landed mid-sync) |
|---|---|---|
| every release enriched | `complete`; journal cleared (as before) | **`stale`**; warning appended to `sync_stats.warnings`; journal **kept** |
| interrupted / failed enrichments | `partial`; journal kept (as before) | `partial`; same warning appended; journal kept |

Rationale: the instance pass ran before the write, so the result may
lack it — `stale` ("a write succeeded after `synced_at`") is exactly the
existing state's meaning. Keeping the journal makes the follow-up
standard sync re-list instances and enrich only releases not yet
journaled (the new add), i.e. seconds instead of a full re-enrichment.

### Write lock (normative)

Per snapshot path, in-process: `mark_stale`, `patch_moved_instances`,
and the sync's final compare-and-save are mutually exclusive, so a
read-modify-write can never overwrite a fresher snapshot written in
between. Cross-process (terminal `sync` + `serve`): the on-disk marker
still detects the write (the long window); the residual
milliseconds-wide RMW interleaving across processes is accepted (no
file locking — pre-existing since 022, documented).

### Completeness semantics — table row amended

| State | Meaning | Serving rule |
|---|---|---|
| `stale` | a US4 write succeeded after `synced_at` (and wasn't patched in place) **— or during the sync that produced this snapshot (FR-017)** | serve with staleness disclosed; suggest refresh |

### State machine — additions

```text
sync running ──live write lands (marker bumped)──▶ sync ends stale (journal kept)
stale (journal kept) ──standard sync──▶ complete   (only new releases enriched)
```

Unchanged: a folder move with NO sync running still patches in place and
the snapshot stays `complete`; a scan add with no sync running still
flips `complete → stale`. Terminal `sync` exit code for a sync that ends
`stale` is `3` (EXIT_PARTIAL — "not complete, re-run sync"), already the
behavior for any non-complete result.
