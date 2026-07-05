# Feature Specification: Listing Link Integrity

**Feature Branch**: `019-listing-link-integrity`
**Created**: 2026-07-05
**Status**: Draft
**Input**: User description: "Fix the collection-agent's invented-Discogs-URL failure mode (019 candidate documented in CLAUDE.md after the 018 postmortem). During 018 replays, the LLM fabricated Discogs URLs from listing instance_ids — e.g. discogs.com/release/<instance_id> — but instance_id is a collection-instance identifier, not a release id, so these links are wrong or point at unrelated releases. This violates system-prompt ground rule 1: links may only come from media_links. Fix direction per the documented follow-up: make the listing payload's id non-linkable-looking and/or carry a real tool-provided URL in the listing payload so the LLM never needs to construct one. Scope is collection-agent only."

## Problem Statement

During the 018 postmortem replays, the collection agent's assistant fabricated
Discogs web links by pasting a record's internal collection-instance identifier
into a release-page URL pattern (`discogs.com/release/<instance_id>`). The
instance identifier lives in a different id space than release identifiers, so
these links are wrong: they 404 or — worse — resolve to a completely unrelated
release, silently misinforming the user. This violates the agent's standing
ground rule 1 ("every link in your answers comes from a tool result"), but the
ground rule alone has proven insufficient at the decision point: when the user
asks for a link (or the assistant decorates a listing with one), the only
URL-shaped material in reach is the internal id, and the assistant improvises.

Consistent with the 013→014 and 018 precedent (prompt steering → deterministic
enforcement), the fix removes the need to improvise: every record the agent
lists carries a genuine, tool-provided link to its Discogs release page, and
the internal identifier is presented so that it no longer invites URL
construction.

Scope is the `collection-agent/` component only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask for a record's Discogs page (Priority: P1)

The collection owner asks for the Discogs link to a record in their collection
("give me the Discogs link for Focus On Guido Schneider", "pásame el link de
ese disco"). The assistant answers with a real link that opens the correct
release page on Discogs — never a constructed or guessed URL.

**Why this priority**: This is the exact failure observed in the 018 replays.
A wrong link that resolves to an unrelated release is a silent wrong answer —
the most damaging failure class in this project's postmortem history.

**Independent Test**: Ask for the Discogs page of any synced record and follow
the returned link; it must land on the release page for that record. Can be
fully tested with the existing snapshot, no writes.

**Acceptance Scenarios**:

1. **Given** a synced collection, **When** the user asks for the Discogs link
   to a record that is in the collection, **Then** the assistant provides a
   release-page link that came verbatim from a tool result and resolves to
   that record's release.
2. **Given** a synced collection, **When** the user asks for the link to a
   record and then follows up "and the link for the second one?" after a
   listing, **Then** the follow-up link also comes verbatim from tool output
   and matches the referenced record.
3. **Given** a record whose enrichment has not completed, **When** the user
   asks for its Discogs link, **Then** the assistant still provides the
   correct release-page link (release identity is known from the initial sync
   pass, not enrichment).

---

### User Story 2 - Listings never carry invented links (Priority: P2)

The collection owner browses their collection through filters and rankings
("my house records from the 90s", "top 10 rated"). Whether or not they ask
for links, any link the assistant includes in those answers is genuine tool
output; internal record identifiers are never dressed up as URLs.

**Why this priority**: The 018 replays showed the assistant volunteering
fabricated links in listing answers even when not asked. Preventing invented
links in every listing shape (including zero-match fallback listings) closes
the failure class, not just the direct-question case.

**Independent Test**: Replay the 018 conversation transcripts that produced
invented URLs; scan the assistant's answers for any `discogs.com` URL not
present verbatim in a tool result of that run.

**Acceptance Scenarios**:

1. **Given** any filtered listing, ranking, or zero-match fallback listing,
   **When** the assistant presents the records, **Then** every Discogs URL in
   the answer appears verbatim in a tool result from the same conversation.
2. **Given** a listing answer, **When** the assistant refers to a record's
   internal identifier (e.g. for a later move), **Then** the identifier is
   presented as an opaque reference, not as part of a URL.

---

### User Story 3 - Media links remain the source for music/video links (Priority: P3)

The collection owner asks to "hear" a record or get its music/video links.
The media-links surface continues to serve those verbatim, and the new
release-page link does not get conflated with playable media links.

**Why this priority**: Regression guard. 017 established media links as
verbatim URIs; the new release-page link must not degrade that answer shape
(e.g. the assistant answering a "play it" request with a release page).

**Independent Test**: Ask for a record's music links; the answer serves the
stored media URIs, and a record with no media still gets the explicit
"no linked media" statement — while its release page link remains available
when asked for the record's Discogs page.

**Acceptance Scenarios**:

1. **Given** a record with stored media links, **When** the user asks for its
   music/video links, **Then** the assistant serves the stored URIs verbatim,
   as today.
2. **Given** a record with no stored media links, **When** the user asks to
   hear it, **Then** the assistant states Discogs has no linked media for it
   and MAY offer the release page link as the record's Discogs reference —
   clearly labeled as the release page, not playable media.

### Edge Cases

- Multiple copies (instances) of the same release in the collection: each
  copy carries the same release-page link; the assistant must still
  distinguish copies by their opaque instance reference when moving/counting.
- The user asks for the Discogs link of a record that is NOT in the
  collection: the assistant must say it is not in the collection (per 018's
  locate ladder) and must not fabricate a link for it.
- Zero-match fallback listings (018 FR-011) are listings too: fallback
  records must carry the same genuine link so a follow-up "give me its link"
  after an affirmed near-miss works without invention.
- A record synced before this feature ships (older snapshot on disk): the
  link material must be derivable from data every existing snapshot already
  holds, or the payload must degrade explicitly (no silent missing links).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every per-record entry in any record listing the agent's tools
  return to the assistant (filtered listings, zero-match fallback listings,
  ranking listings, media-link groupings) MUST include a genuine link to that
  record's Discogs release page, produced by the tool from the record's
  release identity — never by the assistant.
- **FR-002**: The release-page link MUST be derived from the release
  identifier captured during the initial collection sync pass, so it is
  present for every record in every snapshot state (complete, partial, or
  pre-enrichment) without requiring re-sync or additional remote calls.
- **FR-003**: Internal collection-instance identifiers MUST remain available
  in listing payloads for follow-up references (moves, "their links", "the
  second one") with unchanged behavior, and MUST be presented in a form that
  does not read as URL material.
- **FR-004**: The assistant's standing guidance MUST state that a record's
  Discogs page link comes from the listing payload's link field and
  music/video links come from the media-links surface, and MUST forbid
  constructing URLs from any identifier.
- **FR-005**: The media-links answer shape (verbatim URIs, explicit
  per-record "no linked media" flag) MUST be preserved unchanged; the
  release-page link MUST NOT be presented as playable media.
- **FR-006**: When replaying the 018 transcripts that produced invented URLs,
  every Discogs URL in the assistant's answers MUST appear verbatim in a tool
  result of the same run.

### Key Entities

- **Record listing entry**: the per-record unit a tool returns for display —
  identity (artist, title, year), an opaque instance reference for
  follow-ups, and (new) the genuine Discogs release-page link.
- **Release-page link**: the canonical Discogs web page for the release a
  collection instance belongs to; shared by all copies of the same release;
  distinct from media links.
- **Media link**: a music/video URI stored verbatim in the record's Discogs
  metadata (unchanged by this feature).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a replay of the 018 sessions that produced invented URLs,
  the number of Discogs URLs in assistant answers that are absent from that
  run's tool results is zero.
- **SC-002**: For 100% of records in a synced collection — including
  un-enriched records and records in zero-match fallback listings — asking
  for the record's Discogs page yields a link that resolves to the correct
  release.
- **SC-003**: Media-link answers are unchanged: existing media-links tests
  and answer shapes pass without modification to their expectations (verbatim
  URIs, explicit no-media flag).
- **SC-004**: Follow-up references that rely on the internal instance
  identifier (move proposals, "their links", ordinal references into the last
  listing) keep working with no behavior change.

## Assumptions

- The canonical Discogs release-page URL is deterministically derivable from
  the release identifier alone; a tool constructing it from the correct id
  space satisfies ground rule 1 (the rule targets assistant-side invention,
  not deterministic tool output). Precedent: the offline matcher already
  exports exactly this URL shape.
- Release identifiers are captured in the initial sync pass for every record,
  so no snapshot schema migration, re-sync, or extra Discogs API calls are
  needed; existing snapshots on disk already contain the required data.
- Fuzzy title matching and other 018-deferred items remain out of scope; this
  feature only closes the invented-URL follow-up (the "019 candidate"
  documented after 018).
- Verifying that links resolve on the live Discogs site is a manual/one-off
  quickstart check; automated tests assert link presence, id-space
  correctness, and verbatim-from-tool-output behavior, without live network
  calls.
