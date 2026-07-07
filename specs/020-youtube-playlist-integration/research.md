# Research: YouTube Playlist Integration (020)

Re-scoped 2026-07-06 (owner decision): anonymous play links instead of
OAuth account writes. Empirical inputs: the local snapshot (393
records, 372 with videos, 2,798 stored video links — 100%
`www.youtube.com`, checked 2026-07-05) and a live probe of the
anonymous-playlist endpoint (2026-07-06). The superseded OAuth research
is summarized in R6 for the deferred follow-up.

## R1 — Play-link mechanism: `watch_videos` anonymous playlists

**Decision**: Build play links as
`{youtube_web_base_url}/watch_videos?video_ids=<id1,id2,…>`. Opening
one redirects (verified live: HTTP 303) to a `watch` page with a
temporary playlist (`list=TLGG…`) that plays the ids in order; the
site's playlist panel offers **Save playlist**, which copies it into
the viewer's library where they name it. No auth, no API project, no
quota, no account writes.

**Rationale**: Zero setup and zero write surface — the entire OAuth/
quota/confirmation-gate apparatus of the original scope disappears.
Verified working with real snapshot video ids
(`RF8lcGoS9Yc,62_rRSCHO_Q,…` → 303 → `watch?v=…&list=TLGG…`).

**Risk (accepted, recorded in spec Assumptions)**: the endpoint is
undocumented and could be retired by Google. Degradation mode: emitted
links stop resolving in the browser; the agent's answer structure is
unaffected. Mitigation path: the deferred OAuth follow-up (R6).

**Alternatives considered**:
- *OAuth account writes (original 020 scope)*: full control (named
  playlists, append, >50 videos) but requires Google Cloud setup,
  credential storage, a confirmation gate, and quota management
  (~199 video inserts/day). Deferred by owner decision — see R6.
- *`watch?v=<first>&playlist=<rest>` player parameter*: also
  undocumented, same idea but the playlist is not saveable as cleanly;
  `watch_videos` is the shape that yields a saveable temp list.

## R2 — Video ID resolution: deterministic parser, skip on failure

**Decision**: A pure function `video_id_from_uri(uri) -> str | None`
in `src/collection_agent/youtube_links.py` handling the documented
YouTube URL shapes (`watch?v=`, `youtu.be/`, `shorts/`, `embed/`, extra
query params tolerated). `None` ⇒ unresolvable ⇒ per-record skip with
reason (FR-003). The stored `uri` is never edited (snapshot
invariant 6); the parser only reads it.

**Rationale**: Empirically 2,798/2,798 stored links are standard
`watch?v=` URLs, so this is a defensive guard (spec assumption).
Deterministic parsing — never LLM extraction — makes FR-002 ("no
guessed video ids") structural: the 013→014/019 precedent of
enforcement over prompt steering.

**Alternatives considered**: regex-only `v=` extraction (rejected —
mis-parses `youtu.be` short links should one appear); LLM-supplied ids
(rejected outright — exactly the fabrication surface 019 closed).

## R3 — Capacity and chunking

**Decision**: Cap ids per link at `settings.youtube_playlist_max_ids`
(alias `YOUTUBE_PLAYLIST_MAX_IDS`, default **50** — the observed
`watch_videos` limit; Constitution VII(a): operator-tunable, not
hardcoded). Chunking is deterministic and record-aligned: videos keep
listing order; a chunk boundary never splits a record's videos unless
a single record alone exceeds the cap (then it splits with a note).
Each link is labeled with the records it covers and its video count;
the payload reports totals (FR-005 — no silent truncation).

**Rationale**: At this collection's real density (7.5 videos per
video-bearing record) ~6–7 records fill a link in all-videos mode, so
multi-link answers are the common case, not the edge. Record-aligned
boundaries make the labels honest ("link 2 — records 8–14").

**Alternatives considered**: hard error above 50 (rejected — silent
refusal of normal-sized requests); URL-length-based chunking (rejected
— 50 ids ≈ 600 chars, far below URL limits; the id-count cap is the
binding constraint).

## R4 — Read-only tool: no plan, no gate, no session changes

**Decision**: One new **read** ToolDef, `playlist_links`
(`tools/playlist.py`), alongside `media_links`. Args: `record_refs`,
`use_last_listing` (same resolution semantics/`_resolve` as
`media_links` and `propose_moves`), `videos_per_record:
"all" | "first" = "all"` (FR-006). It returns links + labels + skips +
dedup notes in one payload. **No** `WritePlan`/`PlaylistPlan`, **no**
confirmation gate, **no** `AgentSession` changes, **no** CLI changes:
emitting a URL writes nothing anywhere; clicking it is the owner's
action in their browser.

**Rationale**: The two-phase gate exists to make unconfirmed *writes*
unreachable (agent-tools §4). This tool performs no write — gating it
would misstate its risk. It is exactly the `media_links` shape: a
snapshot-served read tool whose output the LLM narrates.

**Alternatives considered**: keeping a propose/confirm step anyway
(rejected — confirmation theater around a no-op teaches the user that
confirmations don't matter); making it part of `media_links` via a
flag (rejected — different output contract and chunking semantics;
separate tool keeps both payloads simple).

## R5 — Naming, saving, and link integrity

**Decision**: A temporary playlist has no name until saved on the
site, so the tool payload carries `suggested_name` (echoing the user's
requested name) and a fixed `save_hint` string; the system prompt
obliges the agent to relay the save-on-site guidance and **never**
claim it created/saved/named a playlist (FR-008). Ground rule 1
extends: play links come **only** from the `playlist_links` payload —
the LLM never assembles a YouTube URL from ids (FR-010; 019
`release_url` precedent). Ground rule 6 keeps account-side playlist
management and YouTube search in the unsupported list, now phrased to
offer the play-link capability instead.

**Rationale**: The honest-capability framing is what separates this
from the 018 class of incidents: the agent states exactly what it did
(built a link) and what it cannot do (save/name in the account).

## R6 — Deferred: OAuth account-write path (summary for the follow-up feature)

Preserved findings from the superseded scope, so the follow-up spec
does not re-research them:

- **Libraries**: `google-api-python-client` + `google-auth-oauthlib`
  (installed-app "Desktop app" flow), wrapped in a thin injectable
  client (the `DiscogsClient`/`ClientFactory` test-seam pattern).
- **Scope**: `https://www.googleapis.com/auth/youtube` (playlist
  writes). Consent screen in Testing mode with the owner as test user
  suffices for personal use.
- **Credentials**: client secret + refresh-token file, both
  settings-sourced paths defaulting under gitignored
  `collection-agent/data/`; disconnect = token deletion; connect flow
  belongs in CLI meta-commands (browser round-trip must not run inside
  an LLM tool round).
- **Quota**: 10,000 units/day default; `playlists.insert` and
  `playlistItems.insert` cost 50 each ⇒ ≈199 video inserts/day — under
  2 records/day short of exhausting a 26-record all-videos slice, so
  quota estimation + pre-confirmation warning + graceful
  `not_attempted` stop are mandatory design elements.
- **Gate**: account writes require the full two-phase
  propose/execute-after-y-N pattern (`execute_*` never a ToolDef), plus
  a single-pending-plan invariant across plan types.
