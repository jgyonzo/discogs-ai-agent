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
- [ ] **SC-003 — stale → sync → fresh, one process**: add a record via
  the Scan tab (snapshot goes stale, banner appears) → tap Sync → watch
  progress to completion → status reads `complete` with updated counts →
  ask chat about the newly added record; it answers from the fresh
  snapshot. No server restart anywhere.
- [ ] **SC-004 — scan regression**: run the 022/026 quickstart flow
  (photo scan → selected match + alternatives → add; manual search;
  other pressings; duplicate double-confirm) inside the tabbed page.
- [ ] **SC-005 — sync single-occupancy**: with a sync running, tap Sync
  again (ideally from a second device) → clear "already running"
  refusal, no second run. Also ask chat to sync during the run → honest
  `already_running` answer.
- [ ] **SC-006 — scan during sync**: with a sync running, complete a
  photo scan; it succeeds (slower is fine) and the page indicates the
  sync is in progress.
- [ ] **SC-007 — container parity**: run `docker compose --profile
  collection up collection-agent` unchanged; the tabbed page serves on
  :8022, chat works, sync-from-page works, exit behavior unchanged.
- [ ] **Busy signal**: send a chat message while a turn is in flight
  (second device) → clear busy refusal, conversation not corrupted.
- [ ] **Plan expiry**: get a move card, then send another message
  instead of confirming → card cleared, nothing written; confirm from a
  stale card (if reproducible) → refused.
- [ ] **Reload**: reload the page mid-conversation → transcript and any
  pending card reappear (server-side history).
