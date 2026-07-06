# Quickstart: YouTube Playlist Integration (020)

Re-scoped 2026-07-06: anonymous play links. **There is no setup** — no
Google Cloud project, no OAuth, no new dependencies, no new env vars
required (the two new settings have working defaults).

## The two-prompt journey (SC-001)

```bash
cd collection-agent
uv run python -m collection_agent chat
```

```
> find records from electronic genre and minimal style, show the
  record list and its associated youtube links
  … listing + per-record media links (existing behavior) …

> create a youtube playlist called discogs-minimal and insert the links
  Here are your play links (nothing was created or saved in any account):
  • link 1 — records 1–7 (50 videos):
    https://www.youtube.com/watch_videos?video_ids=…
  • link 2 — records 8–12 (33 videos):
    https://www.youtube.com/watch_videos?video_ids=…
  Skipped: Artist – Title (no stored videos)
  To keep one: open it, then YouTube ▸ playlist panel ▸ ⋮ ▸
  "Save playlist" and name it "discogs-minimal".
```

Click a link: it opens YouTube playing the videos in listing order as
a temporary playlist. To save it you must be logged into YouTube in
that browser; saving and naming happen entirely on the site.

Sampler mode: "…just one track per record" ⇒ one link with the first
stored video of each record (`videos_per_record="first"`).

## Verification

- **SC-001**: run the journey above; confirm play order matches the
  listing and the site-side save works.
- **SC-002**: spot-audit — every `video_ids` entry in an emitted link
  appears verbatim (as a `watch?v=` id) in the listed records'
  `media_links` output.
- **SC-004**: works on a fresh clone with only `DISCOGS_USER_TOKEN` +
  `OPENAI_API_KEY` configured.

## Tests

```bash
cd collection-agent && pytest    # offline; snapshot fixtures; no network
```

## Optional overrides

| Env var | Default | Meaning |
|---|---|---|
| `YOUTUBE_WEB_BASE_URL` | `https://www.youtube.com` | base for emitted links |
| `YOUTUBE_PLAYLIST_MAX_IDS` | `50` | max video ids per link (chunking threshold) |
