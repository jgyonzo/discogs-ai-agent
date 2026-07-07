# Feature Specification: YouTube Playlist Integration

**Feature Branch**: `020-youtube-playlist-integration`
**Created**: 2026-07-05
**Status**: Draft
**Input**: User description: "implement the youtube integration in collection agent that was deferred. The goal is to give the agent the hability to create playlists and insert records videos. A prompt example from the user could be 'find records from electronic genre and minimal style, show the record list and its assosiated youtube links' and in a following prompt 'create a youtube playlist called discogs-minimal and insert the links'"

**Scope revision (2026-07-06)**: re-scoped by owner decision from
account-write playlist creation (OAuth against the owner's YouTube
account) to **anonymous play links**: the agent emits a YouTube link
that starts playing the records' videos as a temporary playlist, which
the owner can then save (and name) on the YouTube site itself. No
account connection, no credentials, no writes. The account-write
(OAuth) path is deferred as a possible follow-up feature. The endpoint
behavior was verified live with snapshot video ids on 2026-07-06.

**Replay addendum (2026-07-06, T018 live replay)**: two findings from
the owner's first live run (a 47-record slice → 5 chunked links, all
structurally correct).
*Finding 1 — wrapped links break cmd+click*: the CLI hard-wrapped long
answers at terminal width, inserting real newlines inside play-link
URLs; terminal URL detection stops at a newline, so cmd+click opened a
playlist truncated to the first line's ids (exactly 17 at the owner's
terminal width) while copy-paste worked. Fixed in the CLI print path
(`soft_wrap` — no hard newlines in answers), which restores SC-001's
"opened in a browser plays exactly the stored videos" for click-through
as well as copy-paste.
*Finding 2 — creation phrasing*: the agent opened with "I've created
multiple YouTube playlists", brushing against FR-008 (nothing is
created in any account). Ground rule 6 tightened: results are presented
as play links, never as playlists the agent created.

**Replay addendum 2 (2026-07-06, second replay on a new OpenAI
account, same model id `gpt-4o-mini`)**: the deterministic layer held —
an SC-002 audit of the 3 emitted links found all 128 video ids present
verbatim in the snapshot, matching exactly the first stored video of
each of the 132 matched records (128 with videos, 4 without): zero
fabricated or altered ids across ~1,500 characters of transcribed URL.
The narration layer drifted on three counts, all fixed by prompt
tightening:
*Finding 3 — language flip*: an English question got a Spanish answer
(ground rule 4 violation; the prompt's bilingual alias examples likely
biased a small model). Rule 4 now keys explicitly to the user's most
recent message and disclaims prompt-internal Spanish as a signal.
*Finding 4 — unprompted sampler mode*: the model passed
`videos_per_record="first"` without the user asking (FR-006's default
is all videos). Rule 6 now forbids choosing `first` unprompted.
*Finding 5 — unrelayed skips*: the answer said "128 videos" without
mentioning the 4 skipped no-video records the payload reported
(FR-007). Rule 6 now requires reporting skip count and reasons.

**Replay addendum 3 (2026-07-06, third replay)**:
*Finding 6 — listing columns resist prompt steering*: despite the
answer-style rule, listings still rendered Format and Folder columns
(and could not show Country — it was absent from the payload), and
very long titles blew up table layout and token spend. Root cause: the
model renders whatever fields the listing entries carry; column
guidance in the prompt loses to payload shape. Fix (013→014 precedent,
deterministic over steering): `filter_records` entries slimmed to
artist/title/year/country/link; a new `include` arg adds attributes
only when the user asks; non-`eq` criteria auto-include their
attribute (varying values are informative, `eq` columns are not);
titles display-capped at 70 chars (configurable) with an ellipsis.
Contract delta 11. The bare-URL fix from finding 6's same replay
confirmed working.

**Replay addendum 4 (2026-07-06, fourth replay)**:
*Finding 7 — language flip recurred despite the finding-3 rule
tightening*: an English question again got a Spanish answer while
every payload-level fix held (lean columns, bare URLs, truncation).
Confirmed diagnosis: a standing-prompt rule cannot outweigh the ~30
Spanish attribute aliases the registry renders into the same prompt —
finding 3's fix was prompt steering applied to a prompt-steering
failure. Fix (018 decision-point precedent): the language-mirroring
instruction now rides as a transient system message appended as the
LAST message of every LLM request — after tool results, immediately
before the answer is written — and is never persisted to the session
transcript. Residual risk accepted: `gpt-4o-mini` remains stochastic;
the escalation path if drift persists is a stronger model via
`COLLECTION_AGENT_MODEL` (owner note: a newer mini-tier model such as
`gpt-5.4-mini` undercuts `gpt-4o` on price — prefer it; the model id is
pure VII(a) configuration, no code change).

**Replay addendum 5 (2026-07-06, fifth replay)**:
*Finding 8 — "all records" misread as "all attributes"*: the first
answer was correct (lean columns, truncation disclosed, bare URLs —
findings 6/7 fixes holding); the follow-up "show all of the records"
was answered with Format/Folder/Label columns — the model routed
"all" into the finding-6 `include` escape hatch instead of `limit`.
Fix at the argument-choice decision point: `include`'s schema
description now requires the user to NAME the attributes and
explicitly routes "all/more records" to `limit`; `limit`'s description
states it adds rows and never changes columns. If misrouting recurs,
it joins the model-escalation path of finding 7.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a playable playlist link from records in the conversation (Priority: P1)

The owner is chatting with the collection agent. They ask for a slice
of their collection — e.g. "find records from electronic genre and
minimal style, show the record list and its associated youtube links" —
and the agent answers with the record listing and each record's stored
video links (existing behavior). In a follow-up prompt they say "create
a youtube playlist called discogs-minimal and insert the links". The
agent resolves "the links" from the conversation and replies with a
**play link**: one click opens YouTube and starts playing those
records' videos in order as a temporary playlist. The agent explains
that saving is done on the YouTube site (the playlist panel's "Save
playlist" action) and suggests the requested name ("discogs-minimal")
for that save step, since a temporary playlist has no name until the
owner saves it. The answer also accounts for any records that
contributed no videos, with reasons.

**Why this priority**: This is the entire point of the feature — a
filtered slice of the collection becomes listenable in two
conversational prompts, with zero setup.

**Independent Test**: With a synced collection, run the two example
prompts end to end; click the returned link in a browser and verify
the videos that play are exactly the stored videos of the listed
records; verify the "Save playlist" action on the site persists it to
the owner's library.

**Acceptance Scenarios**:

1. **Given** a synced collection and a record listing with video links
   in the conversation, **When** the owner asks to create a playlist
   with those links, **Then** the agent replies with a play link built
   from exactly those records' stored videos, plus a note that saving
   and naming happen on the YouTube site.
2. **Given** the returned play link, **When** the owner opens it in a
   browser, **Then** the videos play in the order the records were
   listed, as a temporary playlist that can be saved to the owner's
   library from the site.
3. **Given** a follow-up prompt referencing "the links" with no prior
   record listing in the session, **When** the owner asks for a
   playlist, **Then** the agent asks which records to use instead of
   guessing.
4. **Given** records in the request that have no stored videos or
   whose stored links cannot be resolved to YouTube videos, **When**
   the link is built, **Then** those records are skipped — never
   substituted with guessed or searched-for videos — and each skip is
   reported with its reason.
5. **Given** any playlist answer, **When** the owner reads it, **Then**
   every link in it comes verbatim from the tool result — the agent
   never assembles a YouTube URL itself.

---

### User Story 2 - Large slices: multiple clearly-labeled links (Priority: P2)

The owner asks for a playlist over a large slice (many records, or
records with many videos each). A single play link can carry only a
limited number of videos (~50), so the agent returns **several links,
in listing order, each labeled with the records it covers** ("link 1 —
records 1–7 (50 videos)", "link 2 — records 8–14 (48 videos)", …).
Nothing is silently dropped: the set of links covers every usable video
of every requested record, and the answer says how many links, videos,
and records are involved.

**Why this priority**: The owner's collection slices routinely exceed
one link's capacity (video-bearing records average ~7.5 stored videos
each), so honest chunking is what makes the feature trustworthy at real
sizes — but the feature is already valuable for small slices without
it.

**Independent Test**: Request a playlist over a slice whose stored
videos exceed one link's capacity; verify every returned link plays,
the labels' record ranges are correct, the union of all links equals
the full usable-video set, and no link exceeds the capacity.

**Acceptance Scenarios**:

1. **Given** a record slice whose usable videos exceed one link's
   capacity, **When** the playlist is requested, **Then** the agent
   returns multiple links in listing order, each within capacity and
   labeled with the records and video count it covers.
2. **Given** a chunked answer, **When** the owner compares it to the
   original listing, **Then** every usable video of every listed record
   appears in exactly one link — no silent truncation, no overlap.
3. **Given** a slice that fits in one link, **When** the playlist is
   requested, **Then** exactly one link is returned (no gratuitous
   chunking).

---

### User Story 3 - One video per record (Priority: P3)

The owner wants a sampler rather than everything: "make it one track
per record". The agent builds the link(s) taking only the first stored
video of each record, so a 50-record slice fits in a single link
instead of ~8.

**Why this priority**: Convenience mode that makes large slices
practical as a single link; the default all-videos mode already covers
the core need.

**Independent Test**: Request the same slice with and without the
one-per-record instruction; verify the one-per-record link contains
exactly one video per video-bearing record (the first stored one) and
that skip reporting is unchanged.

**Acceptance Scenarios**:

1. **Given** a record slice and a one-per-record instruction, **When**
   the playlist is requested, **Then** each video-bearing record
   contributes exactly its first stored video, in listing order.
2. **Given** no explicit instruction, **When** the playlist is
   requested, **Then** all stored videos of each record are included
   (default mode).

---

### Edge Cases

- A stored video link cannot be resolved to a YouTube video (Discogs
  accepts only YouTube links in release videos, so in practice this
  means a malformed or unrecognized URI variant rather than another
  provider): the record is skipped for playlist purposes with a
  per-record reason; the link itself is still shown to the user as
  today. No guessing or searching for a substitute video.
- The same video appears under multiple records in one request (e.g.
  two pressings of the same release): it is included once — in the
  earliest record's position — and the answer notes the deduplication.
- Every requested record ends up skipped (no usable videos at all):
  the agent says so plainly and returns no link, rather than an empty
  or broken one.
- The owner asks to "save it as discogs-minimal": the agent explains
  it cannot name or save playlists in the owner's account — the save
  happens on the YouTube site — and repeats the suggested name. It
  never claims the playlist was saved.
- The play-link mechanism is an undocumented YouTube behavior: if
  YouTube retires it, links stop working in the browser. The agent's
  answers are unaffected structurally (links still come only from tool
  output); the mitigation path is the deferred account-write (OAuth)
  follow-up. Recorded as an accepted risk in Assumptions.
- A playlist request arrives while the snapshot is stale or partial:
  link building uses whatever the conversation's listing showed;
  staleness warnings continue to surface exactly as they do for
  read-only answers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The agent MUST be able to build one or more play links
  from a user-given set of records — resolved from explicit record
  references, name mentions, or the session's most recent record
  listing, with the same resolution behavior the existing media-links
  capability uses — such that opening a link in a browser plays those
  records' stored videos in listing order as a temporary playlist.
- **FR-002**: Only videos taken verbatim from a record's stored media
  links may ever appear in a play link. The agent MUST NOT construct,
  guess, or search for video identifiers from any other source; a
  record with no usable stored video is skipped, never substituted.
- **FR-003**: Records whose stored links are absent or cannot be
  resolved to a YouTube video MUST be skipped with a per-record reason
  visible in the answer.
- **FR-004**: Identical videos appearing more than once within one
  request MUST be included only once, with the deduplication noted.
- **FR-005**: When the usable videos exceed one link's capacity
  (a configurable cap, default 50 videos), the agent MUST return
  multiple links in listing order, each within capacity and labeled
  with the records and video count it covers. Silent truncation is
  forbidden: the links together MUST cover every usable video, and the
  answer MUST state the total link, video, and record counts.
- **FR-006**: The owner MUST be able to request one-video-per-record
  mode (first stored video of each record); the default is all stored
  videos per record.
- **FR-007**: Every playlist answer MUST account for 100% of the
  requested records — each either covered by a link or skipped with a
  reason.
- **FR-008**: The agent MUST present saving honestly: playlists are
  saved and named by the owner on the YouTube site; the agent suggests
  the requested name for that step and MUST never claim it created,
  saved, or named a playlist in the owner's account.
- **FR-009**: The feature MUST require no YouTube account connection,
  no credentials, and no configuration beyond what the agent already
  needs; it performs no writes to any external account and works
  against the existing local snapshot at conversational speed.
- **FR-010**: The agent MUST present play links only from tool output,
  extending the existing link-integrity ground rule: it never
  assembles a YouTube URL from video ids or any other identifier
  itself.

### Key Entities

- **Play link**: A tool-built YouTube URL carrying an ordered set of
  video identifiers (each parsed from a stored media link) that the
  site turns into a temporary, saveable playlist. Has a capacity limit;
  large requests produce an ordered, labeled series of them.
- **Playlist answer**: The agent's reply for a playlist request: the
  play link(s) with per-link labels (records covered, video count),
  skipped records with reasons, deduplication notes, and the
  save-on-site guidance with the suggested name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The two-prompt example journey (filter + show links, then
  "create a youtube playlist called X and insert the links") yields a
  link that, opened in a browser, plays exactly the stored videos of
  the listed records in order — verified live, including saving the
  playlist to the owner's library from the site.
- **SC-002**: Every video identifier in every emitted link traces back
  to a stored media link of a requested record — an audit of emitted
  links against the collection snapshot finds zero unexplained videos
  (and zero YouTube URLs in answers that did not come from tool
  output).
- **SC-003**: For any playlist request, the answer accounts for 100% of
  the requested records — covered by a link or skipped with a reason —
  including chunked multi-link answers, where links are disjoint and
  jointly complete over the usable videos.
- **SC-004**: The feature works with zero setup: a fresh clone with
  only the existing configuration (Discogs token, LLM key) can complete
  SC-001 without any Google/YouTube configuration step.
- **SC-005**: With the collection at the supported scale (300–1,000
  records), a playlist answer for a typical filtered slice (up to ~50
  records) is produced at conversational speed, without re-syncing the
  collection.

## Assumptions

- Single-owner, personal-use tool. Playing a link requires no login;
  saving the temporary playlist to a library requires the owner to be
  logged into YouTube in their browser — that step is theirs, outside
  the agent.
- The anonymous play-link mechanism is a long-standing but
  **undocumented** YouTube behavior (verified working with snapshot
  video ids on 2026-07-06). Its retirement is an accepted risk: the
  feature degrades to the existing per-video media links, and the
  mitigation is the deferred account-write (OAuth) follow-up feature.
- One play link carries at most ~50 videos; the cap is treated as
  configurable with default 50.
- Playlist videos come exclusively from the media links already stored
  in the local collection snapshot by the existing sync; this feature
  adds no new collection syncing and no video discovery/search. The
  deferred "v2 YouTube search" remains out of scope.
- All stored video links are expected to be YouTube: Discogs accepts
  only YouTube URLs in release videos, and the current snapshot
  confirms it (2,798 of 2,798 video links, checked 2026-07-05).
  Unresolvable-link handling (FR-003) is therefore a defensive guard
  against malformed or unrecognized URI variants, not an expected path.
- Creating, editing, or deleting playlists **in the owner's account**,
  and appending to existing saved playlists, are out of scope — they
  belong to the deferred OAuth follow-up.
- The existing conversation-session behavior (last-listing reference
  resolution, opaque per-record follow-up references) is reused as-is;
  this feature adds no new reference semantics.
