# Implementation Plan: YouTube Playlist Integration

**Branch**: `020-youtube-playlist-integration` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/020-youtube-playlist-integration/spec.md`
(re-scoped 2026-07-06: anonymous play links instead of OAuth account
writes — owner decision; superseded OAuth design preserved in
research R6 for the deferred follow-up)

## Summary

Close the deferred "v2 YouTube playlists" scope with a **read-only**
capability: a new `playlist_links` tool turns a conversational record
listing into click-to-play YouTube links
(`{base}/watch_videos?video_ids=…` — verified live 2026-07-06). Opening
a link plays the records' stored videos in listing order as a temporary
playlist that the owner can save and name **on the YouTube site**; the
agent never touches any account. Design is pure 019 pattern: video ids
are parsed deterministically from stored `MediaLink.uri` values (never
LLM-supplied), the URL shape lives in exactly one settings-fed helper,
and ground rule 1 extends so the LLM presents play links only from the
tool payload. Capacity honesty replaces the old quota problem: links
cap at 50 ids (settings-sourced), large slices chunk into
record-aligned, labeled links with no silent truncation, and every
answer accounts for 100% of the requested records (covered or skipped
with reason). No OAuth, no credentials, no new dependencies, no write
gate, no session/CLI changes.

**Component(s) touched**: `collection-agent` only (plan gate
requirement). No new third-party dependencies.

## Technical Context

**Language/Version**: Python ≥3.12 (existing `collection-agent/pyproject.toml`)
**Primary Dependencies**: existing only (openai, httpx, pydantic v2, pydantic-settings, rich) — the re-scope removed the planned Google libraries
**Storage**: local JSON snapshot, READ-ONLY (schema unchanged, no re-sync; `CollectionRecord.videos` already holds every needed URI). Nothing new written to disk — no credentials, no token files
**Testing**: pytest (`cd collection-agent && pytest`), 146 existing tests; new tests are offline (snapshot fixtures, pure-function parser/chunker tests) — no network calls
**Target Platform**: developer terminal (macOS/Linux), same as 017/018/019; the emitted links are opened by the owner's own browser
**Project Type**: single component in monorepo — CLI conversational agent
**Performance Goals**: snapshot-served at conversational speed (SC-005); the tool performs zero network I/O
**Constraints**: VII(a) — both new config values (`youtube_web_base_url`, `youtube_playlist_max_ids`) settings-sourced; VII(b) analog — prompt changes are procedural ground-rule edits (link sourcing, honest saving), attribute prose stays registry-rendered; link integrity — video ids only via deterministic parsing, URL shape only in `build_watch_videos_url` (019 precedent); accepted risk — `watch_videos` is undocumented (spec Assumptions, research R1)
**Scale/Scope**: collection 300–1k records (currently 393; 2,798 stored videos, 100% YouTube; 7.5 videos per video-bearing record ⇒ multi-link answers are the normal case in all-videos mode); 2 settings fields, 1 pure-helper module, 1 read ToolDef, 1 prompt edit, 2 contract documents

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| I. Layered, contract-first data architecture | N/A | No ETL layer or published DuckDB touched. |
| II. Streaming, bounded memory | N/A | No XML/pipeline code touched. |
| III. Reproducible runs | N/A | No pipeline execution changes. |
| IV. Data quality gates | N/A | No layer outputs change; snapshot schema unchanged. |
| V. Agent-friendly analytics surface | N/A | Catalog surface untouched. |
| VI. Components & Contracts | **PASS** | `collection-agent` only; no cross-component imports; **no new dependencies**. New surface documented in this feature's `contracts/youtube-playlists.md`; 017's agent-tools contract amended via `contracts/amendment-017-agent-tools.md` (deltas 9–10 against §1/§5 — third amendment, after 018's 1–5 and 019's 6–8; §4 write path explicitly untouched). |
| VII(a). Configuration sources | **PASS** | `youtube_web_base_url` (alias `YOUTUBE_WEB_BASE_URL`, default `https://www.youtube.com`) and `youtube_playlist_max_ids` (alias `YOUTUBE_PLAYLIST_MAX_IDS`, default 50) — no hardcoded URLs or caps in tool code; the `watch_videos` path constant lives in one helper. |
| VII(b). Prompt-authoring discipline (analog) | **PASS** | Prompt edits touch ground rules 1 and 6 (play-link sourcing; honest save-on-site capability statement) — procedural guidance only; `{attribute_block}` remains the sole schema prose. |
| VII(c). Read-only runtime mechanics | N/A | No mounts; feature writes nothing anywhere. |
| Secrets constraint | **PASS** (vacuously) | Re-scope eliminated all credentials; nothing secret is introduced. |
| Scope guardrails | **PASS** | v2 YouTube *search* stays out of scope; account-write playlists explicitly deferred (spec Assumptions, research R6). |
| Spec-driven flow / plan gate | **PASS** | This plan; phases committed separately. |

**Post-Phase-1 re-check**: PASS — design artifacts introduce no new
violations; no Complexity Tracking entries needed.

## Project Structure

### Documentation (this feature)

```text
specs/020-youtube-playlist-integration/
├── spec.md              # /speckit-specify output, re-scoped 2026-07-06 (committed)
├── plan.md              # This file
├── research.md          # Phase 0 output (R1–R5 + R6 deferred-OAuth summary)
├── data-model.md        # Phase 1 output (payload shapes; no persisted entities)
├── quickstart.md        # Phase 1 output (zero-setup journey)
├── contracts/
│   ├── youtube-playlists.md           # play-link surface: endpoint reliance, tool, verification
│   └── amendment-017-agent-tools.md   # deltas 9–10 against 017 §1/§5
├── checklists/
│   └── requirements.md  # spec quality checklist
└── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
collection-agent/
├── src/collection_agent/
│   ├── settings.py                    # + youtube_web_base_url, youtube_playlist_max_ids
│   ├── youtube_links.py               # NEW: video_id_from_uri (deterministic parser, R2)
│   │                                  #      + build_watch_videos_url (sole URL-shape site, R1)
│   ├── prompts/system.md              # ground rules 1 & 6 edits (delta 10)
│   └── tools/
│       └── playlist.py                # NEW: playlist_links ToolDef (read-only; reuses
│                                      #      media.py's _resolve + common.py envelope)
└── tests/
    ├── unit/
    │   ├── test_youtube_links.py      # parser: watch/youtu.be/shorts/embed/reject;
    │   │                              #   URL builder uses settings base, ≤cap ids
    │   ├── test_playlist_links.py     # resolution reuse, skips (no_videos/unresolvable_uri),
    │   │                              #   dedup-first-occurrence, chunking invariants
    │   │                              #   (record-aligned, disjoint, complete, ≤cap),
    │   │                              #   completeness partition (SC-003), all-skipped ⇒ no link,
    │   │                              #   one-per-record mode, suggested_name/save_hint echo
    │   └── test_prompt_groundrules.py # extend: play-link sourcing + honest-saving clauses
    └── integration/
        └── test_agent_playlist.py     # stub-LLM turn: tool registered read-only; payload
                                       #   narration includes warnings envelope (repo pattern)
```

**Structure Decision**: single existing component (`collection-agent/`)
extended in place. One new pure-helper module at the package root
(sibling of `registry.py`, mirroring how 019 put `release_page_url` in
a shared helper) and one new tools module shaped like
`tools/media.py`. `agent.py`, `cli.py`, `models.py`, and the `discogs/`
and `snapshot/` subpackages are untouched.

## Design Notes (Phase 1 highlights)

- **No gate, deliberately** (research R4): the §4 two-phase gate exists
  to make unconfirmed *writes* unreachable; `playlist_links` writes
  nothing (it doesn't even make a network call — the browser does).
  Adding confirmation theater around a no-op would dilute the gate's
  meaning for real writes.
- **Chunking invariants** (spec FR-005, data-model §1): links are
  record-aligned, disjoint, jointly complete over usable videos, each
  ≤ the settings cap, labeled with covered records + counts — all
  unit-tested as properties, since multi-link answers are the *normal*
  case at this collection's video density (7.5/record).
- **Link integrity** (spec FR-002/010, SC-002): the 019 discipline —
  ids only from `video_id_from_uri`, URL shape only in
  `build_watch_videos_url`, prompt rule says play links come only from
  the payload. Proactive application of the postmortem pattern.
- **Honest capability** (spec FR-008): payload carries
  `suggested_name` + `save_hint`; ground rule 6 obliges the agent to
  say saving/naming happens on the site and never claim account-side
  creation — the anti-018 framing.
- **Resolution reuse**: `tools/media.py::_resolve` provides refs/name
  mentions/last-listing semantics; tasks may promote it to
  `tools/common.py` (import hygiene), with behavior contractually
  identical either way.
- **Live verification** (SC-001/002/004): owner-run replay per
  quickstart — click-through, play-order check, site-side save, and a
  fresh-clone zero-setup check; recorded in tasks as the final gate
  before merge (018/019 replay precedent).

## Complexity Tracking

No constitution violations to justify — table intentionally empty.
