# Quickstart: Phone Record Scan (022)

## Prerequisites

- `collection-agent` installed: `cd collection-agent && uv sync` (or
  `pip install -e ".[dev]"`).
- Repo-root `.env` with `DISCOGS_USER_TOKEN` and `OPENAI_API_KEY`
  (both already required by the chat agent).
- A collection snapshot for duplicate detection (optional but
  recommended): `python -m collection_agent sync`. Without it,
  duplicate status shows "unknown (no snapshot)".
- Laptop and phone on the same home network.

## Configuration (all optional, defaults shown)

| Env var | Default | Meaning |
|---|---|---|
| `COLLECTION_AGENT_VISION_MODEL` | `gpt-4o-mini` | vision-capable OpenAI model for evidence extraction |
| `COLLECTION_AGENT_SCAN_HOST` | `0.0.0.0` | bind address |
| `COLLECTION_AGENT_SCAN_PORT` | `8022` | port |
| `COLLECTION_AGENT_SCAN_FOLDER_ID` | `1` | target collection folder (1 = Uncategorized); validated live at startup |
| `COLLECTION_AGENT_SCAN_CANDIDATES_MAX` | `8` | candidate list cap |
| `COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES` | `10485760` | upload cap (10 MiB) |
| `COLLECTION_AGENT_SCAN_JOURNAL_DIR` | `collection-agent/data/scan-sessions` | session journal location |

LangSmith tracing (021) applies to the vision call automatically when
`LANGSMITH_TRACING` + `LANGSMITH_API_KEY` are set.

## Run

```bash
cd collection-agent
python -m collection_agent scan            # or: --host 0.0.0.0 --port 8022
```

The startup banner prints the URL(s) to open on the phone, e.g.
`http://192.168.1.23:8022/`. Open it in the phone browser.

Smoke check from the laptop:

```bash
curl -s http://localhost:8022/api/health
# {"status":"ok","session_id":"...","snapshot":"complete"}
```

## Scan loop (on the phone)

1. Tap **Scan** → the native camera opens. Photograph the sleeve,
   center label, or barcode.
2. Candidates appear (cover, artist–title, year, country, format,
   label, catno; "already in your collection — N copies" markers where
   applicable).
3. Tap the matching pressing → **Add** (duplicates ask once more).
4. The page confirms and returns to camera-ready. Repeat.
5. No match? The page says so and offers the manual search box.
6. The session log (bottom panel) shows every outcome; it is persisted
   at `data/scan-sessions/<session-id>.jsonl` for later review.

## Tests

```bash
cd collection-agent && pytest
```

No live Discogs/OpenAI calls anywhere in the suite (SC-008); scan
coverage runs against the injected app factory with stubbed vision and
a fake Discogs client.

## Live validation (owner-only — deliberately NOT automated)

The implement phase stops before real-world writes. Owner checklist,
to be run once with real records (spec SC-001..SC-007):

- [ ] SC-001: photo → candidates < 15 s per record on the home LAN.
- [ ] SC-002: correct pressing (or master match) in the list for ≥ 8 of
      10 legible records. *(2/2 so far — needs the 10-record batch)*
- [ ] SC-003: ≤ 3 taps per add after the photo (4 for a duplicate).
      *(owner-observed during the batch)*
- [x] SC-004: zero writes without an explicit confirmation tap
      (verify against the Discogs web UI history).
- [x] SC-005: spot-check candidate fields/links/thumbnails against
      discogs.com — all verbatim, zero constructed values.
- [x] SC-006: known-owned records show the duplicate marker with the
      right copy count. *(owner-validated 2026-07-07: re-scanned one of
      the two just-added records after the re-sync; the "already in
      your collection" marker appeared from the snapshot overlay. The
      re-scan cycle itself is absent from the journal — abandoned
      without tapping Skip, i.e. the documented orphan-cycle gap.)*
- [x] SC-007: kill the server mid-session; the journal accounts for
      every completed cycle.
- [x] After the session: run `python -m collection_agent sync` and
      confirm the chat agent sees the added records.

## Live-validation note (2026-07-07)

Two live sessions, two Crosstown Rebels 12″ singles.

**Session 1 (`20260707-130810Z`, pre-addendum-1 code, gpt-4o-mini):
0/4 identified.** Postmortem in spec replay addendum 1 (findings
F1–F3); diagnosed from the journal + 021 LangSmith traces. Fixes:
FR-019/020/021 + prompt hardening; owner repointed
`COLLECTION_AGENT_VISION_MODEL` to `gpt-5.4-mini`.

**Session 2 (`20260707-160209Z`, addendum-1 code + gpt-5.4-mini):
2/2 identified and added.** Both matched on the **barcode rung** with
correctly classified barcode digits (the same digit runs session 1
had misfiled as catno):

- DJ Silversurfer — *Ace Of Spades / Dirty Dishes* (release 724223,
  instance 2161864447)
- Frankie Flowerz — *The Key / Steppin' In* (release 297060,
  instance 2161864861)

Validated (2026-07-07, scripted against the live API + traces):

- **SC-001**: vision calls 5.1–9.0 s (plus ~1 s search) on 4 of 5
  runs — within the 15 s budget; ONE 80.6 s provider-side outlier
  (16:04:25Z). Watch item, not a code defect. gpt-5.4-mini also cut
  image prompt tokens 25.8k → 3.3k per call.
- **SC-004 PASS**: `GET /users/ionzo/collection/releases/{id}` shows
  exactly one instance per added release, ids byte-equal to the
  journal; no other writes exist.
- **SC-005 PASS (spot-check)**: re-running both barcode searches
  returns titles byte-equal to the journaled `release_title` values.
- **SC-007 PASS**: session 1 was killed mid-flow; its journal holds
  all 4 completed cycles. Session 2's journal is complete and now
  carries FR-021 evidence values.
- **Post-session sync PASS**: snapshot went stale on add (FR-011),
  re-sync → `complete`, 393 → 395 instances, both new records present
  with matching instance ids.

Open: SC-002 (10-record batch), SC-003 (tap-count observation).
SC-006 owner-validated 2026-07-07 (duplicate marker on re-scan of a
just-added record, post-sync). Known minor gap
(non-blocking): a cycle abandoned by simply scanning the next record
(without tapping Skip/None-of-these) is never journaled — session 2
has two such unclosed scan_ids. The contract only guarantees
*completed* cycles; revisit only if batch review needs it.
