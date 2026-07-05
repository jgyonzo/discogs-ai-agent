# Feature Specification: Title-Aware Record Location (Postmortem)

**Feature Branch**: `018-title-locate-postmortem`
**Created**: 2026-07-05
**Status**: Draft
**Input**: User description: "Title-aware record location in the collection agent. Postmortem-style fix: users asking the collection agent to locate a specific record get false 'not in your collection' answers even though the record exists in the snapshot."

## Postmortem Context

On 2026-07-05 the collection owner asked the agent to locate four specific
records, all of which exist in the synced collection snapshot. Two of the
four were falsely reported as absent:

| Query (as typed) | Actual record in collection | Outcome |
|---|---|---|
| Guido Schneider - Focus On 2xLP | Guido Schneider – Focus On Guido Schneider (2006) | **False "couldn't locate"** — offered Styleways instead, "2 total matches, shown 1" |
| Troy Pierce - gone astral 2x12 | Troy Pierce – Gone Astray EP | **False "couldn't locate"** — offered 25 Bitches Vol. II instead, "4 total matches, shown 1" |
| Dj minx - A walk in the park | DJ Minx – A Walk In The Park EP (2004) | Found |
| Click box - Espaco tempo | Click Box – Espaço E Tempo (2008) | Found |

**Root cause (two compounding gaps, confirmed against the live snapshot):**

1. **The record title is not a filterable attribute.** The agent's declarative
   attribute registry — the single source of truth for what the record-listing
   capability can filter on — covers genre, style, year, decade, label,
   country, artist, format, folder, ratings, market stats, and scarcity, but
   not `title`. A "locate Artist – Title" question therefore degenerates into
   an artist-only listing, with the assistant left to spot the title by eye.
2. **The assistant truncates the listing before the target title is visible.**
   For locate-one-record questions the assistant requests a single-row
   listing (it expects exactly one record). The listing returns the first
   match in snapshot order plus a truncation note; the target record is
   hidden behind the truncation, and "not among the rows shown" is
   misreported as "not in your collection."

The two queries that "worked" were for artists with exactly one record in
the collection — truncation to one row hid nothing — which masked the bug.

**Follow-up (2026-07-05, replay after the first fix landed):** replaying
the incident queries in a live chat surfaced three residual gaps, all in
assistant behavior rather than the filter itself: (a) the assistant
sometimes uses exact title matching (`eq`) or the user's full noisy phrase
as the substring ("Espaco tempo" misses "Espaço **E** Tempo"), yielding
zero matches; (b) on zero matches it often skips the artist-only retry —
because the listing tool's own zero-match note ("no records matched — say
so explicitly; do not invent results"), written as an anti-hallucination
guard, overrides the standing retry instruction at exactly the decision
moment; (c) when it does retry and finds the record, it presents it as
"related" instead of affirming it is the requested record ("A Walk In The
Park EP" reported as *similar to* "A walk in the park"). FR-006 (e)–(f)
and FR-009 close these.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Locate a record by artist and title (Priority: P1)

The collection owner asks whether a specific record is in the collection,
naming it the way collectors do — "Artist - Title", possibly with format
noise ("2xLP", "2x12") and imprecise casing/diacritics ("Espaco" for
"Espaço"). The agent narrows the listing by artist **and** a title
substring, and answers from the actual matching records.

**Why this priority**: This is the failing journey from the incident. A
collection agent that denies owning records it has synced destroys trust in
every other answer it gives.

**Independent Test**: With a snapshot containing an artist with multiple
records, ask for one of them by artist + partial title. The agent must be
*able* to express the title criterion (attribute exists, substring matching,
accent/case-insensitive) and the record must be findable without listing
every record by that artist.

**Acceptance Scenarios**:

1. **Given** the registry-driven filter surface, **When** a criterion on
   attribute `title` with a substring operator is applied, **Then** records
   whose title contains the given text (case- and diacritic-insensitive)
   match, and all others do not.
2. **Given** an artist with several records in the snapshot, **When**
   criteria `artist = X` AND `title contains "focus on"` are combined,
   **Then** only that artist's records with matching titles are returned.
3. **Given** a title query with different accents than the stored title
   ("espaco" vs "Espaço"), **When** a substring criterion is applied,
   **Then** the record still matches.
4. **Given** the attribute documentation the assistant sees, **When** it is
   rendered, **Then** `title` appears in it automatically (declared once in
   the registry, never hand-written prose), with its Spanish aliases.

---

### User Story 2 - Presence checks never silently truncate (Priority: P2)

When the goal of a question is "do I own this record?", the assistant must
not restrict the listing to fewer rows than the matches, and must not treat
"not among the rows shown" as "absent". If a title criterion yields nothing
(typo, renamed edition), it retries by artist alone and inspects the full
(untruncated within the standard cap) listing before declaring the record
absent — and strips format qualifiers ("2xLP", "2x12") from the title text
before searching.

**Why this priority**: The title attribute (US1) makes correct behavior
*possible*; this guidance makes it the assistant's *default*. Without it the
assistant can still request a one-row listing and repeat the incident.

**Independent Test**: Inspect the assistant's standing instructions: they
must contain explicit locate-a-record guidance (filter by artist + title
substring, no small listing limits for presence checks, artist-only retry
before declaring absence, format-noise stripping). Behavioral spot-check via
the incident queries.

**Acceptance Scenarios**:

1. **Given** the assistant's standing instructions, **When** they are
   rendered, **Then** they include locate-a-record guidance covering: artist
   + title-substring filtering (substring, never exact; short distinctive
   substring), never limiting a presence-check listing below the standard
   cap, artist-only retry before declaring absence, stripping format noise
   from the queried title, and affirming near-matches as the requested
   record.
2. **Given** the incident queries ("Guido Schneider - Focus On 2xLP",
   "Troy Pierce - gone astral 2x12") against the incident snapshot,
   **When** asked again, **Then** the agent locates both records (the
   second via artist-only retry, since "astral" ≠ "astray").
3. **Given** a listing request with a title criterion that matches zero
   records, **When** the tool result is returned, **Then** its note tells
   the assistant to loosen the search before declaring absence (FR-009);
   **and Given** a zero-match listing with no text criterion, **Then** the
   plain "say so explicitly" note is returned unchanged.

---

### Edge Cases

- Title substring matches multiple records by the same artist (e.g. volumes
  I and II of a series): all matches are listed; the assistant presents
  them rather than picking one silently.
- Title criterion combined with no artist criterion (title-only search,
  e.g. "do I have anything called 'Versus'?"): works; substring matching
  applies across the whole collection.
- Exact-title match requested ("exactly titled X"): an exact operator is
  available alongside substring matching, compared case- and
  diacritic-insensitively.
- A record with an empty/missing title: never matches a title criterion
  (except nothing — there is no "missing" operator for text attributes),
  and never causes an error.
- The queried substring appears only in the artist name, not the title
  (e.g. `title contains "guido"` on "Focus On Guido Schneider" *does*
  match because the title itself contains it — but "Styleways" does not
  match even though the artist is Guido Schneider): title matching reads
  the title field only.
- Unsupported operator for text (e.g. numeric `between` on `title`): the
  criterion is reported as unsupported with the valid operators, never
  silently dropped (existing FR-013a behavior extends to the new
  attribute).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The record **title** MUST be a filterable attribute of the
  record-listing capability, declared in the attribute registry like every
  other attribute (single declaration; no bespoke tool code).
- **FR-002**: Title filtering MUST support substring matching (`contains`)
  and exact matching (`eq`), both case-insensitive and diacritic-insensitive
  (consistent with existing attribute-value folding).
- **FR-003**: The `title` attribute MUST be addressable bilingually (at
  minimum: `title`, `titles`, `título`, `titulo`), consistent with the
  bilingual aliasing of every existing attribute.
- **FR-004**: A title criterion MUST combine with any other supported
  criteria under the existing AND semantics (e.g. artist + title).
- **FR-005**: The `title` attribute MUST appear automatically in the
  assistant-facing attribute documentation rendered from the registry
  (Constitution Principle VII(b) analog — no hand-written attribute prose).
- **FR-006**: The assistant's standing instructions MUST include
  locate-a-specific-record guidance: (a) filter by artist AND a distinctive
  title substring; (b) strip format qualifiers (e.g. "2xLP", "2x12") from
  the queried title before searching; (c) never request a listing limit
  smaller than the standard cap when the question is whether a record is
  present; (d) if artist + title yields nothing, retry with artist only and
  inspect the listing before declaring the record absent; (e) use substring
  matching — never exact matching — for locating, with a **short**
  distinctive substring (a few words; not the user's full phrase, which may
  embed typos, missing connective words, or format noise); (f) a match that
  differs from the user's phrasing only by suffixes ("EP"), casing,
  accents, or extra words IS the requested record and MUST be affirmed as
  found — never presented as merely "related" or "similar".
- **FR-009**: When a record listing with at least one text-kind criterion
  (e.g. title) matches zero records, the listing tool's zero-match note
  MUST itself instruct the assistant to loosen the search (drop the text
  criterion or use a shorter substring) before telling the user the record
  is absent — while still forbidding invented results. The plain zero-match
  note remains for listings without text criteria. Rationale: the assistant
  demonstrably obeys in-result notes over standing instructions at the
  zero-match decision point; the note must push toward the retry, not away
  from it.
- **FR-007**: Records with a missing/empty title MUST simply not match any
  title criterion, without error.
- **FR-008**: All pre-existing behavior MUST be preserved: every existing
  attribute, operator, and test remains green; no live network calls are
  introduced in tests.

### Key Entities

- **Attribute registry entry (`title`)**: text-kind attribute; extracts the
  record's title; single-valued; supports `contains`/`eq`; bilingual
  aliases; one-line description rendered into the assistant's attribute
  block.
- **Locate-a-record guidance**: a short addition to the assistant's
  standing instructions describing the presence-check procedure
  (artist + title substring → no small limits → artist-only fallback).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four incident queries, replayed against the incident
  snapshot, locate their records: Focus On Guido Schneider, Gone Astray EP
  (via artist-only fallback), A Walk In The Park EP, Espaço E Tempo — zero
  false "not in your collection" answers.
- **SC-002**: A record by a multi-record artist is locatable by artist +
  title substring without the answer depending on snapshot ordering or on
  reading more than the matching rows.
- **SC-003**: Adding the title attribute required exactly one registry
  declaration plus its tests — no record-listing tool code changed
  (SC-003a of the agent-tools contract holds).
- **SC-004**: The full existing test suite (~106 tests) passes unchanged;
  new tests cover title matching (substring, exact, folding, missing title),
  the prompt guidance, and the retry-aware zero-match note (FR-009) —
  including that non-text zero-match listings keep the plain note.

## Assumptions

- Substring + artist-fallback guidance is sufficient for near-miss titles
  ("gone astral" vs "Gone Astray"); typo-tolerant/edit-distance matching is
  **out of scope**.
- The link-resolution capability's own fuzzy reference matching
  (`media_links`) is unaffected and **out of scope**.
- No new tools are introduced; the fix rides entirely on the existing
  registry-driven listing capability plus assistant instructions.
- Scale target unchanged (300–1k records); substring scans over the
  snapshot remain conversational-speed.
- The snapshot schema already carries the record title (it is displayed in
  every listing today); no sync/schema change is needed.
