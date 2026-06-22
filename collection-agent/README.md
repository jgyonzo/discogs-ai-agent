# collection-agent (experiment)

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
| `matcher.py` | Fuzzy matcher: normalize `(artist, title)`, Jaro-Winkler scoring in DuckDB, top-K candidates with a per-field score breakdown. `vinyl_only=True` restricts to vinyl pressings (right default for a record crate). |
| `notebooks/01_matcher_experiments.ipynb` | Experiment: messy-input demo, a ground-truth accuracy eval (corrupt known releases, measure top-1/top-5 hit rate), and a disambiguation deep-dive. |
| `data/sample_batches.csv` | A small DJ-style messy input to play with. |
| `requirements.txt` | Notebook deps. |

## Run it

```bash
# from repo root — installs into the existing .venv
.venv/bin/python -m pip install -r collection-agent/requirements.txt

# then open notebooks/01_matcher_experiments.ipynb (VS Code / Jupyter),
# selecting the repo .venv as the kernel.
```

Requires the published DuckDB to exist (`data/published/duckdb/discogs.duckdb`).
If it's missing, run the ETL first — see the repo `README.md` §Quickstart.

## Status / next steps

This is a v0 matcher to find out **how good auto-matching can get** before any
write side is built. Candidate next moves, roughly in order:

1. **Disambiguation signals** — fold `year` / `country` / `primary_format_group`
   and the label `catno` (from `release_label_bridge`) into scoring so the
   matcher picks the *right pressing*, not just the right title.
2. **Blocking / index** — a normalized, persisted index so matching a few
   hundred rows is fast without the in-memory full-scan.
3. **Discogs API write side** — OAuth/token client to add matched releases to
   a collection and create a folder per batch. Net-new; nothing here yet.
4. **Streaming links** — Discogs dumps carry user-submitted `<videos>`
   (YouTube) per release; the ETL doesn't parse them today. Spotify/SoundCloud
   would need their own APIs.

If/when this graduates from experiment to a real component, it should get its
own feature spec under `specs/` per the project's SDD workflow.
