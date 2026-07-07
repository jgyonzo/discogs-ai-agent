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
      10 legible records.
- [ ] SC-003: ≤ 3 taps per add after the photo (4 for a duplicate).
- [ ] SC-004: zero writes without an explicit confirmation tap
      (verify against the Discogs web UI history).
- [ ] SC-005: spot-check candidate fields/links/thumbnails against
      discogs.com — all verbatim, zero constructed values.
- [ ] SC-006: known-owned records show the duplicate marker with the
      right copy count.
- [ ] SC-007: kill the server mid-session; the journal accounts for
      every completed cycle.
- [ ] After the session: run `python -m collection_agent sync` and
      confirm the chat agent sees the added records.

Record the outcome here as a validation note (021 precedent).
