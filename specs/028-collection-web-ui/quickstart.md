# Quickstart: Collection-Agent Web UI (028)

## Run it

```bash
cd collection-agent
source .venv/bin/activate   # or your venv
python -m collection_agent serve        # new name
python -m collection_agent scan         # same thing (alias; 027 container CMD)
```

Startup is the familiar scan sequence (Discogs token + identity check,
live folder validation, OPENAI_API_KEY required) plus the chat agent and
sync runner. The banner prints the LAN URLs; open one on the phone
(Docker note from 027 still applies: the phone needs the HOST's LAN IP,
not the container bridge IP).

Container (unchanged from 027):

```bash
docker compose --profile collection up -d collection-agent
```

## The page

- **Scan tab** — exactly the 022/026 flow.
- **Chat tab** — converse in English or Spanish; folder-move proposals
  render as a confirmation card (Confirm / Cancel). A stale/absent
  snapshot shows a banner with a Sync action.
- **Collection tab** — snapshot status (state, counts, last sync), Sync
  button with live progress, and "View on Discogs" link.

## Tests

```bash
cd collection-agent && pytest
```

No live API calls; the web endpoints are exercised via TestClient with
stubbed LLM/Discogs clients, like the scan suite.

---

## Owner live-validation checklist (fill during live validation; owner-only)

- [x] **SC-001 — web chat parity**: from the phone, ask a collection
  question in the Chat tab; answer matches terminal chat for the same
  snapshot. Ask one question in Spanish; reply is Spanish.
  *Owner-validated 2026-07-12: asked in English then in Spanish — replies
  matched the question language both times; CLI↔web parity confirmed
  (same output content; only the rendering differs, per delta 15's
  plain-text web format). Validated after replay addenda 1–2 landed.*
- [x] **SC-002 — write gate**: ask chat to move records to a folder; a
  confirmation card appears. First: Cancel → verify on Discogs nothing
  changed. Then repeat and Confirm → per-move outcomes shown, records
  moved on Discogs, Collection tab still reads `complete` (snapshot
  patched in place). Record the folder + record count used.
  *Owner-validated 2026-07-13: confirm leg — records found and moved
  correctly; cancel leg — cancelled a plan and verified on Discogs that
  nothing changed. Two presentation findings fixed during validation
  (replay addendum 3, rounds 1–2): the LLM re-listing the plan above
  the card, and the card staying tappable during "Executing moves" —
  card now clears at tap time.*
- [x] **SC-003 — stale → sync → fresh, one process**: add a record via
  the Scan tab (snapshot goes stale, banner appears) → tap Sync → watch
  progress to completion → status reads `complete` with updated counts →
  ask chat about the newly added record; it answers from the fresh
  snapshot. No server restart anywhere.
  *2026-11-20 attempt (session `20261120-214751Z`) NOT a pass: the only
  add (release `29147545`, 22:00:29Z) landed 2 min INTO a running sync,
  and the sync saved its pre-add listing as `complete` — the record was
  missing locally → replay addendum 4 / FR-017. Re-run after the fix
  with the live-write leg:* (1) add record X with NO sync running → stale
  banner; (2) tap Sync; while it runs, add record Y → the run ends
  `⚠ sync finished, but a change landed mid-sync — Sync again…`, status
  `stale` (never `complete`); (3) tap Sync again → finishes in seconds,
  `complete`, counts include X and Y; (4) chat finds both. Note: the
  first post-fix Sync also picks up `29147545` (already on Discogs).
  *Owner-validated 2026-11-21 after addendum 4 (session
  `20261121-192627Z`): X = `29147545` added 19:29:13Z with no sync
  running → stale; Sync; Y = `7722776` added 19:33:35Z mid-sync (marker
  bumped 19:33Z) → run 1 ended **partial** (not stale) with the
  "run sync again … quick" cause warning — legitimately: one release's
  enrichment also failed in that run (follow-up fetched 2 releases, not
  1: 10 requests = 5 pages + 2 + 3), and per the FR-017 table partial
  outranks stale; nothing claimed `complete`. Follow-up Sync: 4.4 s,
  `complete`, 402 instances / 402 unique; chat found X and Y; both
  confirmed on the Discogs account. No server restart between steps.*
- [x] **SC-004 — scan regression**: run the 022/026 quickstart flow
  (photo scan → selected match + alternatives → add; manual search;
  other pressings; duplicate double-confirm) inside the tabbed page.
  *Owner-validated 2026-11-21 (block B, same server run as the SC-003
  re-validation; the add leg = SC-003's two adds through the tabbed
  page). Two observations: (1) the duplicate badge read "2 copies (incl.
  this session)" for ONE owned copy — the same-process sync had absorbed
  the session's add and the overlay counted it again → fixed as replay
  addendum 5 / FR-018 (count reconciled by instance_id); (2) "Show other
  pressings" rows look repeated next to "Other possibilities" — distinct
  releases by construction (dedup by release_id), sibling pressings that
  look alike → owner-deferred UX follow-up (group by master, emphasize
  country/catno/format), NOT fixed in 028.*
- [x] **SC-005 — sync single-occupancy**: with a sync running, tap Sync
  again (ideally from a second device) → clear "already running"
  refusal, no second run. Also ask chat to sync during the run → honest
  `already_running` answer.
  *Owner-validated 2026-11-20 (session `20261120-214751Z`, block C).*
- [x] **SC-006 — scan during sync**: with a sync running, complete a
  photo scan; it succeeds (slower is fine) and the page indicates the
  sync is in progress.
  *Owner-validated 2026-11-20 (same session). Going one step further —
  ADDING the scanned record mid-sync — surfaced replay addendum 4
  (FR-017), see SC-003.*
- [ ] **SC-007 — container parity**: run `docker compose --profile
  collection up collection-agent` unchanged; the tabbed page serves on
  :8022, chat works, sync-from-page works, exit behavior unchanged.
- [x] **Busy signal**: send a chat message while a turn is in flight
  (second device) → clear busy refusal, conversation not corrupted.
  *Owner-validated 2026-11-20 (block A).*
- [x] **Plan expiry**: get a move card, then send another message
  instead of confirming → card cleared, nothing written; confirm from a
  stale card (if reproducible) → refused.
  *Owner-validated 2026-11-20 (block A, phone + laptop).*
- [x] **Reload**: reload the page mid-conversation → transcript and any
  pending card reappear (server-side history).
  *Owner-validated 2026-11-20 (block A).*
