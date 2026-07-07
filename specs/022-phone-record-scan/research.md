# Research: Phone Record Scan (022)

All plan-phase unknowns from the spec's Assumptions section, resolved.
Grounded in a code survey of `collection-agent/src/collection_agent/`
(settings, discogs client + governor, snapshot store/sync, cli, agent,
tests) and `docs/discogs_api_reference.md`.

## R1 — HTTP serving library

**Decision**: FastAPI + uvicorn (+ `python-multipart` for the photo
upload), added to `collection-agent/pyproject.toml`. The app is built by
an `create_app(...)` factory taking injected collaborators (settings,
LLM client, Discogs client, snapshot store, journal) so tests drive it
with `fastapi.testclient.TestClient` and stubs — no sockets, no live
calls.

**Rationale**: FastAPI is the repo's HTTP idiom (`agent/` serves its
API with it), it parses multipart uploads and pydantic request/response
models natively — both load-bearing here — and the injectable-app-factory
pattern matches the component's existing seams (`DiscogsClient(transport=…)`,
`Agent(llm_client=…)`). uvicorn runs only in `_cmd_scan`; the test suite
never starts a socket server.

**Alternatives considered**:
- *stdlib `http.server`* — no dependency cost, but hand-rolled multipart
  parsing, threading, and error mapping; rejected as more code and more
  failure surface than the dependency it avoids.
- *Flask* — equivalent capability but a second HTTP idiom in the repo;
  rejected for consistency.
- *Reusing `agent/`'s FastAPI service* — constitutionally forbidden
  (Principle VI: no cross-component imports; `agent/` must not gain
  Discogs-token capabilities).

## R2 — Vision model + extraction call shape

**Decision**: New settings field `collection_agent_vision_model`
(alias `COLLECTION_AGENT_VISION_MODEL`), default `gpt-4o-mini`
(vision-capable; same default family as the existing
`collection_agent_model`). The extraction call reuses the existing
injectable LLM seam — `cli.py::_build_llm_client(settings)` — so
LangSmith tracing (021) wraps the vision call for free and test stubs
are never wrapped. Call shape: one `chat.completions.create` with the
photo as a base64 `data:` URL image content part plus a prompt from
`prompts/scan_vision.md`, `response_format={"type": "json_object"}`;
the reply is validated into a `ScanEvidence` pydantic model
(all fields optional; empty evidence is a legal outcome, never an
error). The prompt instructs: transcribe only what is legible; never
guess; omit unreadable fields.

**Rationale**: gpt-4o-mini matches the component's cost posture and is
the same provider/SDK already in the loop; per repo feedback, live
pricing shifts — the owner can repoint the env var without a code
change (Constitution VII(a): no hardcoded model identifiers — the
default lives in `Settings`, the runtime reads only the settings
field). `json_object` + pydantic validation gives structured evidence
without adding a tool-calling loop for a single-shot extraction.

**Alternatives considered**:
- *Client-side barcode decoding (JS ZXing) + OCR* — new static-page JS
  dependency, brittle on center labels; the vision model reads barcodes'
  printed digits, label text, and covers with one mechanism. Rejected
  for v1 (spec keeps fingerprint/CV approaches out of scope).
- *OpenAI Responses API* — the component's loop already standardizes on
  `chat.completions`; no reason to introduce a second call style.
- *Structured Outputs (`response_format` json_schema)* — stricter, but
  `json_object` + pydantic re-validation is the lighter idiom and the
  fields are all-optional anyway; revisit if extraction drift shows up
  in live validation.

## R3 — Discogs search + add-to-collection (client methods)

**Decision**: Two new `DiscogsClient` methods, both through the
existing `_request`/`_get_json` helpers so auth headers and the
rate-limit governor apply unchanged:

- `search_releases(params) -> dict` — `GET /database/search` with
  `type=release` plus evidence params (`barcode=` | `catno=` [+
  `label=`] | `artist=` + `release_title=` | free-text `q=`),
  `per_page` from settings. Returns the raw payload (`results` +
  `pagination`).
- `add_to_collection(username, folder_id, release_id) -> dict` —
  `POST /users/{username}/collection/folders/{folder_id}/releases/{release_id}`,
  `raise_for_status()`, returns the created-instance payload
  (`instance_id`, …). Mirrors the existing live-write shape of
  `create_folder`/`move_instance`.

Evidence→search precision ladder (FR-004) lives in scan code, not the
client: barcode → catno(+label) → artist+release_title; a lower rung
runs only if the higher rung is absent or returned zero results.
Candidates are deduplicated by release `id` and capped at the page
size; `pagination.items > shown` drives the "more matches exist" flag.
Candidate display fields come verbatim from search-result fields
(`id`, `title`, `year`, `country`, `format`, `label`, `catno`,
`thumb`/`cover_image`, `uri`) — 019 discipline: no URL or field is ever
constructed; absent fields display as absent.

**Rationale**: the two-helper client seam was built for exactly this;
anything routed through `_request` inherits 429 backoff, retry policy,
and the header-driven governor with zero extra wiring.

**Alternatives considered**: a scan-local httpx client — rejected; it
would bypass the governor and duplicate auth/error policy (FR-015
violation).

## R4 — Snapshot reconciliation after a successful add

**Decision**: `SnapshotStore.mark_stale()` after every successful add
(the existing post-live-write hook), NOT an in-place record append.
Same-session duplicate awareness is handled by the scan session itself:
the server keeps an in-memory set of release_ids added this session and
the duplicate check consults snapshot + that set, so the "second copy
scanned right after the first" edge case is flagged even though the
snapshot is now stale. Duplicate status degrades explicitly (FR-010):
snapshot missing → "unknown (no snapshot)"; snapshot stale → counts
reported as "as of last sync" + session-set overlay.

**Rationale**: a search result cannot fabricate a full
`CollectionRecord` (search lacks enrichment fields; `date_added`,
`folder_id` semantics come from the collection endpoint) — appending a
half-shaped record would put the snapshot in a state `run_sync` never
produces and every downstream consumer would have to tolerate it.
`mark_stale()` is the documented seam (store.py) with exactly this
meaning: "a live write happened; re-sync before trusting counts."
The conversational agent already handles stale snapshots.

**Alternatives considered**: *patch-in the new instance* (like
`patch_moved_instances`) — rejected: moves patch fields that already
exist; adds would invent a record shape sync never wrote. *Trigger a
full re-sync after each add* — rejected: a 60 req/min budget shared
with the next scan's searches; a shelf session would spend its budget
re-syncing instead of scanning.

## R5 — Session journal format & location

**Decision**: Append-only JSONL, one file per server run, at
`collection-agent/data/scan-sessions/<session_id>.jsonl` where
`session_id` is the server-start UTC timestamp (`YYYYMMDD-HHMMSSZ`).
Directory from new settings field `scan_journal_dir` (alias
`COLLECTION_AGENT_SCAN_JOURNAL_DIR`), default
`<component>/data/scan-sessions` — inside the already-gitignored
`data/`. Each line is one completed scan-cycle outcome:
`{ts, seq, outcome: added|skipped|no_match|failed, evidence_kinds,
release_id?, artist?, title?, instance_id?, detail?}`. Writes are
append + flush per event; the file is never rewritten (FR-013). The
page's visible log is served from the in-memory session (backed by the
same entries), newest first.

**Rationale**: JSONL is the component's journal idiom (sync's resumable
journal), append-only survives interruption by construction, and one
file per server run matches the spec's session definition.

**Alternatives considered**: single rolling journal file — harder to
review "this sitting" after the fact; SQLite — over-engineered for an
append-only log the owner reads.

## R6 — Image size cap

**Decision**: New settings field `scan_max_image_bytes` (alias
`COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES`), default **10 MiB**
(10_485_760). Enforced server-side before any vision work (FR-016) with
a clear 413 message; the page also states the cap on failure. No
client-side resizing in v1 (keeps the page dependency-free); phone
JPEGs (~2–6 MB) fit comfortably under the cap and under the vision
API's payload limit.

**Alternatives considered**: canvas-based client resize before upload —
cuts LAN upload time and vision tokens, but adds page complexity and a
quality-loss failure mode (blurry barcode digits after resize); defer
until live validation shows latency or cost pain.

## R7 — Candidate page size

**Decision**: New settings field `scan_candidates_max` (alias
`COLLECTION_AGENT_SCAN_CANDIDATES_MAX`), default **8**. Discogs is
queried with a matching `per_page`; `pagination.items` beyond the cap
sets `more_matches=true`, which the page renders as "N more matches on
Discogs — refine with manual search" (FR-006, edge case: generic
self-titled albums).

**Rationale**: one phone screenful; precision-first search order means
the right pressing is almost always in the first few results when
evidence is strong, and manual search is the designed escape hatch when
it isn't.

## R8 — Server bind & port; page security posture

**Decision**: New settings fields `scan_host` (alias
`COLLECTION_AGENT_SCAN_HOST`, default `0.0.0.0`) and `scan_port`
(alias `COLLECTION_AGENT_SCAN_PORT`, default `8022`); CLI flags
`--host/--port` on the `scan` subcommand override settings at runtime
(argparse > env, same pattern as existing subcommand flags). Plain
HTTP on the trusted home LAN (spec assumption); camera capture uses
`<input type="file" accept="image/*" capture="environment">`, which
works on non-secure origins. No page auth in v1 — recorded risk: anyone
on the LAN who finds the port can trigger collection adds; acceptable
per the spec's single-occupant-LAN assumption, revisiting is an owner
decision. Secrets never reach the browser: the page receives only
candidate data and outcomes; token and API key live server-side only
(FR-017). The startup banner prints the LAN URL(s) to open on the
phone (best-effort local-IP detection, stdlib only).

## R9 — Write gating & folder validation

**Decision**: The write path is HTTP `POST /api/add`, reachable only
from an explicit tap on a specific rendered candidate plus a
confirmation tap (and a second confirmation when duplicate-marked —
enforced server-side: an add for a duplicate-status release without
`confirm_duplicate=true` is rejected with a "needs second confirmation"
response, so a UI bug cannot silently double-add). No LLM output can
reach the write path: the vision step produces evidence only, and the
add endpoint takes a `release_id` that must be one the server itself
returned as a candidate this session (server-side allowlist of
session-seen candidate ids). This is 017's gate translated to HTTP:
the pipeline proposes, the human's tap executes. Target folder: the new
settings field `scan_target_folder_id` (alias
`COLLECTION_AGENT_SCAN_FOLDER_ID`, default `1` = Uncategorized) is
validated live against `client.get_folders()` at server startup
(organize.py discipline: never trust the snapshot for writes) — fail
fast with a config error if the folder doesn't exist.

## R10 — Testing strategy

**Decision**: Follow component conventions exactly — no live API calls:
- `FakeDiscogsClient` (tests/fixtures/fake_client.py) grows
  `search_releases` (replaying new `discogs_payloads.py` builders for
  search results/pagination) and `add_to_collection` (recording adds,
  returning instance payloads, optionally scripted to fail).
- Vision is stubbed with the existing `StubLLM` shape
  (`chat.completions.create` scripted), returning canned JSON evidence;
  invalid-JSON and empty-evidence cases scripted too.
- The FastAPI app is exercised via `TestClient` against the app factory
  with all collaborators injected; `settings` fixture pattern
  (`_env_file=None`, explicit kwargs) extended with the new scan
  fields; journal writes go to `tmp_path`.
- Static guards in the suite: response payloads for candidates must be
  reconstructible verbatim from the fake search payloads (019-style
  no-constructed-values audit as a unit test), and no test may open a
  network socket (TestClient is in-process).
