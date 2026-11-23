# Feature Specification: User-context tenancy seam

**Feature Branch**: `029-user-context-tenancy-seam` (drafted on `claude/collection-agent-roadmap-boujgu`)
**Created**: 2026-11-23
**Status**: Draft
**Input**: User description: "Roadmap item D1 of `docs/collection_agent_distribution_roadmap.md` — the tenancy seam. Introduce a per-user context that owns everything that is process-global today (Discogs credential and username, snapshot + sync journal + live-writes marker, scan journal, scan session with its candidate allowlist and supersede state, web chat with its transcript / pending plan / busy lock, sync status, scan target folder) plus a registry that builds contexts lazily. Split deployment settings from per-user state. Make the Discogs rate-limit governor process-wide, because Discogs throttles per source IP. Give the Discogs client a pluggable credential strategy. Local mode keeps running as one implicit user built from `.env`, byte-identical to today. Done when behavior is unchanged in local mode and a test drives two contexts in one process with full isolation of snapshot, chat, scan session and journals. No auth, no hosted mode, no OAuth signer, no metering, no database, no frontend change — those are D3, D5 and D6."

## Context

The collection agent is a single-user program. Its domain logic is already
injectable — the web app, the agent loop, the scan pipeline and the sync all
receive their collaborators as arguments — but the **composition** builds
exactly one of everything per process, from one `.env`: one Discogs token, one
snapshot file, one scan session, one chat conversation, one sync runner.

The owner wants to distribute the app to a small group of trusted people, each
using their own Discogs collection
(`docs/collection_agent_distribution_roadmap.md`). Every later step of that
roadmap — sign-in, per-user Discogs authorization, usage metering — needs a
place to attach "this belongs to that user". This feature creates that place
and nothing else. It is deliberately invisible: when it ships, the owner's
workflow is unchanged, and the only new capability is one that tests can
exercise — two users served by one process without touching each other.

Terms used throughout:

- **User context** — everything that belongs to one user of the running
  process: their identity, their Discogs access, where their data lives, and
  their live session state.
- **Implicit local user** — the single user context that every existing
  command builds from `.env`. It is today's behavior, expressed in the new
  shape.
- **Context registry** — the process-wide component that hands out the user
  context for a given user id.
- **Deployment configuration** — settings that describe the running app as a
  whole (models, limits, URLs), as opposed to values that belong to one user.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The owner's local workflow is provably unchanged (Priority: P1)

The owner keeps using the collection agent exactly as today: `chat`, `sync`,
`status`, `serve`/`scan`, the eval commands, from the host virtualenv or the
container. Every command reads and writes the same files at the same paths,
prints the same output, returns the same exit codes, and serves the same HTTP
responses. Nothing has to be migrated, reconfigured or re-synced.

**Why this priority**: This is a structural change underneath a working,
live-validated tool. If it alters any observable behavior it is a regression,
whatever else it enables. Non-interference is the feature's hard constraint.

**Independent Test**: On the commit that ships this feature, run the full
pre-existing test suite unmodified, then repeat one real scan-and-add, one chat
turn that proposes and confirms a folder move, and one sync from the page.
Compare the data directory listing before and after against the same session
on the previous commit.

**Acceptance Scenarios**:

1. **Given** an existing `.env` and data directory, **When** any existing
   command is run with the same arguments as before the feature, **Then** its
   output, exit code and file effects are the same as before.
2. **Given** the web page is served, **When** the full scan, chat, plan-confirm
   and sync cycle is driven through it, **Then** every response is identical to
   the response the pre-feature composition returns for the same inputs.
3. **Given** the existing data directory, **When** the feature's version runs
   for the first time, **Then** no file is moved, renamed, copied or
   duplicated, and a later run of the previous version still reads the same
   data.
4. **Given** a missing or rejected Discogs token, a missing OpenAI key, or a
   scan folder id that does not exist on Discogs, **When** a command starts,
   **Then** it fails at the same point, with the same exit code and an
   equivalent message, as today.

---

### User Story 2 - Two users in one process never see each other's data (Priority: P1)

Two user contexts live in one running process. Each has its own Discogs
identity and its own data directory. Each one syncs, scans, adds a record,
chats, and confirms a folder move. Afterwards, each user's snapshot and
journals contain only that user's activity, and neither user's answers,
duplicate badges or pending plans ever reflect the other's collection.

**Why this priority**: This is the capability the feature exists to create and
the foundation every later roadmap item builds on. Equal-top priority with
US1: a seam that leaks between users would be worse than no seam.

**Independent Test**: A test harness builds two user contexts with distinct
fake Discogs accounts in one process, drives the complete scan → add → chat →
move → sync cycle for both, interleaved, and then asserts on each user's files
and responses that no record, journal line, transcript entry or allowlisted
candidate crossed over.

**Acceptance Scenarios**:

1. **Given** two user contexts with different collections, **When** each one
   syncs, **Then** each snapshot contains only its owner's records and each
   sync resumes only from its owner's journal.
2. **Given** user A has scanned a record and been served candidates, **When**
   user B attempts to add one of those candidates without having been served
   it, **Then** the add is refused exactly as an unknown candidate is refused
   today.
3. **Given** user A adds a record, **When** user B's snapshot state is read,
   **Then** it is unchanged — only A's snapshot is marked stale.
4. **Given** user A has a pending folder-move plan, **When** user B confirms
   or cancels using A's plan id, **Then** B gets the same "no pending plan"
   refusal an unknown id gets today, and A's plan is untouched.
5. **Given** both users have chatted, **When** each reloads their history,
   **Then** each sees only their own conversation.

---

### User Story 3 - One user's activity or failure never blocks another (Priority: P2)

The rules that today protect a single user from themselves — one chat turn at
a time, a new scan supersedes the one in flight, at most one sync running —
apply to each user separately. A user whose Discogs credential is rejected, or
whose scan folder no longer exists, gets a clear error of their own; the
process keeps running and every other user is unaffected.

**Why this priority**: Without it the app is technically multi-user but
practically single-occupancy: the first person mid-turn would lock everyone
else out. Second priority because US2 already delivers correct isolation of
data; this story delivers isolation of *behavior*.

**Independent Test**: With two contexts, hold user A's chat turn and scan
identification open (as the existing tests already do for one user), then
drive user B through a full cycle. Separately, give user A a credential that
Discogs rejects and confirm user B completes a full cycle while A receives a
typed error.

**Acceptance Scenarios**:

1. **Given** user A's chat turn is in flight, **When** user B sends a message,
   **Then** B's turn is accepted and answered; only a second message from A is
   refused as busy.
2. **Given** user B's photo identification is in flight, **When** user A
   starts a new scan, **Then** B's identification completes normally — only
   A's own earlier scan is superseded.
3. **Given** user A's sync is running, **When** user B starts a sync, **Then**
   B's sync starts; only a second start from A is refused as already running.
4. **Given** Discogs rejects user A's credential, **When** A makes any
   request, **Then** A receives a typed error, the process stays up, and user
   B's requests succeed.
5. **Given** user A's scan target folder does not exist on Discogs, **When** A
   tries to add a record, **Then** A's add is refused with a clear error and no
   other user is affected.

---

### User Story 4 - All users share one Discogs rate budget (Priority: P2)

Discogs limits requests per source IP, not per account, so every user of one
process draws from the same budget. All Discogs traffic — scans, adds, folder
moves, sync enrichment, for every user — is paced against that one budget, so
the process as a whole stays within the limit instead of each user pacing as
if they were alone.

**Why this priority**: With per-client pacing, two users syncing at once would
each believe they own the full budget and together run into sustained
throttling. This must be right before a second real user exists. Second
priority because with one user (today) the difference is not observable.

**Independent Test**: With two contexts issuing Discogs requests from
concurrent threads against a fake that reports a shrinking shared budget,
verify that once the reported remaining budget reaches the configured floor,
neither context sends another request until the pacing delay has elapsed, and
that a throttling response to one user backs off both.

**Acceptance Scenarios**:

1. **Given** two users making Discogs requests concurrently, **When** the
   budget reported by Discogs reaches the floor on a response to either user,
   **Then** the next request from either user is paced.
2. **Given** a throttling response to user A, **When** user B makes a request
   during the backoff, **Then** B's request waits as well.
3. **Given** many threads sharing the budget, **When** they run concurrently,
   **Then** the pacing state stays consistent — no lost updates, no deadlock.
4. **Given** a single user (local mode), **When** a page sync runs while that
   user scans, **Then** both draw on the same budget and both complete, as the
   owner experiences today.

---

### User Story 5 - The next features have a place to plug in (Priority: P3)

The roadmap's next steps each replace one thing per user: how a user proves
who they are to Discogs (per-user authorization), and what happens around each
of their LLM calls (usage metering). After this feature, each of those is a
substitution at a single, per-user point — no caller of the Discogs client or
the LLM client has to change.

**Why this priority**: It is what makes the seam worth building now, but it
delivers no behavior of its own; it is proven by demonstration, not by use.

**Independent Test**: In tests only, register a second Discogs credential
strategy and a wrapping LLM handle for one user context, and show that the
user's scan, chat and sync flows use them — with zero edits to the code that
makes Discogs or LLM calls, and with the other user's context still using the
defaults.

**Acceptance Scenarios**:

1. **Given** a user context configured with a test credential strategy,
   **When** that user's flows call Discogs, **Then** every request carries the
   authorization produced by that strategy and no other user's requests do.
2. **Given** a user context whose LLM handle is wrapped by a recording
   wrapper, **When** that user chats and scans, **Then** the wrapper observes
   every LLM call made for that user — chat turns and photo extraction — and
   none made for anyone else.
3. **Given** no wrapper is configured, **When** any user makes LLM calls,
   **Then** the calls are exactly the calls made today: same requests, same
   count, same tracing behavior.

---

### Edge Cases

- **Hostile or malformed user ids**: an id containing path separators, parent
  references, empty or whitespace-only text, or a name reserved for the
  implicit local user is rejected before any file is created or any request is
  sent. No id can make one user's data directory resolve inside, above, or
  equal to another's.
- **First use from two threads at once**: two simultaneous first requests for
  the same user produce exactly one context; both callers receive it. Live
  session state (allowlist, pending plan) therefore can never fork.
- **Disposing a context that is busy**: releasing a user's context while their
  sync or chat turn is running ends that user's work the same way stopping the
  process does today — the sync journal allows a later resume, the pending
  plan is void — and affects no other user.
- **Two contexts pointing at the same Discogs account**: not prevented by this
  feature (uniqueness is a rule of the later per-user authorization feature).
  Each context still has its own directory and stays internally consistent;
  they behave like the same account used from two machines today.
- **Process restart**: in-memory state is lost for every user, exactly as it
  is lost for the one user today. On-disk state — snapshot, sync journal, scan
  journals — is intact and per user.
- **Scan sessions started in the same second by different users**: journal
  file names derive from the start time; because journals live in per-user
  directories they cannot collide.
- **Photo retention enabled**: retention is an owner diagnostic. It applies to
  the implicit local user only; no other user's photos are ever retained.
- **Eval commands**: they keep operating on the implicit local user's snapshot
  and the existing eval directories. They are never per-user.
- **Tracing**: LangSmith behavior is unchanged, including the strict no-op
  when unconfigured. Tagging traces by user is deferred to the metering
  feature.
- **A user with no snapshot yet**: each user independently sees the existing
  "no snapshot, sync first" behavior; another user's complete snapshot is
  never used as a fallback.

## Requirements *(mandatory)*

### Functional Requirements

**The tenancy model**

- **FR-001**: The system MUST represent each user as a user context that owns
  that user's: identity (user id and Discogs username), Discogs access,
  snapshot location (including the sync journal and live-writes marker), scan
  journal location, scan target folder, scan session state (candidate
  allowlist, session adds, open cycles, supersede state), chat state
  (transcript, pending write plan, busy state), sync status, and LLM access
  handle.
- **FR-002**: A context registry MUST return the user context for a user id,
  building it on first use. It MUST return the same context for the same user
  for as long as that context lives, and MUST build exactly one context when
  the first uses are concurrent.
- **FR-003**: The registry MUST support explicitly disposing a user context,
  releasing that user's resources without affecting any other context. This
  feature defines no automatic expiry or eviction.
- **FR-004**: User ids MUST be validated against a conservative,
  filesystem-safe form before any file or network effect. An invalid id MUST
  be rejected with a typed error. No valid id may resolve to a location
  outside the per-user data root, to another user's location, or to the
  implicit local user's location.

**Local mode is unchanged**

- **FR-005**: Every existing command (`chat`, `sync`, `status`, `serve`,
  `scan`, `eval-dataset`, `eval-run`) MUST operate as the implicit local user
  built from `.env`, with unchanged arguments, output, exit codes, startup
  checks (including their order) and file effects. Every HTTP endpoint
  published by 022, 026 and 028 MUST keep its contract verbatim.
- **FR-006**: The implicit local user's data MUST stay at today's locations
  with today's file names and formats. The feature MUST NOT migrate, move or
  copy existing data, and the 027 host/container interchangeability MUST hold
  unchanged.
- **FR-007**: All pre-existing tests MUST pass unmodified. Any change to a
  pre-existing test is an exception that MUST be individually justified and
  recorded in the feature's task notes (the secrets-audit allowlist in
  FR-020 is the one anticipated case).
- **FR-008**: No entry point shipped by this feature may serve any user other
  than the implicit local user, and no request input — parameter, header,
  cookie, body field or path segment — may select a user. Selecting a user
  becomes possible only together with authentication, in a later feature.

**Isolation between users**

- **FR-009**: Any operation performed for one user MUST read and write only
  that user's snapshot, sync journal, live-writes marker, scan journals and
  in-memory session state.
- **FR-010**: Each non-implicit user's data MUST live in its own directory
  under a single per-user data root, using the same file set and formats as
  today. The snapshot schema and the scan journal schema are unchanged.
- **FR-011**: The existing single-occupancy rules MUST apply per user: one
  chat turn at a time, a new scan superseding that user's in-flight
  identification and auto-closing that user's open cycles, and at most one
  running sync. One user's activity MUST NOT trigger any of these for another
  user.
- **FR-012**: The write gates MUST hold per user: a record can be added only
  if it was served as a candidate to that same user, and a move plan can be
  confirmed or cancelled only by the user it was proposed to. A cross-user
  attempt MUST be indistinguishable from an unknown candidate or unknown plan.
- **FR-013**: A failure that belongs to one user — rejected Discogs
  credential, nonexistent scan target folder, Discogs or LLM error — MUST
  surface as that user's typed error. It MUST NOT terminate the process or
  change any other user's state. For the implicit local user the same
  conditions keep today's startup failures (FR-005).
- **FR-014**: The scan target folder MUST be a per-user value, and MUST be
  validated against the user's live Discogs folders before the first add is
  executed for that user.

**Resources shared by all users**

- **FR-015**: All Discogs requests made by the process, for every user and
  every purpose, MUST be paced by one shared rate-limit budget that reflects
  the most recent budget reported by Discogs, whichever user's response
  reported it. The shared pacing MUST be correct under concurrent use.
- **FR-016**: This feature MUST NOT introduce prioritization or queuing of
  Discogs traffic. Concurrent syncs by different users are allowed and simply
  share the budget. Scheduling is a later feature.
- **FR-017**: The LLM provider client MUST remain one per process, and each
  user context MUST obtain LLM access through its own handle. Every LLM call
  made on behalf of a user — chat and photo extraction — MUST go through that
  user's handle. In this feature the handle passes calls through unchanged:
  no extra requests, no altered payloads, no change to tracing.
- **FR-018**: How a user authenticates to Discogs MUST be a per-user,
  replaceable strategy. The personal access token is the only strategy this
  feature ships. Adding another strategy MUST require no change to the code
  that issues Discogs requests. The endpoints called, the other request
  headers and the failure policy are unchanged.

**Configuration**

- **FR-019**: Configuration MUST be separated into deployment configuration
  and per-user values. Per-user values are: Discogs credential, Discogs
  username, snapshot location, scan journal location and scan target folder.
  Photo retention and the eval directories stay deployment-level and apply to
  the implicit local user only. Per-user values MUST be read in one
  composition point, not scattered through the code.
- **FR-020**: Discogs credentials MUST never appear in logs, exceptions,
  snapshots, journals, traces or HTTP responses. The existing secrets audit
  MUST keep passing; if the sanctioned place where a secret is unwrapped
  moves, the audit's allowlist is updated deliberately and the number of
  sanctioned places MUST NOT grow beyond what the new composition point
  requires.
- **FR-021**: Deployment configuration MUST be loadable without any Discogs
  credential present, so that contexts for other users can be composed.
  Commands that act as the implicit local user MUST still fail with the
  configuration exit code, naming the missing variable, when it is absent.
- **FR-022**: Any new configurable value MUST be settings-sourced with a
  default that preserves today's behavior (Constitution VII(a)). The location
  of the per-user data root is the only new value anticipated.

**Guards and records**

- **FR-023**: An automated two-user isolation suite MUST drive the complete
  scan, add, chat, move and sync cycle for two contexts in one process and
  assert the isolation and concurrency properties of FR-009 through FR-013.
- **FR-024**: Structural guards MUST pin the seam so it cannot erode
  silently: per-user configuration values are read only at the composition
  point (FR-019), and LLM and Discogs access for a user is obtained only
  through that user's context (FR-017, FR-018).
- **FR-025**: Contract documents that describe a process-wide singleton — the
  one shared conversation and one sync runner of 028, the one session per
  server run of 022, the per-client governor of 017 — MUST be amended to
  per-user (or, for the governor, process-wide) wording, with every payload
  shape left unchanged.

### Key Entities

- **User context**: one user's slice of the running process — identity,
  Discogs access, data locations, scan target folder, and live session state
  for scan, chat and sync. Built on first use, lives until disposed or the
  process ends.
- **Implicit local user**: the user context every existing command uses,
  built from `.env`, whose data stays at today's paths.
- **Context registry**: hands out the one context per user id; the only way
  to reach per-user state.
- **Per-user data root**: the directory under which each non-implicit user
  has a private directory with the same files the owner has today.
- **Discogs credential strategy**: how one user's requests are authorized.
  One implementation in this feature: the personal access token.
- **Shared rate budget**: the single process-wide view of Discogs's
  per-IP request allowance, used to pace all users' traffic.
- **LLM access handle**: the per-user point through which that user's LLM
  calls pass; a transparent pass-through in this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All pre-existing tests (639 at 028's merge) pass, with zero
  pre-existing test files modified or with each modification individually
  justified in the task notes.
- **SC-002**: The owner repeats one real scan-and-add, one chat turn with a
  confirmed folder move, and one sync from the page, and observes no
  difference from the pre-feature behavior; the data directory contains no
  moved, renamed or newly introduced files beyond those the same session
  creates on the previous version.
- **SC-003**: The full scan, chat, plan and sync cycle driven through the
  implicit local user's web app returns responses byte-identical to those of
  the pre-feature composition for the same scripted inputs.
- **SC-004**: In the two-user suite, after both users complete the full cycle
  interleaved, 100% of the records, journal lines, transcript entries and
  allowlisted candidates found in each user's state belong to that user, and
  every cross-user add, confirm and cancel attempt is refused.
- **SC-005**: While one user's chat turn, scan identification and sync are
  held open, the other user completes a full cycle with no busy, superseded or
  already-running refusal.
- **SC-006**: With one user's Discogs credential rejected, the other user
  completes a full cycle and the process remains running.
- **SC-007**: With two contexts issuing Discogs requests from concurrent
  threads, zero requests are sent by either context while the shared budget is
  at or below the floor and the pacing delay has not elapsed.
- **SC-008**: A second credential strategy and a wrapping LLM handle are
  exercised for one user in tests with zero edits to the code that issues
  Discogs or LLM requests, and the wrapper observes 100% of that user's LLM
  calls and none of the other user's.
- **SC-009**: Every id in a list of hostile user ids (path traversal, absolute
  paths, separators, empty, reserved) is rejected with no file created and no
  request sent.
- **SC-010**: An audit of the HTTP surface shipped by this feature finds no
  request input that selects a user.

## Assumptions

- This feature is roadmap item D1 of
  `docs/collection_agent_distribution_roadmap.md`. Hosted run mode,
  authentication and the database (D3), the Discogs OAuth signer, per-user
  credential storage, and traffic scheduling (D5), usage metering and trace
  tagging by user (D6), and the new web client (D2) are out of scope. D1
  ships no new command, endpoint or user-visible behavior.
- The spec number 029 follows the repository's sequence. The `date_added`
  recency follow-up, informally called the "029 candidate" in 028's notes,
  takes a later number when it is specified.
- The implicit local user keeps today's data layout rather than moving under
  the per-user data root. This costs a small asymmetry between the implicit
  user and every other user, and buys zero migration, zero risk to the
  owner's live data, and unchanged 027 container behavior.
- How the seam is built is a planning decision, including whether the scan
  server's per-run state is extracted into a per-user object or the existing
  app is instantiated once per user. Source changes under
  `collection-agent/src/` are expected, including in `scan/server.py`: 028's
  "zero diff in `scan/server.py`" was that feature's constraint, not a
  standing rule. What is fixed is the outcome: contracts verbatim and tests
  unmodified.
- Sharing one rate-limit budget is correct for the single local user too:
  today the scan server, the sync runner and the folder-move tools each pace
  independently against the same per-IP allowance. Unifying them changes
  pacing decisions only at the margin and changes no contract.
- The target is up to about ten users in one process and one worker. No
  context eviction, no cross-process coordination and no horizontal scaling
  are required.
- No new dependencies are expected.
- Because no entry point exposes more than the implicit user, the multi-user
  capability is validated by automated tests only; live owner validation
  covers the unchanged local workflow.
