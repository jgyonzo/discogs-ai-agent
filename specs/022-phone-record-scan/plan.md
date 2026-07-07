# Implementation Plan: Phone Record Scan — Load Physical Records into the Discogs Collection

**Branch**: `022-phone-record-scan` | **Date**: 2026-07-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/022-phone-record-scan/spec.md`

## Summary

Add a `scan` HTTP mode to the existing `collection-agent` component: a
phone-friendly single-page UI (served over the home LAN) photographs a
record; the server extracts identification evidence with a
settings-configured OpenAI vision model (through the existing
`_build_llm_client` seam, so 021 tracing applies), resolves candidates
against live Discogs `GET /database/search` in precision order
(barcode → catno+label → artist+title, with a free-text manual
fallback), marks duplicates from the local snapshot, and — only on an
explicit owner tap (double-tap for duplicates, enforced server-side) —
performs the live write
`POST /users/{u}/collection/folders/{fid}/releases/{rid}` through the
existing rate-governed `DiscogsClient`, then marks the snapshot stale.
Every scan-cycle outcome is appended to a per-session JSONL journal
under the gitignored `data/`. Component-local change only; ~all
technical decisions in [research.md](research.md) R1–R10.

## Technical Context

**Language/Version**: Python ≥3.12 (existing `collection-agent` toolchain)
**Primary Dependencies**: existing — `openai`, `httpx`, `pydantic` v2,
`pydantic-settings`, `rich`, `langsmith`; new — `fastapi`, `uvicorn`,
`python-multipart` (R1)
**Storage**: existing local snapshot `collection-agent/data/snapshot.json`
(read for duplicate status; `mark_stale()` after adds); new append-only
JSONL session journals under `collection-agent/data/scan-sessions/` (R5).
Both inside the gitignored `data/`.
**Testing**: pytest (`cd collection-agent && pytest`), 223 tests at
branch point; FastAPI `TestClient` + `FakeDiscogsClient` + `StubLLM`
stubs; zero live API calls (R10)
**Target Platform**: owner's laptop (macOS/Linux) serving plain HTTP on
the home LAN; phone browser (iOS Safari / Android Chrome) as client
**Project Type**: single component extension — new `scan` subpackage +
CLI subcommand inside `collection-agent`
**Performance Goals**: photo → candidates on screen < 15 s (SC-001);
add flow ≤ 3 taps after photo (SC-003); all Discogs traffic within the
60 req/min authenticated budget via the existing governor (FR-015)
**Constraints**: no live API calls in tests (SC-008); no secrets to the
browser (FR-017); write only on explicit human confirmation, second
confirmation for duplicates enforced server-side (FR-007/009, R9);
displayed candidate data verbatim from Discogs responses (FR-005);
image uploads capped at 10 MiB default (FR-016, R6)
**Scale/Scope**: single owner, one phone, batch sessions of dozens of
records; collection scale 300–1k records (017 target)

## Constitution Check

*GATE: evaluated against Constitution v1.2.1. Components touched:
**`collection-agent` only** (plus its own `pyproject.toml` and tests).*

- **I. Layered, contract-first data architecture** — PASS (not
  engaged): no ETL layer, no DuckDB, no published-contract change. The
  feature's own external surfaces are contract-documented in
  `contracts/` (scan HTTP API, journal schema, Discogs-consumption
  amendment).
- **II. Streaming, bounded-memory processing** — PASS (not engaged):
  no XML/dump processing. Uploads are size-capped before buffering
  (FR-016).
- **III. Reproducible runs with manifest & logs** — PASS (not engaged
  as written — it governs pipeline executions): the analog is honored
  anyway via the append-only per-session scan journal (FR-013),
  reviewable after interruption.
- **IV. Data quality gates** — PASS (not engaged): no layer outputs.
  Snapshot integrity is preserved by *not* appending sync-shaped
  records the sync never wrote (R4) and using the documented
  `mark_stale()` transition.
- **V. Agent-friendly analytics surface** — PASS (not engaged): the
  DuckDB surface is untouched.
- **VI. Components & Contracts** — PASS: the feature lives entirely in
  `collection-agent` (the component that owns the live-collection
  domain); no new component; no cross-component imports (the scan page
  is a self-contained static file, explicitly NOT the `frontend`
  component; `frontend`/`agent`/`etl` untouched); dependencies added to
  the component's own `pyproject.toml`. The scan server runs end-to-end
  with no other component's process.
- **VII. Implementation Discipline** —
  - (a) PASS: every new knob is a `Settings` field with an env alias
    (vision model, host, port, folder id, journal dir, image cap,
    candidate cap — R2/R5–R9); no hardcoded model names, paths, ports,
    or caps in runtime code.
  - (b) PASS (not engaged): the one new prompt (`scan_vision.md`)
    contains no catalog-schema prose — it describes reading a
    photograph; the `{schema_context_block}` rule applies to catalog
    schema, which this feature never touches.
  - (c) PASS (not engaged): no read-only-mounted resources; snapshot
    writes go through the store's existing atomic write path.
- **Secrets** — PASS: token/API key stay server-side, sourced from
  `.env` via `Settings`; never rendered into the page or its API
  responses (FR-017).
- **Scope guardrails** — PASS: ETL v1 and agent v1 guardrails untouched.
- **Development workflow** — this plan includes the Constitution Check;
  phases commit before the next per the spec-driven flow; single-PR
  convention (feature + post-merge CLAUDE.md state in one PR, owner
  decision 2026-07-07).

**Post-Phase-1 re-check**: design artifacts (data-model, contracts,
quickstart) introduce no new violations — PASS.

**Deliberate risk recorded (not a constitution violation)**: the scan
page has no authentication on the trusted home LAN (spec assumption;
R8). Anyone on the LAN who finds the port can trigger collection adds.
Accepted for v1 by the spec; exposure beyond the LAN is an owner
decision and out of scope.

## Project Structure

### Documentation (this feature)

```text
specs/022-phone-record-scan/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — decisions R1–R10
├── data-model.md        # Phase 1 — scan-domain entities & states
├── quickstart.md        # Phase 1 — run & validate instructions
├── checklists/
│   └── requirements.md  # Spec quality checklist (done)
├── contracts/
│   ├── scan-api.md                        # HTTP API + page behavior contract
│   ├── scan-journal-schema.md             # JSONL journal contract
│   └── amendment-017-discogs-consumption.md  # new Discogs endpoints consumed
└── tasks.md             # Phase 2 (/speckit-tasks — not created by plan)
```

### Source Code (repository root)

```text
collection-agent/
├── pyproject.toml                      # + fastapi, uvicorn, python-multipart
├── src/collection_agent/
│   ├── settings.py                     # + 7 scan settings fields (R2, R5–R9)
│   ├── cli.py                          # + `scan` subparser, _cmd_scan
│   ├── discogs/
│   │   └── client.py                   # + search_releases, add_to_collection
│   ├── prompts/
│   │   └── scan_vision.md              # vision evidence-extraction prompt
│   └── scan/                           # NEW subpackage
│       ├── __init__.py
│       ├── models.py                   # ScanEvidence, Candidate, DuplicateStatus,
│       │                               #   ScanCycleOutcome, API request/response models
│       ├── vision.py                   # extract_evidence(llm, settings, image_bytes, mime)
│       ├── search.py                   # precision ladder, dedup, cap, duplicate overlay
│       ├── session.py                  # ScanSession: seen-candidate allowlist,
│       │                               #   session-added set, log entries
│       ├── journal.py                  # append-only JSONL session journal
│       ├── server.py                   # create_app(...) FastAPI factory + routes
│       └── static/
│           └── index.html              # self-contained phone page (no build step)
└── tests/
    ├── conftest.py                     # settings fixture gains scan kwargs
    ├── fixtures/
    │   ├── discogs_payloads.py         # + search-result & add-instance builders
    │   └── fake_client.py              # + search_releases / add_to_collection
    ├── unit/
    │   ├── test_scan_models.py
    │   ├── test_scan_vision.py         # incl. invalid-JSON / empty-evidence
    │   ├── test_scan_search.py         # ladder, fallback, dedup, cap, verbatim audit
    │   ├── test_scan_journal.py
    │   └── test_discogs_client_scan.py # new client methods via mock transport
    └── integration/
        └── test_scan_server.py         # TestClient end-to-end: scan→confirm→add,
                                        #   duplicate double-confirm, size cap,
                                        #   no-match→manual search, journal, secrets-absent
```

**Structure Decision**: single-component extension. The scan feature is
a new `scan/` subpackage inside `collection_agent` plus small additions
to four existing files (`settings.py`, `cli.py`, `discogs/client.py`,
`pyproject.toml`). No other component is touched; the static page ships
inside the package (served by FastAPI from the installed package
directory) so the component stays self-contained.

## Design overview (Phase 1 summary)

**Request flow** (normative details in `contracts/scan-api.md`):

1. `GET /` → static page. Page state machine: *camera-ready* →
   *identifying* → *candidates* → *confirming* → back to *camera-ready*.
2. `POST /api/scan` (multipart photo) → size gate → vision extraction
   (`ScanEvidence`) → precision-ladder search → candidates with
   duplicate overlay → `{scan_id, evidence_summary, candidates[],
   more_matches, message}`. Empty evidence or zero candidates returns
   an honest no-match message with `candidates: []` (page offers manual
   search). Vision/Discogs failures map to explicit error payloads —
   never fabricated candidates.
3. `GET /api/search?q=…` → same candidate pipeline from free text
   (skips vision), same response shape.
4. `POST /api/add` `{scan_id, release_id, confirm_duplicate}` →
   release_id must be in the session's seen-candidates allowlist;
   duplicate-status releases require `confirm_duplicate=true` else the
   server answers `needs_duplicate_confirmation` and does NOT write;
   otherwise the live add runs, journal logs `added`, snapshot is
   marked stale, session-added set updated.
5. `POST /api/skip` `{scan_id, release_id?}` → journal logs `skipped`.
6. `GET /api/session` → session log entries (newest first) for the
   on-page log.

**Duplicate status** (FR-009/010, R4): computed per candidate as
`in_collection(count)` / `not_in_collection` / `unknown(reason)` from
snapshot presence + completeness + the in-memory session-added set.

**Session** (R9): one `ScanSession` per server run — journal file id,
monotonically increasing `seq`, seen-candidate release_id allowlist,
session-added release_ids, in-memory log entries.

**Failure honesty** (FR-012, edge cases): every error path returns a
typed, user-readable payload and (for completed cycles) a journal
entry; the page never invents content and always lands back on a state
with a clear next action.

## Complexity Tracking

No constitution violations to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
