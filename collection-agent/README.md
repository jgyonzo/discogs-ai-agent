# collection-agent

Two independent tools sharing this component directory (no imports between
them):

- **`src/collection_matcher/`** — offline batch matcher (experiment): messy
  DJ lists → confident Discogs release matches, against the ETL-published
  DuckDB. Described below.
- **`src/collection_agent/`** — conversational agent over the owner's **live
  Discogs collection** (feature `specs/017-discogs-collection-agent/`,
  extended by 018–022): sync-to-snapshot analytics, filtered listings,
  media links, click-to-play YouTube playlist links
  (`specs/020-youtube-playlist-integration/`), confirmation-gated
  folder organization, from a terminal chat — plus a phone
  **record-scan** mode (`specs/022-phone-record-scan/`) that adds
  physical records to the collection from photos.

## Environment variables (collection_agent)

Read from the repo-root `.env` (gitignored — never commit secrets):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DISCOGS_USER_TOKEN` | yes | — | Discogs personal access token (Settings → Developers) |
| `OPENAI_API_KEY` | yes | — | LLM provider key |
| `DISCOGS_USERNAME` | no | via `/oauth/identity` | Username override |
| `COLLECTION_AGENT_MODEL` | no | `gpt-4o-mini` | OpenAI model id |
| `SNAPSHOT_PATH` | no | `collection-agent/data/snapshot.json` | Snapshot location |
| `DISCOGS_WEB_BASE_URL` | no | `https://www.discogs.com` | Base for tool-built release-page links (019) |
| `YOUTUBE_WEB_BASE_URL` | no | `https://www.youtube.com` | Base for tool-built play links (020) |
| `YOUTUBE_PLAYLIST_MAX_IDS` | no | `50` | Max video ids per play link (chunking threshold) |
| `LISTING_TITLE_MAX_CHARS` | no | `70` | Title display cap in listing tables |
| `COLLECTION_AGENT_VISION_MODEL` | no | `gpt-4o-mini` | Vision model for photo evidence extraction (022) |
| `COLLECTION_AGENT_SCAN_HOST` | no | `0.0.0.0` | Scan server bind address (022) |
| `COLLECTION_AGENT_SCAN_PORT` | no | `8022` | Scan server port (022) |
| `COLLECTION_AGENT_SCAN_FOLDER_ID` | no | `1` (Uncategorized) | Target folder for scan adds; validated live at startup (022) |
| `COLLECTION_AGENT_SCAN_CANDIDATES_MAX` | no | `8` | Candidate list cap per scan (022) |
| `COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES` | no | `10485760` | Photo upload cap, 10 MiB (022) |
| `COLLECTION_AGENT_SCAN_JOURNAL_DIR` | no | `collection-agent/data/scan-sessions` | Per-session scan journal location (022) |
| `COLLECTION_AGENT_SCAN_VISION_TIMEOUT_S` | no | `45` | Hard cap per vision call; a re-scan supersedes the pending one (022 addendum 2) |
| `COLLECTION_AGENT_SCAN_CATNO_SEARCH_DEPTH` | no | `50` | Catno-rung fetch depth for the exact-catno re-rank (024) |
| `COLLECTION_AGENT_SCAN_VERSIONS_MAX` | no | `25` | Cap of the on-demand "other pressings of this master" list (026) |
| `COLLECTION_AGENT_EVAL_DATASET_DIR` | no | `collection-agent/data/eval/discogs-images` | Labeled eval-image dataset location (023) |
| `COLLECTION_AGENT_EVAL_IMAGES_PER_RELEASE` | no | `2` | Image download cap per release, secondary-preferred (023) |
| `COLLECTION_AGENT_EVAL_RESULTS_DIR` | no | `collection-agent/data/eval/runs` | Eval run results location (023) |
| `COLLECTION_AGENT_SCAN_RETAIN_PHOTOS` | no | `false` | Opt-in: keep uploaded scan photos for the eval dataset (023) |
| `COLLECTION_AGENT_SCAN_RETENTION_DIR` | no | `collection-agent/data/eval/scan-photos` | Where retained scan photos land (023) |
| `LANGSMITH_TRACING` | no | off | Enable LangSmith tracing (021) — absent ⇒ strict no-op |
| `LANGSMITH_API_KEY` | no | — | LangSmith key; if unset while tracing is on, chat continues untraced (one notice, never an error) |
| `LANGSMITH_ENDPOINT` | no | SDK default | LangSmith endpoint override |
| `COLLECTION_AGENT_LANGSMITH_PROJECT` | no | `discogs-collection-agent` | LangSmith project for THIS component — deliberately not `LANGSMITH_PROJECT`, which belongs to `agent/` |

### Tracing (021)

With `LANGSMITH_TRACING` + `LANGSMITH_API_KEY` set, every chat turn emits
one trace tree to the `discogs-collection-agent` project on
<https://smith.langchain.com>: a `run_turn` root, each LLM request with its
as-sent payload and token usage, and one span per tool execution (errors
included). Tracing observes only — it never blocks or fails a turn (trace
delivery is background/batched), and without the env vars the client isn't
even wrapped. Contract: `specs/021-langsmith-tracing/contracts/tracing.md`.

## Run the agent

```bash
cd collection-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m collection_agent sync      # first sync: minutes-scale, resumable (Ctrl-C safe)
python -m collection_agent status    # snapshot age / completeness / counts / value
python -m collection_agent chat      # conversation (es/en); /refresh /status /exit
python -m collection_agent scan      # phone record-scan server (022); --host/--port
python -m collection_agent eval-dataset  # build the labeled eval image dataset (023)
python -m collection_agent eval-run      # measure scan identification accuracy (023)
```

Analytics, filtered listings, media links, and YouTube playlist links are
answered instantly from the local snapshot (`data/snapshot.json`,
gitignored); moving records / creating folders executes **live** against
Discogs and only after the CLI itself asks `¿Confirmás? [y/N]` — the LLM
can only *propose* moves. Playlist links are click-to-play `watch_videos`
URLs built from the records' stored videos: they open as a temporary
playlist you can save and name **on the YouTube site** — the agent never
touches a YouTube account (no OAuth, no credentials, no quota).

### Run with Docker (027)

Every mode also runs containerized — no host Python needed. One image
(`collection-agent/Dockerfile`), wired into the repo-root
`docker-compose.yml` as an **opt-in** service behind the `collection`
profile, so the demo stack's plain `docker compose up` is unaffected
(guard-tested). Config comes from the same repo-root `.env`; state is the
same host `collection-agent/data/` directory (bind-mounted), so container
and venv runs are interchangeable mid-workflow in both directions — no
migration, no fresh start.

From the repo root:

```bash
docker compose --profile collection up collection-agent   # scan server on :8022
docker compose run --rm collection-agent sync             # one-shot; Ctrl-C-resumable
docker compose run --rm collection-agent status
docker compose run --rm collection-agent chat             # interactive (TTY allocated)
docker compose run --rm collection-agent eval-dataset
docker compose run --rm collection-agent eval-run --source discogs
```

Notes:

- **Phone URL**: open `http://<this-machine's-LAN-IP>:8022` on the phone.
  The URL in the container's startup banner reflects the *container's*
  interfaces, not the address phones can reach.
- **Failure posture**: the service has deliberately **no restart policy** —
  a failed startup folder validation (bad/missing `DISCOGS_USER_TOKEN`)
  exits once, loudly, with code 2, instead of retry-looping against the
  live Discogs API. Check `docker compose ps -a` + logs.
- **Exit codes** (0/1/2/3, see below) pass through `docker compose run`
  verbatim.
- **Linux hosts**: on native Linux (not Docker Desktop), files created by
  the container under `data/` are root-owned; `chown` them before mixing
  with a venv workflow. On macOS Docker Desktop, ownership is mapped
  transparently.
- The image contains code only — no secrets, no `data/` contents; the
  build context excludes them (`.dockerignore`, guard-tested). Contract:
  `specs/027-dockerize-collection-agent/contracts/docker-packaging.md`.

### Record scan (022)

`python -m collection_agent scan` serves a phone-friendly page on the
home LAN (the banner prints the URL to open on the phone — same Wi-Fi).
Photograph a sleeve, center label, or barcode: a vision model extracts
printed evidence, Discogs is searched in precision order (barcode →
catalog number → artist+title → a free-text query composed from
whatever partial evidence was read; manual text search on top), and the
matching pressings are shown with cover, year, country, format, catno,
and an "already in your collection — N copies" marker. On the
catalog-number search, pressings whose catno exactly matches what was
read are listed first (024 — Discogs' substring search otherwise buries
short catnos like `SUB 15` under `SUB 150/151/…`), and a "barcode" the
vision model read with fewer than 8 digits is discarded before searching
(025 — real UPC/EAN codes are 8–13 digits; a 4-digit misread once
hijacked the barcode search and hid a correct catalog-number match).
Results are presented as one **Selected match** (the pipeline's
top-ranked candidate, with a master-release row when it belongs to one)
followed by the other candidates under **Other possibilities** (026).
Every release — and the selected release's master — carries a
"View on Discogs ↗" link that opens the real Discogs page in a new tab
(links are server-built from genuine ids; the page never constructs a
URL). When the right album is showing but the wrong pressing, tap
**Show other pressings**: the master's versions are fetched from Discogs
(one request, only on tap — never automatically) and appear as
additional selectable candidates with the same duplicate markers and
confirmation flow; if more versions exist than are shown, the page says
so. **Nothing is written until you tap a candidate and confirm** (duplicates ask twice;
enforced server-side). Adds go to the configured folder; the snapshot
is marked stale so the chat agent re-syncs before trusting counts.
Every outcome lands in an append-only session journal
(`data/scan-sessions/<session>.jsonl`) for post-session review.

Plain-HTTP LAN service with **no page auth** (v1 assumption: trusted
single-occupant network — anyone on the LAN who finds the port can
trigger adds); do not expose it beyond the LAN. Secrets never reach the
browser.

### Identification eval (023)

`eval-dataset` walks the synced snapshot and downloads each release's
Discogs images (secondary — back covers, center labels — preferred) into a
**gitignored, local-only** dataset labeled by release id; interrupt and
re-run freely, it resumes. The images are uploader-copyrighted: never
commit, publish, or share them (the dataset carries a `NOTICE.txt`;
a guard test enforces the gitignore).

`eval-run --source discogs [--limit N]` replays every labeled image
through the *production* scan pipeline (same vision model/prompt/timeout,
same search ladder — LangSmith-traced when configured) and reports
identification rate, top-1 rate, and per-rung attribution to
`data/eval/runs/<run_id>/` (`results.jsonl` + `summary.json`). Each image
costs one billable vision call (the summary prints the count); the run is
strictly read-only against Discogs. Since 024, each result record also
carries the extracted evidence values (so misses are diagnosable from the
file alone), and the summary reports a **practical rate** beside the
strict one: misses where a candidate was another pressing of the same
master ("right album, wrong pressing") counted as near-misses. Truth
master ids come from the dataset manifest — run
`eval-dataset --backfill-masters` once to upgrade a pre-024 dataset
(metadata fetches only). Note the honesty caveat: Discogs images are
clean scans, so this measures an upper bound of real phone-photo
accuracy — the strict and practical rates bracket it.

To accumulate the *real* distribution, start the scan server with
`COLLECTION_AGENT_SCAN_RETAIN_PHOTOS=true`: uploaded photos are kept under
`data/eval/scan-photos/<session>/`, and a confirmed add labels the photo
via the session journal automatically — then `eval-run --source retained`
scores them (photos from unconfirmed cycles are counted as unlabeled, not
billed). Retention is off by default and never affects the scan flow.

`eval-run --replay <run_id>` (025) re-runs **only the search ladder** over
the evidence values recorded in a prior run's `results.jsonl` — no images
read, zero vision calls, no OpenAI key needed. Because the evidence inputs
are byte-identical between replays, per-image outcome differences are
attributable to search/normalization changes, not vision nondeterminism
(a measured ±10 images per 94 between camera runs) — this is the A/B
instrument for ladder changes. What it holds constant: extracted evidence,
truth labels, the record set (records without recorded evidence are
carried through unchanged, keeping rates directly comparable). What still
runs live: current evidence normalization (deliberately — so fixes like
the barcode gate are measurable) and Discogs search reads under the usual
rate governor. The output is a standard run whose summary names the
source run (`replay_of`); replays are themselves replayable.

Exit codes: `0` ok · `1` unexpected error · `2` configuration error
(missing/invalid token) · `3` sync ended partial (re-run `sync` to resume).

Full walkthrough: `specs/017-discogs-collection-agent/quickstart.md`
(playlists: `specs/020-youtube-playlist-integration/quickstart.md`;
record scan: `specs/022-phone-record-scan/quickstart.md`;
eval: `specs/023-scan-eval-harness/quickstart.md`;
replay: `specs/025-eval-replay-barcode-gate/quickstart.md`) ·
API notes: `docs/discogs_api_reference.md` ·
Tests: `pytest` (no live API calls).

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

Installed together with the agent — `pip install -e ".[dev]"` inside
`collection-agent/` (see "Run the agent" above) puts both
`collection_agent` and `collection_matcher` on the path.

Requires the published DuckDB to exist (`data/published/duckdb/discogs.duckdb`).
If it's missing, run the ETL first — see the repo `README.md` §Quickstart.

**Review a batch in the terminal** (nothing written):

```bash
# from collection-agent/, with its .venv active
python -m collection_matcher.review_batch Lote-Feb
```

Prints a queue sorted worst-confidence-first, with a high-confidence count
(`score >= 0.95` and unambiguous) so you know how much needs eyeballing.

**Export a batch to a review CSV** for clicking through on Discogs:

```bash
python -m collection_matcher.export_batch Lote-Feb
# -> collection-agent/data/Lote-Feb_review.csv
```

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
