# Feature Specification: Scan Release & Master Selection

**Feature Branch**: `026-scan-release-selection`
**Created**: 2026-07-12
**Status**: Draft
**Input**: User description: "When scanning a record and searching it on discogs, I want a way to see the master and the release selected, and a list of the other probable releases that could match in order to give the user the ability to select another one. Also, clicking/tapping on a master or release should open it in discogs in another tab."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the selected release, its master, and the alternatives (Priority: P1)

After scanning a record, the owner sees the results organized around a single
clearly designated **selected release** — the system's current best match —
together with the identity of the **master** (the album/work) that release
belongs to, followed by the **other probable releases** presented as
selectable alternatives. If the record in hand is one of the alternatives
rather than the best match, the owner selects that alternative and adds it
through the same confirmation flow that exists today.

**Why this priority**: This is the core of the request. Today all candidates
are presented as an undifferentiated flat list; the owner can't tell at a
glance which one the system considers the match, what album it represents,
or how the rest relate to it. Distinguishing "the pick" from "the plausible
others" is the primary decision aid when several pressings look alike.

**Independent Test**: Can be fully tested by scanning (or manually searching)
a record that yields multiple candidates and verifying that exactly one
candidate is presented as the selected release with its master identity
shown, the remainder appear as alternatives, and choosing an alternative
adds that alternative (not the selected one) after the usual confirmation.

**Acceptance Scenarios**:

1. **Given** a scan that returns two or more candidates, **When** the results
   appear, **Then** exactly one candidate is visually designated as the
   selected release, its master identity is shown when the release belongs
   to a master, and the remaining candidates appear as a distinct list of
   alternatives.
2. **Given** results are displayed, **When** the owner selects an alternative
   and confirms, **Then** the alternative — not the originally selected
   release — is added to the collection, with the existing duplicate
   confirmation still enforced.
3. **Given** a scan that returns exactly one candidate, **When** the results
   appear, **Then** that candidate is shown as the selected release (with
   master identity when it has one) and the alternatives list is honestly
   empty — no filler entries.
4. **Given** the selected release does not belong to any master, **When**
   the results appear, **Then** no master is shown for it and nothing is
   fabricated in its place.
5. **Given** a manual search (typed query) instead of a photo scan, **When**
   candidates come back, **Then** they receive the same selected-release /
   master / alternatives presentation.

---

### User Story 2 - Open a release or master on Discogs in a new tab (Priority: P2)

While reviewing results, the owner taps/clicks any displayed release or
master and it opens on the Discogs website in a new browser tab, so they can
inspect the full page (tracklist, images, pressing notes) before deciding —
and then return to the scan page with the results and session exactly as
they left them.

**Why this priority**: Verification against the real Discogs page is how the
owner resolves close calls between pressings. It depends on the results
being displayed (US1) but delivers standalone value the moment any release
or master is on screen.

**Independent Test**: Can be fully tested by tapping the Discogs link on a
displayed release and on a displayed master, confirming each opens the
correct Discogs page in a new tab, and confirming the scan page still shows
the same results and can still add a candidate afterwards.

**Acceptance Scenarios**:

1. **Given** results are displayed, **When** the owner taps the Discogs
   action on any release, **Then** that exact release's Discogs page opens
   in a new tab and the scan page keeps its current results.
2. **Given** a master is displayed, **When** the owner taps its Discogs
   action, **Then** that exact master's Discogs page opens in a new tab.
3. **Given** the owner has opened a Discogs page in a new tab, **When** they
   return to the scan page, **Then** the scan session is intact and they can
   still select and add a candidate from the same results.
4. **Given** a displayed release, **When** the owner taps its open-on-Discogs
   action, **Then** nothing is added to the collection — the link action and
   the add action are unmistakably distinct.

---

### User Story 3 - Browse other pressings of the selected master on demand (Priority: P3)

When the record in hand isn't among the displayed candidates but the album
clearly is (right album, wrong pressing), the owner taps an explicit "show
other pressings of this master" action. Only then does the system fetch the
master's other versions from Discogs and present them as additional
selectable alternatives, each addable through the same confirmation flow.

**Why this priority**: Measured evaluation of the scan pipeline showed a
meaningful class of misses are other pressings of the correct master. This
closes that gap at the moment it matters — without adding latency or Discogs
requests to the scans where the best match was already right, which is why
it is on-demand rather than automatic.

**Independent Test**: Can be fully tested by scanning a record whose correct
pressing is absent from the candidates but whose master is represented,
tapping the on-demand action, and verifying additional versions of that
master appear and one of them can be selected and added.

**Acceptance Scenarios**:

1. **Given** a selected release that belongs to a master, **When** the owner
   taps the "show other pressings" action, **Then** other versions of that
   master are fetched and shown as additional alternatives with the same
   descriptive detail and Discogs links as the original candidates.
2. **Given** the on-demand versions are displayed, **When** the owner selects
   one and confirms, **Then** it is added to the collection through the same
   confirmation (and duplicate confirmation) gate as any other candidate.
3. **Given** a selected release with no master, **When** results are shown,
   **Then** no "show other pressings" action is offered for it.
4. **Given** the fetch of other pressings fails or returns nothing new,
   **When** the owner has tapped the action, **Then** they see an honest
   message to that effect and the original results remain usable.
5. **Given** other pressings were fetched, **When** they are displayed,
   **Then** their duplicate-status marking follows the same rules as the
   original candidates (including the explicit "unknown" state — never a
   false "not in collection").

---

### Edge Cases

- Selected release has no master: no master shown, no master link, no
  "other pressings" action — and never a fabricated placeholder.
- Several candidates share the same master: each still appears once as its
  own release; the master shown belongs to the selected release.
- A candidate is missing the identifier needed for a Discogs link: that
  candidate simply offers no link — a link is never constructed from any
  other identifier.
- Zero candidates: the existing no-match flow (message + manual search) is
  unchanged; there is nothing to designate as selected.
- Opening a Discogs tab on the phone backgrounds the scan page: returning
  must find the results and session state intact.
- Starting a new scan while other-pressings results are displayed follows
  the existing supersede behavior — the new scan replaces everything shown.
- The on-demand pressings list may be long on popular masters: it must be
  presented without silently truncating — if there are more versions than
  shown, say so.
- Duplicate confirmation still applies to every add path, including adds
  chosen from on-demand pressings.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Results with at least one candidate MUST designate exactly one
  candidate as the selected release — the system's top-ranked match — and
  present it visually distinct from the other candidates.
- **FR-002**: When the selected release belongs to a master, the results
  MUST display that master's identity alongside the selected release; when
  it does not, no master information is shown and none is invented.
- **FR-003**: All remaining candidates MUST be presented as a list of
  alternative releases carrying the same descriptive detail and
  duplicate-status marking they carry today.
- **FR-004**: The owner MUST be able to select any alternative and add it
  through the existing add-confirmation flow; selecting an alternative MUST
  never weaken the confirmation or duplicate-confirmation gates.
- **FR-005**: Every displayed release MUST offer an action that opens that
  exact release's Discogs page in a new browser tab.
- **FR-006**: Every displayed master MUST offer an action that opens that
  exact master's Discogs page in a new browser tab.
- **FR-007**: Discogs links MUST be built only from genuine identifiers
  returned by Discogs for that item; when the identifier is absent, no link
  is offered. A link MUST never be constructed from any other identifier.
- **FR-008**: Opening a Discogs page MUST NOT disturb the scan session:
  after returning to the scan page, the displayed results remain valid and
  a candidate can still be selected and added.
- **FR-009**: The open-on-Discogs action MUST be clearly distinct from the
  add action: activating a link never adds a record, and activating add
  never navigates away.
- **FR-010**: When the selected release belongs to a master, the results
  MUST offer an explicit on-demand action that fetches and displays other
  versions of that master as additional selectable alternatives. The fetch
  happens only when the owner invokes the action — never automatically as
  part of a scan.
- **FR-011**: On-demand pressings MUST be displayed with the same
  descriptive detail, duplicate-status rules (including the explicit
  "unknown" state), Discogs links, and add-confirmation gates as original
  candidates.
- **FR-012**: If the on-demand fetch fails or yields no additional versions,
  the owner MUST see an honest message and the previously displayed results
  MUST remain usable.
- **FR-013**: If more versions of a master exist than are displayed, the
  results MUST say so rather than silently truncating.
- **FR-014**: The selected-release / master / alternatives presentation MUST
  apply equally to photo-scan results and manual-search results.

### Key Entities

- **Selected release**: The top-ranked candidate of a scan or manual search;
  exactly one per non-empty result set. Carries the same descriptive detail
  as today plus its master identity (when it has one) and a Discogs link.
- **Master**: The album/work a release is a pressing of. Displayed for the
  selected release when known; source of the on-demand "other pressings"
  list; linkable to its Discogs page.
- **Alternative release**: Any non-selected candidate, whether from the
  original search or fetched on demand from the selected release's master.
  Selectable, addable via the existing confirmation flow, linkable.
- **Discogs page link**: An outbound reference to the exact Discogs page for
  a release or master, derived only from that item's genuine identifier.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any scan returning multiple candidates, the owner can
  identify which release the system selected and (when it exists) its
  master without any additional taps — both visible in the initial results.
- **SC-002**: 100% of offered Discogs links open the exact page for the
  item they were shown on (verifiable by spot-checking every link in a live
  session against the release/master identifiers Discogs returned).
- **SC-003**: The owner can open a Discogs page and return to the scan page
  with results and session intact 100% of the time, on the phone.
- **SC-004**: Adding an alternative (original or on-demand) requires no more
  confirmation steps than adding the selected release does today.
- **SC-005**: For a record whose correct pressing is absent from the
  original candidates but whose master is represented, the owner can reach
  and add the correct pressing via the on-demand action in a single scan
  session — no re-scan or manual search needed.
- **SC-006**: Scans where the owner never invokes the on-demand action incur
  zero additional Discogs requests compared with today.

## Assumptions

- "The release selected" means the system's top-ranked candidate from the
  existing search precision ladder, presented as the current best match
  before any add happens; the ranking itself is unchanged by this feature.
- The alternatives shown by default are the candidates the existing search
  already returns (up to the existing cap); other pressings of the master
  join only via the explicit on-demand action (owner decision, 2026-07-12).
- The existing add flow — explicit confirmation, server-enforced duplicate
  confirmation, session allowlist — is reused as-is for every add path this
  feature introduces; this feature adds no new write capability.
- "Another tab" means the platform's default new-tab behavior in the phone
  or desktop browser; the scan page itself never navigates away.
- The feature lives entirely in the existing scan experience (the phone
  page and its backing service); the conversational agent, eval harness,
  and snapshot sync are untouched.
- Discogs page addresses for releases and masters follow the same
  tool-built-link discipline already established for the collection agent's
  listing links (019): links derive only from genuine identifiers, never
  from any other id space.
- The scan identification evaluation (023/024/025) measures the search
  pipeline, not the results presentation; since this feature's default view
  reorders nothing and the on-demand fetch is owner-invoked, eval results
  remain comparable.
