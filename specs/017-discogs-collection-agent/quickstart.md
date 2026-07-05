# Quickstart: Discogs Collection Agent (017)

Get from a fresh checkout to a first conversation with your collection.

## 1. Prerequisites

- Python 3.12+
- A Discogs account that owns the collection
- A **personal access token**: Discogs → Settings → Developers →
  *Generate new token* (<https://www.discogs.com/settings/developers>)
- An OpenAI API key (repo-standard provider)

## 2. Configure secrets

Add to the repo-root `.env` (gitignored — never commit):

```bash
DISCOGS_USER_TOKEN=your_discogs_token_here
OPENAI_API_KEY=sk-...
# optional overrides
# DISCOGS_USERNAME=your_username          # normally resolved via /oauth/identity
# COLLECTION_AGENT_MODEL=gpt-4o-mini
# SNAPSHOT_PATH=collection-agent/data/snapshot.json
```

## 3. Install

```bash
cd collection-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 4. First sync

```bash
python -m collection_agent sync
```

Expected: a progress display over two phases — collection pages, then
per-release enrichment (~1 request/second under the Discogs rate limit; a
500-record collection takes roughly 8–10 minutes; ~1,000 records up to ~20).
Ctrl-C is safe: re-running `sync` resumes from the journal.

```bash
python -m collection_agent status
# → username, synced_at (age), completeness=complete, 512 instances,
#   498 unique releases, collection value (min/median/max), warnings
```

## 5. Chat

```bash
python -m collection_agent chat
```

Try (Spanish or English — the agent answers in your language):

```text
¿Qué géneros tengo y en qué proporción?
top 10 labels
mis discos de house de los 90
which of my records are the rarest or most wanted?
¿cuánto vale mi colección?
los 5 más caros
links de video para los discos de techno del 96
movelos a una carpeta nueva "Techno 96"
```

The last one triggers the write flow: the agent shows the plan (records +
target folder) and the **CLI itself** asks `¿Confirmás? [y/N]` — nothing is
sent to Discogs unless you type `y`. Afterward it reports per-record results
and refreshes the snapshot.

Meta-commands inside chat: `/status` (snapshot age/state), `/refresh`
(re-sync), `/exit`.

## 6. Run tests

```bash
cd collection-agent
pytest             # unit + integration; no live Discogs/OpenAI calls
```

## 7. Validation walkthrough (maps to spec success criteria)

| Check | How | SC |
|---|---|---|
| Genre proportions sum & unknown bucket | ask genres question; compare total to `status` instance count | SC-001/002 |
| Filter correctness | ask genre and genre+decade lists; spot-check against Discogs website | SC-003 |
| Extensibility | add a registry entry (e.g. `catno`) + unit test; existing filter tests untouched and passing | SC-003a |
| Links grounded | pick a release with videos on its Discogs page; compare links verbatim | SC-004 |
| Move + confirm | move one record to a new folder; verify on discogs.com; verify `n` cancels cleanly | SC-005 |
| Sync bounds | `sync` on your real collection; confirm minutes-scale, progress visible, no 429 storm | SC-006 |
| Groundedness | every value/rarity/rating answer names its basis; partial snapshot answers carry the warning | SC-007 |

## Troubleshooting

- **"configuration error (2)"** — `DISCOGS_USER_TOKEN` missing/invalid;
  regenerate at Developer Settings.
- **Sync ends `partial` (exit 3)** — check `status` warnings; re-run `sync`
  to resume. Analytics will keep warning until the sync completes.
- **Throttled notices** — normal on large syncs; the governor is pacing to
  Discogs' 60/min window.
- **Empty answers about images/videos** — verify the token is being sent;
  unauthenticated requests get no media URLs.
