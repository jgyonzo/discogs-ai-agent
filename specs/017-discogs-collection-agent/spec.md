# Feature Specification: Discogs Collection Agent

**Feature Branch**: `017-discogs-collection-agent`
**Created**: 2026-07-04
**Status**: Draft
**Input**: User description: "Quiero desarrollar un agente conversacional que se conecte con la API de Discogs y permita: analizar mi colección (géneros y proporción, top labels, discos por género y década, top rated, por país de origen, más raros/buscados, valor de la colección, más caros), mostrarme mis discos de un género, darme los links a música/video presentes en la metadata de Discogs, y mover discos a una carpeta (existente o nueva). Para una v2, usar la API de YouTube para armar playlists y buscar candidatos de video. Consulta docs/discogs_api_reference.md."

## Clarifications

### Session 2026-07-05

- Q: Where do users interact with this agent in v1 (existing web frontend, CLI chat, API-only, new UI)? → A: Terminal/CLI chat — an interactive conversational session in the terminal; no web-frontend work in this feature.
- Q: Must every answer reflect live Discogs data, or is a locally synced snapshot acceptable for analytics? → A: Local snapshot — the agent syncs the collection (showing progress), answers analytics instantly from the snapshot, discloses sync age, and re-syncs on demand. Account-modifying actions (US4) always execute live.
- Q: "Top rated" ranks by community rating, my own ratings, or both? → A: Community rating — rank by Discogs community average, with the vote count shown. Personal ratings remain available as a US2 filter attribute.
- Q: Do analytics count every copy (instance) or unique releases? → A: Instances — every copy counts; distribution totals reconcile exactly with the collection size Discogs reports.
- Q: Roughly how many records does the collection have? → A: ~300–1,000 records (may grow moderately). Sizing target for sync design: a full sync is a minutes-scale operation, not hours.

## User Scenarios & Testing *(mandatory)*

This feature adds a **conversational agent that works against a user's live
Discogs account**. The user asks questions and gives instructions in natural
language ("¿qué géneros tengo y en qué proporción?", "muéstrame mis discos de
techno de los 90", "mové estos a una carpeta nueva"), and the agent answers
with analytics over their personal collection or performs the requested
organizing action. This is distinct from the existing DuckDB-over-dumps agent:
the data source here is the **owner's collection on the live Discogs API**, not
the published ETL artifact.

### User Story 1 - Analyze my collection (Priority: P1)

As the owner of a Discogs collection, I want to ask the agent for aggregate
insights about my collection so I understand its shape without manually
browsing hundreds of records.

The agent can answer, over the full collection:

- Which **genres** I own and in what **proportion**.
- My **top labels** (by number of records).
- My **top-rated** records (by Discogs community average rating, vote count
  shown).
- Distribution by **country of origin** — count and percentage per country.
- My **rarest / most-wanted** records — those with a low community "have"
  count and a high "want" count, and/or those with **no copies or almost no copies currently for
  sale**.
- The **estimated value** of my collection.
- My **most expensive** records.

**Why this priority**: This is the core value proposition — turning a raw
collection into understandable insight. It is demonstrable on its own and is
the reason a user would adopt the agent. Every other story builds on the same
collection-reading foundation.

**Independent Test**: Connect a Discogs account that owns a non-empty
collection, ask each analytic question in turn, and confirm the agent returns a
correct, clearly-presented answer (proportions sum to 100%, counts match the
account's collection size, rankings are ordered correctly) grounded in that
account's actual data.

**Acceptance Scenarios**:

1. **Given** a connected account with a non-empty collection, **When** I ask
   "what genres do I have and in what proportion?", **Then** the agent returns
   each genre with a count and a percentage, and the percentages account for
   the whole collection (records with multiple genres and records with no
   genre are handled consistently and explained).
2. **Given** the same collection, **When** I ask for my top labels, **Then** the
   agent returns labels ranked by how many of my records they released, with
   counts.
3. **Given** the same collection, **When** I ask for my top-rated records,
   **Then** the agent returns records ranked by Discogs community average
   rating, showing each record's vote count so a high average on few votes is
   interpretable.
4. **Given** the same collection, **When** I ask for records by country of
   origin, **Then** the agent returns each country with a count and a
   percentage of the collection.
5. **Given** the same collection, **When** I ask for my rarest / most-wanted
   records, **Then** the agent returns records ranked by scarcity (low "have" /
   high "want", and/or zero or almost zero copies currently for sale) and
   explains the criterion used.
6. **Given** the same collection, **When** I ask for the value of my collection,
   **Then** the agent returns an estimated total value (with the valuation basis
   and currency stated).
7. **Given** the same collection, **When** I ask for my most expensive records,
   **Then** the agent returns records ranked by estimated per-record value.
8. **Given** an empty or fully-private collection, **When** I ask any analytic
   question, **Then** the agent explains it cannot read collection data and why,
   rather than returning an empty or misleading result.

---

### User Story 2 - Browse and filter my records (Priority: P2)

As a collector, I want to ask the agent to list the specific records in my
collection that match a filter — on any attribute the collection data carries —
so I can see the actual titles rather than only aggregate statistics.

Filtering is a **general capability over record attributes**, not a fixed menu.
Any attribute the analytics can see is also a filter dimension: genre, style,
decade/year, label, country of origin, artist, format, rating, scarcity
signals, and so on — alone or combined ("mis discos de house de los 90", "los
japoneses en vinilo", "los de 4AD que no tengan rating"). Adding a new
filterable attribute later must be an incremental extension, not a redesign.

Two filters are the **guaranteed launch set** and acceptance-tested explicitly:

- By **genre** ("muéstrame mis discos de jazz").
- By **genre and decade** ("mis discos de house de los 90").

**Why this priority**: Complements P1 by moving from "how much / how many" to
"which ones". Useful on its own once collection reading works, but the aggregate
insight is the headline capability, so this is P2.

**Independent Test**: Ask for records of a known genre (and a genre+decade
combination) and confirm the returned list contains only matching records from
the collection, each identified well enough to recognize (artist, title, year),
with a total count. Then ask for at least one filter on a different attribute
(e.g. label or country) and confirm the same contract holds.

**Acceptance Scenarios**:

1. **Given** a connected collection, **When** I ask to see my records of a given
   genre, **Then** the agent returns the matching records with enough identity
   (artist, title, year) to recognize each, plus a count.
2. **Given** a connected collection, **When** I ask for a genre within a decade,
   **Then** the agent returns only records whose genre and release decade both
   match.
3. **Given** a connected collection, **When** I filter by another available
   attribute (e.g. label, country, format) or combine several attributes,
   **Then** the agent applies the same list contract (matching records +
   identity + count) to that filter.
4. **Given** a filter on an attribute the agent cannot evaluate, **When** I ask,
   **Then** the agent says which part of the filter it cannot apply instead of
   silently ignoring it.
5. **Given** a filter that matches nothing, **When** I ask, **Then** the agent
   states clearly that no records matched, without inventing results.

---

### User Story 3 - Get media links from Discogs metadata (Priority: P2)

As a collector, I want the agent to give me the music/video links that Discogs
already stores in a record's metadata, for a single record or for a list of
records, so I can listen to or watch them without opening Discogs.

**Why this priority**: A high-delight, self-contained capability that reuses the
same record-reading foundation. Independent of organizing actions, and a natural
lead-in to the future YouTube integration.

**Independent Test**: Ask for the media links of a specific record known to have
videos in Discogs, and for a small list of records, and confirm the agent
returns the links present in the Discogs metadata (and clearly says when a
record has none).

**Acceptance Scenarios**:

1. **Given** a record that has video/music links in its Discogs metadata, **When**
   I ask for that record's links, **Then** the agent returns each link (with its
   title/description where available).
2. **Given** a list of records (e.g. "the jazz ones from story 2"), **When** I ask
   for their links, **Then** the agent returns the links grouped per record.
3. **Given** a record with no media links in its metadata, **When** I ask, **Then**
   the agent states that the record has no linked media rather than returning an
   empty answer with no explanation.

---

### User Story 4 - Organize records into folders (Priority: P3)

As a collector, I want to tell the agent to move one or more records into a
folder — an existing one, or a new folder it creates for me — so I can organize
my collection conversationally.

**Why this priority**: The only write action in scope; it mutates the user's
Discogs account, so it depends on the reading stories being solid first and
carries the most risk. Valuable but not required for the analytic MVP.

**Independent Test**: Ask the agent to move a specific record to an existing
folder and confirm the record appears there on Discogs; ask it to move records
to a new folder by name and confirm the folder is created and populated.

**Acceptance Scenarios**:

1. **Given** a record in my collection and an existing target folder, **When** I
   ask the agent to move it there, **Then** after confirmation the record is in
   the target folder and no longer counted in its previous folder.
2. **Given** a record and a folder name that does not yet exist, **When** I ask
   the agent to move it to that folder, **Then** the agent creates the folder and
   places the record in it.
3. **Given** a move instruction, **When** the agent is about to change my account,
   **Then** it summarizes what it will do (which records, which folder, create-new
   or use-existing) and proceeds only after I confirm.
4. **Given** a move that cannot complete (record not found, permission denied,
   name collides with an existing folder), **When** I ask, **Then** the agent
   reports what failed and leaves the collection unchanged for the failed items.

---

### Edge Cases

- **Empty / private collection**: agent must explain it cannot read the data
  rather than returning zeros as if the collection were empty.
- **Records missing attributes**: a record may have no genre, no country, no
  release year, no rating, or no marketplace data. Aggregations must handle and
  explicitly account for these (e.g. an "unknown country" bucket) instead of
  silently dropping them or crashing.
- **Multi-valued attributes**: a record can have multiple genres/styles and
  multiple labels. The agent must state how it counts these (per-record vs.
  per-genre) so percentages are interpretable.
- **Multiple instances of the same release**: the same release can appear more
  than once in a collection and across folders. Analytics count **instances**
  (every copy counts — clarified 2026-07-05), so totals reconcile with the
  collection size Discogs reports. Moves operate on a specific instance, and
  the agent states which one when ambiguity exists.
- **Large collections + rate limits**: syncing a big collection requires many
  API calls. The sync must stay within Discogs rate limits, show progress,
  survive interruption without corrupting the snapshot (resumable or cleanly
  restartable), and never leave a partial snapshot masquerading as a complete
  one.
- **Stale snapshot vs. live actions**: a move/folder action can target a record
  whose snapshot state no longer matches Discogs (e.g. moved or removed on the
  website since the last sync). Live actions must validate against Discogs at
  execution time and report the discrepancy, not act blindly on snapshot state.
- **Rarity with no market data**: "no copies for sale" and "low have / high
  want" must be distinguished; a record with missing community stats must not be
  falsely reported as rare.
- **Value / currency**: valuation must state its basis and currency; the agent
  must not present an estimate as an exact appraisal.
- **Ambiguous filters**: an unrecognized or ambiguous genre/decade should prompt
  a clarification or a best-effort match the agent names, not a silent empty
  result.
- **Destructive/irreversible intent**: any account-modifying action requires
  explicit user confirmation before execution.

## Requirements *(mandatory)*

### Functional Requirements

**Connection & identity**

- **FR-001**: The system MUST connect to a single Discogs account (the
  collection owner) using that account's credentials and read that account's
  collection on their behalf.
- **FR-002**: The system MUST keep the account credentials secret (never
  displayed, logged in the clear, or committed to the repository).
- **FR-003**: The system MUST identify itself to Discogs as required by
  Discogs' usage rules and stay within Discogs' request-rate limits, degrading
  gracefully (informing the user) rather than failing hard when limits are
  approached.

**Collection snapshot & sync**

- **FR-003a**: The system MUST be able to **sync the account's collection into a
  local snapshot** (all records with the attributes the analytics need), showing
  progress during the sync and staying within Discogs rate limits.
- **FR-003b**: Analytics, browsing, and media-link answers MUST be served from
  the snapshot at conversational speed; the system MUST be able to disclose the
  snapshot's sync age and MUST re-sync when the user asks.
- **FR-003c**: An interrupted or failed sync MUST NOT produce a snapshot that is
  presented as complete; the system MUST either resume, cleanly restart, or
  clearly report the snapshot as partial.
- **FR-003d**: Account-modifying actions (US4) MUST execute live against Discogs
  — never against the snapshot — and MUST validate the target's current state at
  execution time; after a successful write, the snapshot MUST be updated or
  marked stale.

**Collection analytics (US1)**

- **FR-004**: Users MUST be able to ask, in natural language, for the
  distribution of their collection by **genre**, returned as counts and
  percentages, with the counting rule for multi-genre records made explicit.
- **FR-005**: Users MUST be able to ask for their **top labels**, ranked by the
  number of records in the collection released by each label.
- **FR-006**: Users MUST be able to ask for their **top-rated** records, ranked
  by the Discogs **community average rating**, with each record's vote count
  shown (a high average on very few votes must be interpretable). The owner's
  own ratings are not the ranking basis; they remain available as a filter
  attribute (US2).
- **FR-007**: Users MUST be able to ask for the distribution of their collection
  by **country of origin**, returned as counts and percentages per country,
  including an explicit bucket for records with unknown country.
- **FR-008**: Users MUST be able to ask for their **rarest / most-wanted**
  records, using scarcity signals (low community "have", high community "want",
  and/or zero or almost zero copies currently for sale), with the criterion used
  stated in the answer.
- **FR-009**: Users MUST be able to ask for the **estimated total value** of
  their collection, with the valuation basis and currency stated.
- **FR-010**: Users MUST be able to ask for their **most expensive** records,
  ranked by estimated per-record value, with the valuation basis stated.

**Browse & filter (US2)**

- **FR-011**: Users MUST be able to ask for a **filtered list of their records**,
  returning each matching record with enough identity to recognize it (at least
  artist, title, and year) plus a total count. **Genre** filtering MUST be
  supported at launch.
- **FR-012**: Filters MUST be **combinable** — multiple attributes in one
  request narrow the result (logical AND). The **genre + decade** combination
  MUST be supported at launch.
- **FR-013**: Filtering MUST be **extensible by design**: it operates over the
  record attributes the system already reads (including at minimum genre,
  style, decade/year, label, country, artist, format, and rating), and adding a
  new filterable attribute MUST NOT require redesigning the filtering
  capability — only declaring the new attribute.
- **FR-013a**: When a request filters on an attribute the system cannot
  evaluate, the system MUST identify the unsupported part of the filter rather
  than silently ignoring it or fabricating a result.
- **FR-013b**: When a filter matches no records, the system MUST say so
  explicitly rather than returning an empty or fabricated result.

**Media links (US3)**

- **FR-014**: Users MUST be able to ask for the **music/video links present in a
  record's Discogs metadata**, for a single record.
- **FR-015**: Users MUST be able to ask for the media links of a **list of
  records** and receive the links grouped per record.
- **FR-016**: When a record has no media links in its metadata, the system MUST
  state that explicitly for that record.

**Organize (US4)**

- **FR-017**: Users MUST be able to instruct the system to **move one or more
  records to an existing folder** in their collection.
- **FR-018**: Users MUST be able to instruct the system to **move records to a
  new folder**, which the system creates by the requested name.
- **FR-019**: Before performing any account-modifying action, the system MUST
  present a summary of the intended change and require explicit user
  confirmation.
- **FR-020**: When an organizing action partially or fully fails, the system MUST
  report which items failed and why, and MUST NOT leave the collection in a
  state the user was not told about.

**Conversational behavior & integrity**

- **FR-021**: The system MUST accept requests in natural language (the user
  writes in Spanish and/or English) and respond conversationally.
- **FR-022**: Every analytic answer MUST be grounded in the connected account's
  actual collection data; the system MUST NOT fabricate records, counts, values,
  or links.
- **FR-023**: When data needed to answer is missing, restricted, or ambiguous,
  the system MUST explain the limitation rather than guess silently.
- **FR-024**: The system MUST present percentages that are internally consistent
  (each distribution's parts reconcile to the stated whole) and rankings in the
  correct order.
- **FR-025**: Analytics MUST count **collection instances** (every owned copy
  counts, including duplicates of the same release), so distribution totals
  reconcile exactly with the collection size reported by Discogs.

### Key Entities *(include if feature involves data)*

- **Collection**: the owner's set of records on Discogs; has a size (number of
  records) and is organized into folders. The unit of analysis for US1/US2.
- **Folder**: a named subdivision of the collection; records live in folders and
  can be moved between them; folders can be created. Central to US4.
- **Collection Item (instance)**: a specific occurrence of a release in the
  collection, in a folder, optionally carrying the owner's own rating and notes.
- **Release**: the record's catalog entry, carrying the attributes the analytics
  use — genres, styles, labels, country of origin, release year/decade,
  community rating, community "have"/"want" counts, marketplace availability
  (copies for sale, price signal), and media links (videos).
- **Media Link**: a music/video URL stored in a release's Discogs metadata, with
  an optional title/description.
- **Collection Value**: an estimated monetary valuation of the collection (and,
  derived, of individual records), expressed with a basis and a currency.
- **Collection Snapshot**: the locally synced copy of the collection that
  analytics/browse/link answers are served from; carries a sync timestamp
  (age), a completeness state (complete / partial / stale), and is refreshed on
  demand.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a connected non-empty collection, a user can obtain each of the
  seven US1 analyses (genre proportions, top labels, top rated, by country,
  rarest/most-wanted, collection value, most expensive) through natural-language
  requests, with no manual browsing of Discogs required.
- **SC-002**: Aggregate counts reconcile with the account's real collection: the
  total across any single distribution equals the collection size the account
  reports (100% of records accounted for, including explicit "unknown" buckets).
- **SC-003**: For genre and genre+decade filters — and for at least one filter
  on a different attribute (e.g. label or country) — at least 95% of returned
  records actually match the requested filter (no false inclusions), verified
  against a known sample collection.
- **SC-003a**: A new filterable attribute can be added without reworking the
  existing filters: previously passing filter requests still pass unchanged
  after the addition.
- **SC-004**: For a record that has media links in Discogs, the agent returns
  every link present in that record's metadata, and correctly reports "no links"
  for records that have none — with zero fabricated links.
- **SC-005**: A user can move a record to an existing folder and to a
  newly-created folder entirely through conversation, and the change is visible
  in the account afterward; every account-modifying action is preceded by a
  confirmation step.
- **SC-006**: The collection sync completes for the target scale (~300–1,000
  records) in minutes — roughly bounded by Discogs' ~60 requests/minute limit
  (≈1,000 records ≲ 20 minutes worst case) — without exceeding rate limits and
  showing progress while it runs; once synced, analytic answers arrive at
  conversational speed (seconds, not minutes). A partial or stale snapshot is
  never presented as complete/current — answers can disclose the sync age.
- **SC-007**: In a review of answers over a known sample collection, the agent
  produces no fabricated records, counts, values, or links (100% grounded), and
  states the basis/criterion for value and rarity answers every time.

## Assumptions

- **Single owner, not multi-tenant**: "mi colección" is read as a personal tool
  for one collection owner. The agent operates on one account's credentials at a
  time; a multi-user, log-in-on-behalf-of-others service is **out of scope** for
  this version. (This is the reasonable default given the wording; it can be
  revisited if multi-user is later required.)
- **Credentials via the project's existing secret mechanism**: the account's
  Discogs credentials are supplied through the repo's standard secret handling
  (e.g. `.env` locally), consistent with the constitution's Secrets rules — not
  hardcoded or committed.
- **Live Discogs API is the data source**: this feature reads the owner's live
  collection and release metadata directly from the Discogs API described in
  `docs/discogs_api_reference.md`. It does **not** use, and is independent of, the
  published DuckDB artifact produced by the ETL component.
- **"Genre" defaults to Discogs genres**: analytics group by Discogs' `genre`
  field by default; the finer `style` field is a secondary refinement the agent
  may offer but the headline grouping is genre. Multi-genre records are counted
  per-record-per-genre unless the user asks otherwise, and the agent states this.
- **"Decade" is derived from release year**: a record's decade comes from its
  release year (e.g. 1994 → "the 90s"); records without a year fall into an
  explicit "unknown decade" bucket.
- **Collection scale ≈ 300–1,000 records** (clarified 2026-07-05): sync design,
  progress reporting, and success criteria are sized for this range — a full
  sync completes in minutes under Discogs rate limits. Larger collections
  should degrade gracefully (longer sync, same guarantees), but are not the
  design target.
- **Filtering is attribute-driven, not menu-driven**: genre and genre+decade
  are the acceptance-tested launch filters, but the filtering capability is
  defined over whatever record attributes the system reads (style, label,
  country, artist, format, rating, scarcity, …). New attributes become
  filterable by declaration, without redesigning the capability.
- **Value/rarity are estimates from Discogs signals**: collection value uses
  Discogs' own valuation for the collection; per-record "most expensive" and
  "rarity" are derived from Discogs marketplace and community signals (price
  suggestion / lowest listed price, and have/want/for-sale counts). All such
  figures are presented as estimates with their basis and currency, never as a
  guaranteed appraisal.
- **Confirmation before any write**: account-modifying actions (moving records,
  creating folders) always require explicit user confirmation; there is no
  silent or bulk-destructive mode.
- **v1 surface = terminal/CLI chat** (clarified 2026-07-05): the agent runs as an
  interactive conversational session in the terminal. No web-frontend work is in
  scope for this feature; the existing React frontend remains coupled to the
  DuckDB agent only. A web surface for this agent, if desired, is a future
  feature.
- **Snapshot-based analytics** (clarified 2026-07-05): the agent reads the
  collection into a **local snapshot** (a sync that may take minutes for large
  collections, with visible progress), and answers analytics/browse/link
  questions instantly from that snapshot. Every snapshot-based answer can
  disclose the sync age, and the user can request a re-sync at any time
  ("refresh"). Account-modifying actions (US4 moves/folder creation) always
  execute **live** against Discogs, never against the snapshot; after a
  successful write the snapshot is updated or marked stale. The sync itself
  respects Discogs rate limits.

## Out of Scope (Future / v2)

The following were requested explicitly **for a later version** and are **not**
part of this feature:

- **YouTube integration** — using the YouTube API to (a) build a YouTube
  playlist from the videos already associated with a set of Discogs records, and
  (b) search YouTube for candidate videos for a record's tracks that have no
  video linked in Discogs. Captured here so it is not lost, to be specified as
  its own feature when v1 lands.

Also out of scope for this version: multi-user / act-on-behalf-of-others
accounts; editing release metadata on Discogs; marketplace buying/selling
actions; any use of the published DuckDB ETL artifact.
