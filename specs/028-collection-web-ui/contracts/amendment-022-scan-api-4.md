# Amendment: 022 scan-api contract — delta 4 (028-collection-web-ui)

Amends `specs/022-phone-record-scan/contracts/scan-api.md`. Fourth
amendment (after 024's exact-catno ordering, 025's evidence gate
semantics, 026's link fields + selected semantic + versions endpoint).

## Delta — `GET /` serves the tabbed collection page

- `GET /` now serves a three-tab page (Scan | Chat | Collection) from the
  same static file. The **Scan tab** preserves the 022/026 page behavior
  functionally unchanged: photo scan, manual search, selected match +
  master row + alternatives, on-demand other pressings, duplicate
  double-confirmation, add/skip, session log, supersede semantics.
- **Every `/api/*` endpoint defined by this contract is unchanged** —
  request shapes, response shapes, status codes, gate order, journal
  semantics, generation/supersede behavior, and the error envelope are
  byte-for-byte the 022/024/025/026 contract. 028 adds sibling endpoints
  (`/api/chat*`, `/api/collection/status`, `/api/sync`) documented in
  `specs/028-collection-web-ui/contracts/web-ui-api.md`; none of them
  touches scan state except as already contracted (e.g. a chat-visible
  snapshot going stale via an add was already true in 022).
- Page disciplines carry to the whole tabbed page: self-contained static
  file, no secrets on the wire, server-built links only, `target="_blank"
  rel="noopener noreferrer"`, link anchors structurally separate from
  action buttons. The existing grep-guard tests keep applying to the same
  file path.
- The serving process may now also run a background sync thread; scan
  endpoints remain available during it (shared Discogs rate budget —
  slower is in-contract, unavailable is not).

## Delta — duplicate overlay counts a synced session add once (replay addendum 5, FR-018)

Amends 022 data-model `DuplicateStatus.copies` ("snapshot instance count
+ session adds") — the response SHAPE is unchanged; only the count's
arithmetic is corrected:

- `copies` = snapshot instances of the release + session adds of the
  release **not yet in the snapshot**. A session add is "in the
  snapshot" iff the `instance_id` Discogs returned for it (recorded on
  the session's `added` outcome since 022) is the `instance_id` of a
  snapshot record. Adds with no recorded `instance_id` are always
  counted (conservative — the pre-amendment arithmetic).
- Unchanged: `state` (`in_collection` whenever a session add exists,
  regardless of snapshot state), `added_this_session` (true iff the
  release was added in this server run), `reason`, every degradation
  rule, and the `/api/add` duplicate double-confirmation gate.
- Why now: 028's same-process page sync made "add → Sync → scan the
  same record again" the standard flow; the old sum then counted the
  absorbed add twice ("2 copies" for one owned copy).
