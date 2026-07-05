# collection-agent

Two independent tools sharing this component directory (no imports between
them):

- **`src/collection_matcher/`** — offline batch matcher (experiment): messy
  DJ lists → confident Discogs release matches, against the ETL-published
  DuckDB. Described below.
- **`src/collection_agent/`** — conversational agent over the owner's **live
  Discogs collection** (feature `specs/017-discogs-collection-agent/`):
  sync-to-snapshot analytics, filtered listings, media links, and
  confirmation-gated folder organization, from a terminal chat.

## Environment variables (collection_agent)

Read from the repo-root `.env` (gitignored — never commit secrets):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DISCOGS_USER_TOKEN` | yes | — | Discogs personal access token (Settings → Developers) |
| `OPENAI_API_KEY` | yes | — | LLM provider key |
| `DISCOGS_USERNAME` | no | via `/oauth/identity` | Username override |
| `COLLECTION_AGENT_MODEL` | no | `gpt-4o-mini` | OpenAI model id |
| `SNAPSHOT_PATH` | no | `collection-agent/data/snapshot.json` | Snapshot location |

Quickstart: `specs/017-discogs-collection-agent/quickstart.md`.

---

# collection_matcher (experiment)

A separate, exploratory project inside this monorepo. Goal: turn a messy
DJ-supplied list of records (`artist`, `title`, one row per disc, grouped in
batches — with typos) into confident **Discogs release matches**, as a step
toward importing them into a personal Discogs collection with per-batch folders.

This folder is **read-only and offline**. It reuses exactly one thing from the
rest of the repo: the ETL-published catalog at
`data/published/duckdb/discogs.duckdb` (~19M releases). It does **not** import
from `etl/` or `agent/`, does not call the Discogs API, and writes nothing
back to Discogs. The write side (add-to-collection, create-folder) and any
streaming-link enrichment are deliberately out of scope for now.

## What's here

| Path | What it is |
|---|---|
| `src/collection_matcher/matcher.py` | Fuzzy matcher: normalize `(artist, title)`, Jaro-Winkler scoring in DuckDB, top-K candidates with a per-field score breakdown. Scores both a *structured* (artist-vs-artist + title-vs-title) and a *combined* (whole query vs `artist + title`) view and keeps the higher — so rows written without a clean separator still match. `vinyl_only=True` restricts to vinyl pressings (right default for a record crate). |
| `src/collection_matcher/review_batch.py` | Run one batch through the matcher and print a confidence-sorted review queue to the terminal. Quick look, no files written. |
| `src/collection_matcher/export_batch.py` | Run one batch and write `data/<batch>_review.csv` — one row per disc with Discogs URLs, alternate candidates, and a `confirmed` column to fill in. |
| `notebooks/01_matcher_experiments.ipynb` | Experiment: messy-input demo, a ground-truth accuracy eval (corrupt known releases, measure top-1/top-5 hit rate), and a disambiguation deep-dive. |
| `data/sample_batches.csv` | A small DJ-style messy input to play with. |
| `requirements.txt` | Notebook + script deps. |

## Input format

The tools read a **single CSV** at `data/pending_discogs.csv` (gitignored —
it's your data). Two columns:

```csv
batch,title
Lote-Feb,Stewart Walker - Live Extracts
Lote-Feb,Alex Smoke - Simple Things
Lote-26,MICROTEK - Mean Machine
```

- **`batch`** — a label grouping discs (e.g. per purchase). You review and
  export one batch at a time; it becomes a Discogs collection folder later.
- **`title`** — the whole disc as one messy string, usually `ARTIST - Title`.

What the parser tolerates in `title`:

- Any dash variant as the artist/title separator (`-`, `–`, `—`), with or
  without surrounding spaces, plus invisible bidi / zero-width marks that
  spreadsheets leave around it.
- **No separator at all** (`noah pred navigation ep`) — the combined-score
  view still matches it against `artist + title`.
- Typos, casing, accents, punctuation (normalized away on both sides).
- Trailing noise tokens like `2xLP` / `3xlp` are harmless.

Known weak spot: rows that jam the **label** in front
(`LABEL ARTIST TITLE`, or `ARTIST LABEL` with no title). The matcher only
scores against artist + title, so these need a manual note (see below).

`data/sample_batches.csv` is a committed, safe example if you don't have your
own `pending_discogs.csv`.

## Run it

```bash
# from repo root — installs into the existing .venv
.venv/bin/python -m pip install -r collection-agent/requirements.txt
```

Requires the published DuckDB to exist (`data/published/duckdb/discogs.duckdb`).
If it's missing, run the ETL first — see the repo `README.md` §Quickstart.

**Review a batch in the terminal** (nothing written):

```bash
# from collection-agent/ (or add collection-agent/src to PYTHONPATH from repo root)
cd collection-agent
PYTHONPATH=src ../.venv/bin/python -m collection_matcher.review_batch Lote-Feb
```

Prints a queue sorted worst-confidence-first, with a high-confidence count
(`score >= 0.95` and unambiguous) so you know how much needs eyeballing.

**Export a batch to a review CSV** for clicking through on Discogs:

```bash
cd collection-agent
PYTHONPATH=src ../.venv/bin/python -m collection_matcher.export_batch Lote-Feb
# -> collection-agent/data/Lote-Feb_review.csv
```

(Once the component's `pyproject.toml` lands — next step in feature 017 —
`pip install -e .` makes the `PYTHONPATH=src` prefix unnecessary.)

Columns in the exported CSV:

| Column | Meaning |
|---|---|
| `raw_input`, `parsed_artist`, `parsed_title` | Your row and how it was split. |
| `matched_artist` … `format` | The best-matched release. |
| `score` | Blend of the structured and combined similarity (0–1). |
| `ambiguous` | `True` when the runner-up is within 0.02 — usually *multiple pressings* of the right record, so you pick the exact one. |
| `release_id`, `discogs_url` | The match; click the URL to verify. |
| `alt_release_ids` | Next-best candidate ids if the top pick is off. |
| `confirmed` | **Blank, for you** — fill `y` / `n` / or paste a corrected `release_id`. |
| `note` | Optional hand-authored note (see below). |

Both scripts default to `vinyl_only=True`.

### Optional: per-row review notes

Some rows can't be settled automatically (the label-in-front case, a title
that's really a track name, a pick between pressings). You can keep notes in
`data/review_notes.csv` (gitignored — batch-specific research, not part of the
tool):

```csv
raw_input,note
KAHLWILD - Maison Doree Ep,"'Kahlwild' is the label; correct release is 13977491 (Alejandro Vivanco - Maison Doree EP)."
```

`raw_input` is matched leniently (dash spacing, bidi marks, and case are
ignored), so write the keys in plain ASCII. Any matching row gets its `note`
copied into the exported CSV. No file → the `note` column is just blank.

## Status / next steps

A v0 matcher plus a per-batch review workflow, to find out **how good
auto-matching can get** before any write side is built. Candidate next moves,
roughly in order:

1. **Label-aware scoring** — recurring rows jam the label in front
   (`LABEL ARTIST TITLE`) and the matcher misses them because it only scores
   artist + title. A third scoring view that includes `primary_label_name`
   (and/or the `catno` from `release_label_bridge`) would auto-catch these
   instead of needing a manual `review_notes.csv` entry.
2. **Disambiguation signals** — fold `year` / `country` / `primary_format_group`
   and the label `catno` into scoring so the matcher picks the *right pressing*,
   not just the right title (shrinks the `ambiguous` rows).
3. **Discogs API write side** — OAuth/token client to add confirmed releases
   (the `confirmed` column) to a collection and create a folder per batch.
   Net-new; nothing here yet.
4. **Streaming links** — Discogs dumps carry user-submitted `<videos>`
   (YouTube) per release; the ETL doesn't parse them today. Spotify/SoundCloud
   would need their own APIs.

If/when this graduates from experiment to a real component, it should get its
own feature spec under `specs/` per the project's SDD workflow.
