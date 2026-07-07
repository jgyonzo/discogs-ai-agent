# Feature Specification: Phone Record Scan — Load Physical Records into the Discogs Collection

**Feature Branch**: `022-phone-record-scan`
**Created**: 2026-07-07
**Status**: Draft
**Input**: User description: "As a large collection record owner I want to be able to scan my physical records with my phone to load them into my Discogs account. Reference product: Label Mate (https://yeahdef.github.io/label-mate-site/) — identification + add-to-collection, not playback/printing/BPM."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan one record and add it to the collection (Priority: P1)

The owner stands at their record shelves with their phone. They open the scan
page (served from the laptop over the home network), photograph a record —
the sleeve cover, the center label, or the barcode — and within a few seconds
see a short ranked list of matching Discogs releases, each with a cover
thumbnail, artist, title, year, country, format, label, and catalog number.
They tap the pressing that matches the record in their hand, confirm, and the
release is added to their Discogs collection. The page immediately returns to
the camera so they can scan the next record.

**Why this priority**: This is the entire point of the feature — the
photograph → identify → confirm → add loop. Everything else supports it.

**Independent Test**: With identification and search providers stubbed, a
photo upload produces ranked candidates; selecting a candidate and confirming
produces exactly one add-to-collection call for the confirmed release id, and
the UI returns to the ready-to-scan state.

**Acceptance Scenarios**:

1. **Given** the scan page is open on a phone, **When** the owner photographs
   a record sleeve with a legible artist and title, **Then** the system shows
   a ranked list of matching releases with cover thumbnail, artist, title,
   year, country, format, label, and catalog number, each taken verbatim from
   the release database.
2. **Given** a candidate list is shown, **When** the owner taps a candidate
   and confirms the add, **Then** exactly that release is added to the
   configured collection folder and the result (success, with the added
   release named) is shown.
3. **Given** a successful add, **When** the confirmation is displayed,
   **Then** the page returns to the camera-ready state without any further
   navigation so the next record can be scanned immediately.
4. **Given** a candidate list is shown, **When** the owner taps "none of
   these" (or dismisses the list), **Then** nothing is written to the
   collection and the owner is offered a manual text search.
5. **Given** the photo shows a barcode with legible digits, **When**
   identification runs, **Then** barcode evidence takes precedence over
   text evidence in producing candidates (the barcode-matched pressing is
   ranked first when found).

---

### User Story 2 - Duplicate awareness before adding (Priority: P2)

The owner scans a record they may already have cataloged. Before they
confirm the add, each candidate already present in their collection is
clearly marked ("already in your collection — N copies"). Adding a genuine
duplicate is allowed (collectors own multiple copies), but it requires a
distinct second confirmation so it can never happen by a mis-tap.

**Why this priority**: A large-collection owner scanning shelf-by-shelf will
inevitably re-scan records already cataloged. Silent duplicates corrupt the
collection; hard-blocking duplicates would be wrong too, because owning two
copies is real. Marking + double confirmation is the middle path.

**Independent Test**: With a local snapshot fixture containing release X,
scanning a record that resolves to X shows the duplicate marker with the
copy count; the add flow for X demands a second, explicit confirmation and
only then issues the write.

**Acceptance Scenarios**:

1. **Given** a candidate release that already exists in the local collection
   snapshot, **When** candidates are displayed, **Then** that candidate
   carries a visible "already in your collection — N copies" marker with the
   correct instance count.
2. **Given** a duplicate-marked candidate, **When** the owner taps it,
   **Then** the system asks for an explicit extra confirmation ("add another
   copy?") and only writes after that second confirmation.
3. **Given** a candidate not in the snapshot, **When** the owner taps it,
   **Then** only the normal single confirmation is required.
4. **Given** a successful add, **When** the local snapshot is next consulted
   (by this feature or the conversational agent), **Then** it either includes
   the newly added record or is explicitly marked stale — it never silently
   contradicts the live collection.

---

### User Story 3 - Batch scanning session with a reviewable log (Priority: P2)

The owner works through a crate of records in one sitting. Every scan
outcome — identified & added, identified & skipped, no match found, failed —
accumulates in a session log visible on the page (most recent first). The log
is also persisted on the laptop so that an interrupted or finished session
can be reviewed afterwards: which records were added, which were skipped,
which need another attempt.

**Why this priority**: The owner has a *large* collection; the feature's real
value is cataloging dozens of records in one session. Without a reviewable
trail, any interruption loses track of where the session stopped.

**Independent Test**: Perform several stubbed scan cycles with mixed outcomes;
the on-page log lists each outcome in order, and the persisted journal on
disk contains one entry per outcome with timestamp, outcome type, and the
release identity when one was involved.

**Acceptance Scenarios**:

1. **Given** several completed scan cycles in one session, **When** the owner
   views the session log, **Then** every cycle appears with its outcome
   (added / skipped / no match / failed) and the release identity where
   applicable, most recent first.
2. **Given** a scanning session in progress, **When** the server or page is
   interrupted and later reopened, **Then** the persisted journal on the
   laptop still contains every outcome recorded up to the interruption.
3. **Given** a new scan cycle completes, **When** the log updates, **Then**
   no earlier entry is lost or altered.

---

### User Story 4 - Manual search fallback (Priority: P3)

Some records defeat the camera: white labels, promos, worn sleeves, glare.
When identification yields nothing usable — or the owner rejects all
candidates — the page offers a free-text search box. The owner types what
they know ("Rhythim Is Rhythim Nude Photo") and gets the same kind of
candidate list, with the same confirm-to-add flow.

**Why this priority**: Keeps the session moving when vision fails; without
it, every hard record forces the owner to leave the app and use Discogs
directly, breaking the batch loop. It is P3 because the core loop works
without it for the majority of records.

**Independent Test**: With the search provider stubbed, submitting free text
returns a candidate list identical in shape and behavior (duplicate markers,
confirmation, logging) to the photo flow.

**Acceptance Scenarios**:

1. **Given** identification found no usable evidence in a photo, **When** the
   result is shown, **Then** the system states plainly that it could not
   identify the record (no invented guesses) and presents the manual search
   box.
2. **Given** the owner types a free-text query, **When** the search runs,
   **Then** matching releases are shown as candidates with the same fields,
   duplicate markers, and confirmation flow as photo-derived candidates.
3. **Given** a manual-search add completes, **When** the session log updates,
   **Then** the entry is recorded like any other outcome.

---

### Edge Cases

- Photo with no usable evidence (blurred, dark, not a record at all): the
  system states it could not identify the record and offers manual search —
  it never fabricates a candidate.
- Barcode digits extracted but the release database returns zero results for
  them: fall back to the next-strongest evidence (catalog number, then
  artist + title) within the same scan cycle before reporting no match.
- Evidence search returns a very large result set (generic self-titled
  album): the candidate list is capped at a small page with an indication
  that more matches exist, and the owner is invited to refine via manual
  search.
- The same release appears via multiple evidence paths: candidates are
  de-duplicated by release identity before display.
- Add request fails midway (network drop, API error, rate limit): the
  failure is reported honestly on the page, logged as failed in the session
  journal, and no snapshot update is recorded; the owner can retry.
- The local snapshot is missing or stale when a scan session starts:
  duplicate markers are degraded gracefully (marked as "duplicate status
  unknown — snapshot unavailable/stale") rather than silently wrong.
- Two adds of the same release in one session (intentional duplicates): the
  second add shows the duplicate marker including the copy just added this
  session.
- Upload exceeding the image size cap: rejected with a clear message before
  any identification work runs.
- A second device or browser tab opens the scan page mid-session: the
  session journal remains consistent (appends never corrupt earlier
  entries).
- The phone loses network mid-upload: the page reports the failure and
  allows re-taking the photo; nothing is logged as added.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST serve a phone-usable scan page reachable from
  the owner's phone over the home network while the laptop runs the serving
  process.
- **FR-002**: The scan page MUST let the owner capture a photo with the
  phone's native camera (or pick an existing photo) and submit it for
  identification in a single flow.
- **FR-003**: The system MUST extract identification evidence from the
  submitted photo — any of: artist, title, label name, catalog number,
  barcode digits, format hints — and MUST treat extraction as best-effort
  evidence, never as a final answer shown to the owner.
- **FR-004**: The system MUST resolve evidence into candidate releases by
  querying the live Discogs release database, applying evidence in
  precision order: barcode first, then catalog number (with label when
  available), then artist + title. A lower-precision query runs only when
  higher-precision evidence is absent or returned no results.
- **FR-005**: Every candidate shown to the owner MUST display cover
  thumbnail, artist, title, year, country, format, label, and catalog
  number, and every displayed value (including any URL or image reference)
  MUST come verbatim from the release database response — never constructed,
  inferred, or filled in by the identification step (018/019 ground-rule
  precedent).
- **FR-006**: Candidates MUST be de-duplicated by release identity and
  capped at a configured page size, with an explicit indication when more
  matches exist beyond the cap.
- **FR-007**: The system MUST NOT write to the Discogs collection except in
  direct response to an explicit owner confirmation of a specific candidate
  on the page. Identification and search steps have no write capability
  (017 write-gating precedent: pipeline proposes, human confirmation
  executes).
- **FR-008**: A confirmed add MUST add exactly the confirmed release to the
  configured collection folder of the owner's Discogs account, and the
  outcome (success or failure, with reason) MUST be reported on the page.
- **FR-009**: Before offering an add, the system MUST check the candidate
  against the local collection snapshot and visibly mark candidates already
  in the collection with their copy count. Adding a marked duplicate MUST
  require a second explicit confirmation.
- **FR-010**: If the snapshot is missing or stale, duplicate markers MUST
  degrade to an explicit "duplicate status unknown" state — the system MUST
  NOT present unknown status as "not in your collection".
- **FR-011**: After a successful add, the system MUST reconcile the local
  snapshot: either record the new instance in it or mark the snapshot
  stale, so no other consumer of the snapshot silently contradicts the live
  collection.
- **FR-012**: When identification produces no usable evidence or no
  candidates, the system MUST say so plainly and offer a manual free-text
  search that returns candidates through the same display, duplicate-check,
  and confirmation flow.
- **FR-013**: Every scan cycle outcome (added / skipped / no match /
  failed) MUST be appended to a per-session log visible on the page and
  persisted as a journal on the laptop; entries carry a timestamp, the
  outcome, and the release identity when one was involved. Existing entries
  are never rewritten.
- **FR-014**: After a completed add or an abandoned cycle, the page MUST
  return to the camera-ready state in one step, keeping the per-record
  interaction cost to a few taps.
- **FR-015**: All live Discogs traffic for this feature MUST respect the
  authenticated rate budget (60 requests/min) via the component's existing
  rate governor; identification and search MUST NOT bypass it.
- **FR-016**: Photo uploads MUST be size-capped with a clear rejection
  message; oversized uploads are rejected before identification work runs.
- **FR-017**: The scan page and its API MUST never expose the Discogs token
  or the vision provider's API key to the browser; secrets remain
  server-side, sourced from the component's environment configuration.
- **FR-018**: The identification step MUST be configuration-driven for its
  model/provider identity (no hardcoded model names — Constitution VII(a))
  and MUST be replaceable by a stub in tests; the test suite performs no
  live vision or Discogs calls.

### Key Entities

- **Scan cycle**: One photograph-or-search attempt and its resolution.
  Attributes: timestamp, evidence used (which kinds were extracted /
  entered), outcome (added / skipped / no match / failed), the confirmed
  release identity when one exists.
- **Identification evidence**: The structured best-effort reading of a
  photo — artist, title, label, catalog number, barcode digits, format
  hints. Never displayed as fact; only used to drive search.
- **Candidate release**: A release returned by the live database search.
  Attributes shown: release id, artist, title, year, country, format,
  label, catalog number, cover thumbnail; plus a duplicate status derived
  from the snapshot (in collection with count / not in collection /
  unknown).
- **Scan session**: The sequence of scan cycles between server start (or
  page open) and the end of the sitting; owns the visible log and the
  persisted journal.
- **Session journal**: The append-only persisted record of scan-cycle
  outcomes for review after interruption.
- **Collection snapshot**: The component's existing local copy of the
  owner's collection; consulted for duplicate status and reconciled (or
  marked stale) after successful adds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a record with a legible sleeve or barcode, the owner
  completes photograph → identified candidates on screen in under 15
  seconds per record under normal home-network conditions.
- **SC-002**: The correct pressing (or its master-level match) appears in
  the candidate list for at least 8 of 10 records with legible covers,
  labels, or barcodes in the owner's live validation batch.
- **SC-003**: Adding a confirmed record requires at most 3 taps after the
  photo is taken (candidate tap → confirm → back at camera), and at most 4
  for a duplicate (extra confirmation).
- **SC-004**: Zero writes to the Discogs collection occur without an
  explicit owner confirmation — verified across the full automated suite
  and the live validation session.
- **SC-005**: 100% of displayed candidate fields, links, and thumbnails
  originate verbatim from release-database responses (audited over a live
  validation batch, 019-style: zero constructed values).
- **SC-006**: Records already in the collection are flagged as duplicates
  with a correct copy count in 100% of snapshot-covered cases in the live
  validation batch.
- **SC-007**: After an interrupted session, the persisted journal accounts
  for 100% of completed scan cycles up to the interruption.
- **SC-008**: The full automated test suite passes with no live vision or
  Discogs API calls.

## Assumptions

- The feature lives inside the existing `collection-agent` component (the
  component that owns the live-collection domain: Discogs client, rate
  governor, snapshot, write-gating precedent). No new top-level component;
  no cross-component imports (Constitution VI).
- The serving process runs on the owner's laptop on the home LAN; the phone
  reaches it via the laptop's LAN address over plain HTTP. Public-internet
  exposure, HTTPS, and any authentication for the page itself are out of
  scope for v1 (single-occupant trusted home network assumed; note the page
  can trigger collection writes, so this assumption is recorded
  deliberately and revisiting it is an owner decision).
- Phone camera access uses the native camera via a file-capture control,
  which works on plain-HTTP LAN origins where in-page camera streaming
  would be blocked by secure-context rules.
- The scan page is a single self-contained static page served by the
  component itself — it is NOT part of the `frontend` component and shares
  no code with it.
- Evidence extraction uses the repo's LLM provider of record (OpenAI)
  with a vision-capable model, configured via settings; the plan phase
  decides the exact model default and the HTTP serving library.
- Discogs personal access token (`DISCOGS_USER_TOKEN` in `.env`) has the
  authority to write to the owner's own collection; folder defaults to the
  "Uncategorized" folder (id 1) unless configured otherwise.
- The existing two-phase sync remains the authoritative way to rebuild the
  snapshot; this feature only appends/reconciles enough to keep duplicate
  detection and the conversational agent honest between syncs.
- Identification quality targets legible printed evidence (covers, labels,
  barcodes); heavily worn, handwritten, or white-label records are expected
  to route to manual search rather than succeed via vision.
- v1 out of scope: playback/streaming, printing/labels, BPM/key detection,
  wantlist, marketplace pricing, native mobile apps, cover-art fingerprint
  matching, editing collection notes/custom fields, removing releases,
  YouTube integration.
- Live end-to-end validation with real records and real writes to the
  owner's account is an owner-only activity, excluded from the automated
  implement phase (020/021 pattern); the implement phase delivers
  everything up to that point.

## Replay addendum 1 (2026-07-07) — first live session: 0/4 identified

**Findings.** The owner's first live session (session
`20260707-130810Z`, two Crosstown Rebels 12″ singles, four photo
cycles — sleeve-with-center and label-only framings) identified
nothing. The journal plus the LangSmith traces of the four vision
calls showed two compounding causes, neither of them "the photo was
illegible":

1. *Evidence misclassification by the vision step* (F1). Barcode
   digits were transcribed into `catno` twice (`81824 11306`,
   `8 00505 200413` — digit runs that can never match a catalog
   number); the label name was read as the artist once; and no cycle
   produced a `title`, because 12″ singles print a track list, not a
   title — the model parked the lead tracks ("ace of spades",
   "the key") in `notes`, which nothing searches. The release title
   on Discogs for such singles IS the lead track.
2. *Ladder rigidity in the face of partial evidence* (F2). The
   artist+title rung requires both; artist-only, label-only, and
   track-title evidence was discarded entirely. Cycle 1 extracted a
   perfectly good label and never queried Discogs at all; cycle 2 had
   artist + label + lead track — enough for a trivial free-text hit —
   and returned "no match".

A third, tooling finding (F3): the journal records evidence *kinds*
only, so diagnosing this required LangSmith; the extracted field
values (never the photo) belong in the journal line.

**Requirement deltas.**

- **FR-003 (refined)**: the extraction prompt MUST teach the
  photo-domain distinctions the failures exposed: barcode digits vs
  catalog number, record-company name vs artist, and the 12″-single
  convention (no printed title ⇒ the lead A-side track is the title);
  extracted track titles get a dedicated `tracks` field (searchable
  evidence, unlike `notes`).
- **FR-019 (new)**: evidence normalization MUST reclassify a "catalog
  number" whose separator-stripped value is a digit run of 10+ as
  barcode evidence (never searched as a catno).
- **FR-020 (new)**: when every structured rung is absent or returns
  zero results, the system MUST fall back to one free-text search
  composed from the evidence it does hold (artist, title or lead
  track, label) before reporting no match. The fallback is a rung of
  the same ladder: same candidate shape, cap, and honesty rules; the
  cycle's recorded evidence kinds include `text` when it fired.
- **FR-021 (new)**: every journaled photo-cycle outcome MUST carry the
  extracted evidence field values (compact, excluding the image);
  manual-search outcomes carry the query. Debugging an identification
  failure must not require the tracing backend (F3).

**Out of scope for this addendum**: model choice (the vision model is
already a settings knob; the owner repointed it independently),
client-side image downscaling, and any change to write gating.
