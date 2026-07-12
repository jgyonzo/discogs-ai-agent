# Quickstart: Scan Release & Master Selection (026)

## Prerequisites

- `collection-agent` set up per its README (`.env` with
  `DISCOGS_USER_TOKEN`, `OPENAI_API_KEY` for photo scans; a synced snapshot
  makes duplicate badges meaningful).
- No new dependencies; no new required configuration. Optional knob:
  `COLLECTION_AGENT_SCAN_VERSIONS_MAX` (default 25).

## Run

```bash
cd collection-agent
uv run collection-agent scan          # serves http://<laptop-lan-ip>:8022
```

Open the page on the phone (same LAN), or use `curl` for the API-level
checks below.

## What changed on the page

1. **Scan a record** (or use manual search). With ≥1 candidate:
   - The top card is the **Selected match** — visually prominent, with a
     "View release on Discogs ↗" link and, when the release has a master,
     a master row: "Master page ↗" link + a **Show other pressings**
     button.
   - Remaining candidates appear under **Other possibilities**, each with
     its own Discogs link and add button, duplicate badges unchanged.
2. **Links** open Discogs in a new tab; the scan page keeps its results —
   come back and add as usual. Links never add; add buttons never navigate.
3. **Show other pressings** fetches the master's versions (one Discogs
   request) and appends them as additional selectable alternatives with
   the same badges/links/add flow. If more versions exist than shown, the
   page says "showing N of T". Failure or an empty result is stated
   honestly; existing results stay usable.

## API-level smoke (optional)

```bash
# manual search → note scan_id, candidates[0].master_id + link fields
curl -s "http://localhost:8022/api/search?q=rumours+fleetwood+mac" | jq \
  '.scan_id, .candidates[0].release_page_url, .candidates[0].master_page_url'

# on-demand versions (use the scan_id + master_id from above)
curl -s "http://localhost:8022/api/master-versions?scan_id=<ID>&master_id=<MID>" \
  | jq '.total_versions, (.candidates | length), .candidates[0].release_page_url'

# gate checks
curl -s "http://localhost:8022/api/master-versions?scan_id=<ID>&master_id=1" \
  | jq .    # → 403 unknown_master (id never offered in this cycle)
```

## Tests

```bash
cd collection-agent && pytest        # all offline; no live API calls
```

## Owner live-validation checklist (SC-001..SC-006)

- [ ] **SC-001** — Scan a record that yields multiple candidates: the
      selected release and (when present) its master row are visible in
      the initial results with no extra taps.
- [ ] **SC-002** — In one live session, tap EVERY offered release/master
      link and verify each opens the exact Discogs page for the id the
      API returned (spot-check `release_page_url`/`master_page_url`
      against `release_id`/`master_id` in the response).
- [ ] **SC-003** — On the phone: open a Discogs link, background the scan
      page, return — results intact, an add still works.
- [ ] **SC-004** — Add an alternative (one from the original list AND one
      from on-demand pressings): confirmation steps identical to adding
      the selected release; duplicate confirmation still triggers on a
      known-duplicate.
- [ ] **SC-005** — For a record whose exact pressing is missing but whose
      master is represented (024's near-miss class): reach and add the
      correct pressing via "Show other pressings" in a single scan
      session.
- [ ] **SC-006** — Session where the on-demand action is never tapped:
      confirm (server log / LangSmith / request count) zero
      `/masters/*/versions` requests were issued.
