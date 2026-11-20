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
