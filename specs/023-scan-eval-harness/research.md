# Research: Scan Identification Eval Dataset & Harness (023)

All decisions grounded in the merged 017/021/022 code on `main` at branch point.

## R1 — Where release images come from: re-fetch, don't re-model the snapshot

**Decision**: The builder derives distinct release_ids from the existing snapshot
(`SnapshotStore.load()` → `records[].release_id`, deduplicated) and calls the
already-contracted `GET /releases/{id}` (`DiscogsClient.get_release`) per
release, consuming the response's `images[]` array (`type` = `primary` |
`secondary`, `uri`, `uri150`) — a field the sync fetches today and discards.
The snapshot schema is **not** extended to store image URIs.

**Rationale**: Storing image URIs in the snapshot would bump the snapshot
schema, force a re-sync, and couple an eval-only concern into 017's
snapshot-schema contract — for data that is only needed once, at build time.
Discogs image URIs are also signed/rotating, so persisting them in the snapshot
would store stale links. A fresh `get_release` at build time is one governed
call per release (300–1k calls ≈ 5–17 min inside the 60 req/min budget) and
keeps every existing contract untouched except a fields-consumed delta
(amendment 2 to 017's discogs-consumption contract).

**Alternatives considered**: (a) extend snapshot with `images[]` — rejected
above; (b) scrape release pages — rejected: violates the API-only consumption
contract and its User-Agent/licensing discipline.

## R2 — Downloading image binaries through the governed client

**Decision**: Add `DiscogsClient.download_image(uri) -> bytes | None` that
issues the GET through the existing `_request` path with the **absolute** image
URI (httpx sends absolute URLs as-is, ignoring `base_url`). 404/403 on an
expired signed URI returns `None` (caller records a failed download; the
builder can re-fetch the release for fresh URIs on resume). Response
content-type is checked to start with `image/`.

**Rationale**: `_request` gives the retry/backoff/429 policy and the
governor for free. The image CDN (`i.discogs.com`) does not send
`X-Discogs-Ratelimit*` headers — verified against `ratelimit.py`:
`after_response` leaves governor state **unchanged** when headers are absent,
so CDN responses neither corrupt nor reset the API budget signal; pacing
remains driven by the interleaved API responses. Auth header + settings
User-Agent ride along harmlessly (Discogs requires a real User-Agent for image
fetches).

**Alternatives considered**: a second bare `httpx.Client` for images —
rejected: duplicates retry/UA plumbing and escapes the governor for no
benefit.

## R3 — Dataset layout & manifest

**Decision**: `settings.eval_dataset_dir` (default
`collection-agent/data/eval/discogs-images/`) containing image files named
`{release_id}_{kind}{ordinal}.{ext}` (e.g. `724223_secondary1.jpg`) and an
append-only `manifest.jsonl`: one `run_header` line per build invocation
(snapshot completeness + synced_at, built_at, settings echo) and one `release`
line per processed release (status `downloaded` | `no_images` | `failed`, plus
per-image entries). Resume = load manifest, skip release_ids that already have
a `release` line with status `downloaded`/`no_images`; a torn trailing line
(crash mid-append) is tolerated and ignored. Full schema in
`contracts/eval-dataset.md`.

**Rationale**: JSONL append-only matches the component's journal discipline
(022) and makes resume trivial and corruption-tolerant (FR-005, SC-007).
Filename embeds the ground truth for human browsing, but the **manifest** is
the authoritative label source (FR-004) — filenames are never parsed for
truth.

## R4 — Licensing containment

**Decision**: Everything lands under `collection-agent/data/eval/…`, which the
repo-root `.gitignore` already ignores via its blanket `data/` rule (verified:
the rule is unanchored, so it matches `collection-agent/data/` — this is what
already keeps `snapshot.json` and scan journals out of git). A `NOTICE.txt` is
written into the dataset root stating images are uploader-copyrighted,
local-only, never redistributed (FR-006). A guard test statically asserts (a)
the `.gitignore` `data/` rule is present and not negated for collection-agent
paths, and (b) all three new directory defaults resolve under
`collection-agent/data/` — fully offline, in the spirit of 022's grep-guard
tests.

**Alternatives considered**: `git check-ignore` subprocess in the test —
rejected: shells out and depends on git presence/cwd; the static assertion
pins the same invariant.

## R5 — CLI surface: two subcommands on the existing entry point

**Decision**: `python -m collection_agent eval-dataset [--limit N]
[--images-per-release N]` (builder) and `python -m collection_agent eval-run
--source discogs|retained [--limit N]` (harness), implemented in a new
`collection_agent/eval/` package and wired in `cli.py` beside
chat/sync/status/scan. Both are lazy-imported like the other subcommands so
`status` stays cheap.

**Rationale**: 017 fixed the component's surface as a CLI; every operation is
"reachable via the documented CLI" (constitution workflow analog). A separate
scripts directory would orphan the code from Settings/tests and invite drift.

## R6 — Read-only guarantee for the harness (spec FR-016, VII(c) analog)

**Decision**: The harness builds a real `DiscogsClient` (search needs it) but
the `eval/` package is forbidden — by an AST guard test — from referencing the
client's write methods (`add_to_collection`, `create_folder`,
`move_instance`) or importing `scan.journal` / `scan.session` (so it can never
journal a scan cycle or feed the allowlist). Duplicate status is supplied by
the existing `pending_duplicate_checker` (explicit `unknown`), which keeps
`find_candidates`' signature satisfied without loading snapshot overlay state.

**Rationale**: 022 R9 put the write gate in code, not prompts; the same
static-enforcement precedent (013→014: deterministic over steering) applies
here. Guard-testing the absence of write references makes SC-006 structural.

## R7 — Harness pipeline fidelity (spec FR-011)

**Decision**: Per image the harness calls exactly the production seams:
`extract_evidence(llm, settings, image_bytes, mime)` from `scan/vision.py`
(with the LLM client from `cli.py::_build_llm_client`, so 021's LangSmith
wrapping and the `scan_vision_timeout_s` cap apply unchanged) and then
`find_candidates(client, settings, evidence, pending_duplicate_checker)` from
`scan/search.py`. Nothing is monkeypatched, subclassed, or reimplemented; the
scan HTTP server is not involved (its concerns — upload caps, supersession,
journal, allowlist — are session mechanics, not identification).

**Rationale**: The unit under measurement is vision + ladder. Driving the HTTP
server instead would drag in a running event loop and journal writes the
read-only rule forbids, while measuring the same two calls. MIME is derived
from the file extension (the builder records it; retention preserves the
upload's extension).

## R8 — Results & summary shape

**Decision**: Each run writes to
`settings.eval_results_dir/<run_id>/` (`run_id` =
`YYYYMMDD-HHMMSSZ-<source>`): `results.jsonl` (one record per image, appended
incrementally so a crashed run keeps its partial results) and `summary.json`
(written at the end; also rendered as a rich table). Outcome taxonomy per
image: `hit` (truth in candidates; rank recorded, rung = last rung tried) |
`miss` | `no_evidence` (vision returned empty evidence) | `error`
(`vision_error` | `discogs_error`, message recorded) | `unlabeled` (retained
source only; excluded from rate denominators, counted). Summary reports
identified/top1 rates over (hit+miss+no_evidence), per-rung hit counts,
error/unlabeled/billable-call counts, and `limited: true` when `--limit`
truncated the source. Sum invariants are unit-tested (spec FR-014).

**Rationale**: Mirrors the journal's honest-outcome discipline; JSONL matches
R3; separating `no_evidence` from `miss` isolates vision failures from ladder
failures — the distinction that made 022's replay addendum 1 diagnosable.

## R9 — Retention mechanics (spec FR-007..010)

**Decision**: New `scan/retention.py::PhotoRetainer`, constructed in
`create_app` only when `settings.scan_retain_photos` is true (off → the hook
is `None` and the request path is byte-identical to 022). In `POST /api/scan`,
immediately after the size gate the retainer saves the upload as
`<retention_dir>/<session_id>/pending-<n>.<ext>` (extension from the upload's
content type); once the cycle gets its `scan_id` (all three terminal paths
that assign one), the file is renamed — atomic same-directory `os.rename` — to
`<scan_id>.<ext>`. Vision-error/superseded paths never get a scan_id, so their
`pending-*` files simply remain: permanently unlabeled, honestly counted by
the harness. Any retention I/O failure logs one loud server-side warning and
the scan proceeds (spec's deliberate contrast with the loud-500 journal rule).
Ground truth is joined lazily by the harness: retention file `<scan_id>.<ext>`
+ journal line `outcome=added, scan_id=…` → labeled with that `release_id`;
anything else (skipped, no_match, failed, auto-closed, pending) → unlabeled.

**Rationale**: Saving before identification satisfies FR-008 even when vision
dies; the rename gives the journal-joinable key without writing anything new
into the journal (whose schema stays untouched — no contract amendment
needed). The retainer object keeps `server.py` changes to a few flag-gated
lines.

## R10 — Test strategy (offline, 022 precedent)

**Decision**: `FakeDiscogsClient` grows scriptable `get_release` image
payloads and a byte-serving `download_image`; vision is a scripted stub LLM
returning canned JSON (existing pattern from `test_scan_vision.py`).
Integration test `test_eval_harness.py` builds a tmp dataset via the fake,
runs the full harness loop, and asserts results + summary invariants.
Retention is covered at unit level (retainer semantics incl. failure-path
warning) and through `test_scan_server.py` TestClient cases (flag off/on).
No test touches the network, real `data/`, or the real `.env` (existing
`settings` fixture gains tmp overrides for the three new dirs).

**Rationale**: Keeps the suite's zero-live-calls property (spec FR-018) while
covering all pure logic; live accuracy numbers are owner-run by design
(quickstart checklist).
