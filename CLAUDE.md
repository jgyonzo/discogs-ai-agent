<!-- SPECKIT START -->
Repo identity: the GitHub origin is `jgyonzo/discogs-ai-agent`
(renamed from `discogs-analytics-agent` on 2026-07-05).

**No feature is currently in flight.** Most recently merged:
**027-dockerize-collection-agent** (implemented + validated 2026-07-12 —
live validation CLOSED pre-merge, owner-validated 2026-07-12: quickstart
SC-001..SC-006 all recorded, incl. SC-001's phone scan-and-add through the
CONTAINERIZED server (session `20260712-200831Z`, two adds journaled:
releases 36973368/36703081 — found only after applying R8's phone-URL
caveat live: the banner printed the Docker bridge IP 172.19.0.2, the phone
needed the host LAN IP) and the full SC-003 boundary loop: container-sync
SIGINT at 5% enrichment → exit 3 → host-venv resume → 398/398 complete →
containerized status reads complete byte-identically; also image audit
clean, demo-stack service set verified live, empty-token scan exits 2 once
with no restart loop, EOF chat exits 0; tasks T001–T016 ALL complete
incl. owner-only T006/T016) —
the collection-agent packaged as ONE image (all six CLI modes via
`ENTRYPOINT python -m collection_agent`; `CMD ["scan"]` because the CLI's
own default is `chat`, which would hang headless) plus an OPT-IN compose
service: `profiles: ["collection"]`, :8022 published for LAN phones,
`env_file: .env`, exactly one bind mount
`./collection-agent/data:/app/collection-agent/data`. First step toward the
long-term AWS/third-party goal — containerization groundwork ONLY (scoped
out: AWS deploy, multi-tenancy, OAuth, TLS/auth, web chat,
collection_matcher workflows; 022's trusted-LAN no-auth stance unchanged).
`collection-agent` only, zero new deps, ZERO Settings fields, ZERO edits
under `collection-agent/src/`, 9 new tests (536→545).
(1) **Editable install is load-bearing** (research R2): `settings.py:17`
anchors every data-path default to the source location
(`Path(__file__).resolve().parents[2]`), so `pip install -e` at
`/app/collection-agent` makes snapshot/journals/eval dirs resolve INSIDE
the mount — container and host venv read/write the same files
interchangeably, both directions, no env overrides (a non-editable install
silently breaks every default path; guard-pinned via the `pip install -e`
grep). (2) **Demo stack provably untouched**: unprofiled compose service
set == {postgres, agent-api, frontend} pinned by a stdlib-only structural
parse in `tests/unit/test_docker_packaging.py` (no PyYAML; 023
read-repo-root-file precedent), plus profile/isolation/no-restart/
Dockerfile-hygiene/.dockerignore guards — guard sensitivity demonstrated
red before commit. (3) **Failure posture**: deliberately NO `restart:`
policy (scan startup validates the Discogs folder LIVE and exits 2; a
restart policy would retry-loop the live API — FR-010), NO healthcheck, NO
depends_on either direction. (4) **Hygiene**: image = pyproject/src/README
only; `.dockerignore` excludes `data/` (32 MB personal/licensed content),
`.env`, `.venv/` — build context is KB-scale; secrets arrive ONLY as
process env via compose `env_file` (agent-api pattern; pydantic-settings
missing-env_file tolerance means no `.env` file exists in-container).
One-off modes: `docker compose run --rm collection-agent
<sync|status|chat|eval-*>` (run auto-activates the profile; TTY for chat;
exit codes 0/1/2/3 verbatim). Artifacts:
`specs/027-dockerize-collection-agent/` (spec, plan, research R1–R10,
data-model, quickstart + owner checklist, tasks T001–T016, contracts:
`docker-packaging.md` — a NEW contract; nothing amended). Known follow-up
candidates recorded there: uv.lock-frozen image builds + registry/CI
(research R10, for the AWS feature), Linux-host file-ownership handling
(R9).

Prior feature:
**026-scan-release-selection** (PR #16, merged to main 2026-07-12 —
live validation CLOSED pre-merge, owner-validated 2026-07-12:
quickstart SC-001..SC-006 all recorded, incl. SC-005's single-session
wrong-pressing recovery via the on-demand fetch and SC-006's
zero-versions-requests audit; the two replay fixes below were found
DURING this validation) —
the scan page's results reshaped from a flat candidate list into a
**Selected match** + master + alternatives view with real Discogs
links and an owner-invoked "other pressings" fetch (closes 024's
measured "right album, wrong pressing" miss class at pick time).
`collection-agent` only, zero new deps, ONE new Settings field
(`COLLECTION_AGENT_SCAN_VERSIONS_MAX`, default 25 = per_page AND
display cap of the single versions request), ~44 new tests (492→536).
Two same-day owner-replay fixes rode the PR: 022 replay addendum 3 /
FR-024 (cancelling a card's add-confirm step backs out that card only —
it used to journal `skipped` and reset the whole scan; "None of these"
stays the only skip gesture) and 026 replay addendum 1 / FR-012
sharpened + FR-015 (empty on-demand result says WHICH empty:
all-versions-already-shown vs none-found, surfaced in the button +
status line — a no-change tap never renders as success; both messages
test-pinned).
(1) **Selected/alternatives presentation** — `candidates[0]` IS the
selected release (documented contract semantic, NOT a ranking change;
ladder + 024 exact-catno re-rank already order best-first); master
identity = the candidate's own title + a master page link, NO
`get_master` call ever (R2 — default view adds zero requests, SC-006
test-pinned); one shared card renderer ⇒ photo scan, manual search,
and on-demand pressings render identically (FR-011/014 structurally
true). (2) **Server-built page links (019 discipline)** — Candidate
gains additive `release_page_url` (always) / `master_page_url` (iff
`master_id`), built ONLY in `tools/common.py` (`release_page_url`
refactored to id-based core + new `master_page_url`; `/release/{` and
`/master/{` shapes grep-guarded to exactly one src site each); the
static page renders only these fields — no hardcoded host, no
client-side URL minting, anchors `target=_blank rel="noopener
noreferrer"` structurally separate from add buttons (all
grep-guarded in `test_scan_page_links.py`). (3) **On-demand master
versions** — NEW `DiscogsClient.get_master_versions` (ONE governed
`GET /masters/{id}/versions`, page 1, per_page=cap, called ONLY by
the endpoint, never in identification/sync/eval/replay) behind NEW
`GET /api/master-versions?scan_id&master_id`: gates in order
(unknown/closed cycle → 409 `superseded`; master_id not carried by a
REGISTERED candidate of that cycle → 403 `unknown_master` — mirror of
the add gate); deliberately does NOT bump the supersede generation
(it extends the current cycle; gen re-checked after the fetch, a
mid-flight close discards with zero state effects);
`candidates_from_versions` maps verbatim (str(released) year, whole
`format`/`label` strings list-wrapped never split, `discogs_uri=None`,
requested master_id) and dedupes against the cycle's registered ids
(the selected release always drops — it's a version of its own
master; all-deduped ⇒ honest empty message); results register into
the SAME session allowlist + cycle title map ⇒ `/api/add`, duplicate
double-confirmation, and the journal work with ZERO changes (adds
journal the cycle's original source; NO journal schema change, the
fetch itself is never journaled — it's a read, like search);
`VersionsResponse.total_versions` = pagination.items verbatim for
"showing N of T" honesty (FR-013). Discogs failure → 502, cycle
stays usable. Eval comparability preserved by construction AND
pinned (R9 test: fixed payload ⇒ byte-identical ordering/fields
minus the two link fields); zero edits under `eval/`, vision prompt
frozen. Artifacts: `specs/026-scan-release-selection/` (spec, plan,
research R1–R9, data-model, quickstart + owner checklist, tasks
T001–T023 ALL complete incl. owner-only T023, contracts:
`amendment-017-discogs-consumption-4.md` — +`GET
/masters/{id}/versions` read, ZERO new writes, +1 req per explicit
tap only; `amendment-022-scan-api-3.md` — link fields + selected
semantic + endpoint + settings). Out of scope kept: `get_master`
metadata fetch, versions pagination/load-more UI, auto-fetch of
versions (owner decision 2026-07-12: on-demand only), ranking
changes.

Prior feature:
**025-eval-replay-barcode-gate** (PR #15, merged to main 2026-07-12 —
live validation CLOSED pre-merge, owner-validated 2026-07-12: quickstart
SC-001..SC-006 all recorded, incl. two byte-identical back-to-back
replays (100% determinism, zero drift), the Cybotron flip as the ONLY
diff line of the gate replay (strict 52.1%→53.2%, catno hits 17→18,
run `20260712-001333Z-replay`), and one physical plausible-barcode
scan) — the two follow-ups from 024's post-merge measured comparison
(2026-07-11 run `20260711-222805Z-discogs` vs the 2026-07-07 baseline:
strict 52.1% vs 56.4%, top-1 37.2%, practical 56.4%, 0 errors — but the
per-image diff showed 20/94 images flipped outcome on vision
nondeterminism alone (8 miss→hit, 12 hit→miss) while ALL of 024's target
catno-drowning cases converted with zero re-rank regressions ⇒
single-run strict-rate comparisons cannot resolve ladder changes; the
run numbers live only in gitignored `data/eval/runs/` and 024's
quickstart SC-002 note). `collection-agent` only, zero new deps, ZERO
new Settings fields (first eval feature with none), ~42 new tests
(450→492).
(1) **Evidence-replay eval mode** — `eval-run --replay <run_id>`
(mutually exclusive w/ `--source`, `--limit` applies): re-runs ONLY the
production search ladder over the evidence recorded in a prior run's
`results.jsonl` (024's `evidence` field = replayability predicate AND
ladder input; the run's own records are ground truth — no images, no
`summary.json` needed, interrupted source runs replayable, replays
themselves replayable). Zero vision calls; no `OPENAI_API_KEY` needed
(the key gate is camera-mode-only; `_build_llm_client` never called ⇒
nothing traced). Evidence re-materialized via `ScanEvidence(**dump)` —
CURRENT normalization deliberately applies, so normalization changes
are A/B-able too (research R2); an evidence dict the current rules
empty (e.g. gated barcode only) becomes an honest replayed
`no_evidence`. Non-replayable records carried through exactly once
each (no_evidence→no_evidence; pre-vision error→error, kind preserved;
unlabeled→unlabeled — also any evidence-less truth-less record;
defensive hit/miss-without-evidence carried + flagged in detail, never
silently re-scored) so denominators match the source run exactly.
Output = a standard run dir `<ts>-replay` (`eval/replay.py` loader +
`harness.py::run_replay` reusing the factored `_execute_run` fsync
loop): summary gains `replay_of`, every record gains `replayed`
true/false, `dataset_snapshot_completeness` None; 023/024 readers
unaffected (all fields default). Miss master buckets recomputed over
the FRESH candidates; truth masters re-resolved from the local dataset
manifest (newest-line-wins; absent/corrupt manifest ⇒ unknown,
retained-source ⇒ always None, never fetched live). Fail-fast
`EXIT_CONFIG` BEFORE any run dir exists: missing run/results.jsonl,
zero records, zero evidence-carrying records (pre-024 runs),
`--replay`+explicit `--source` (its default is now None, resolved to
discogs); torn trailing line tolerated, corrupt mid-file line hard
error (corrupt ≠ interrupted). Invariants 11–14 normative
(vision_calls==0 summary+records; `replay_of` iff `replayed` on every
record, never on camera runs; denominator parity w/ source; hits only
from replayed records). Read-only: the 023 AST guard sweeps
`eval/replay.py` automatically; the source run dir is read-only input
(byte-identical after replay, tested).
(2) **Barcode plausibility gate** (the one pipeline change; measured
cause: vision emitted a 4-digit "barcode" `3070` on
`17859_secondary1.jpeg` (Cybotron), hijacking the highest-precision
barcode rung and suppressing the correctly-extracted catno `D-216` —
a baseline hit): NEW `scan/models.py::BARCODE_PLAUSIBLE_MIN_DIGITS = 8`
(UPC-E/EAN-8 are the shortest real forms; a domain constant like
FR-019's `BARCODE_MIN_DIGITS = 10`, deliberately NOT a Settings knob) —
a `ScanEvidence` model validator ordered AFTER FR-019's catno→barcode
reclassification (so reclassified ≥10-digit values are never gated)
clears sub-8-digit barcodes; the cleared value is NEVER moved to catno
(a short digit run is not definitively a catno — it could hijack that
rung the same way); `evidence_kinds`/journal/eval evidence dumps all
reflect post-gate values (no ghost rung, derived at read time);
8+-digit barcodes byte-identical to 024. One shared normalization site
⇒ phone page + camera eval + replay inherit identically, vision prompt
frozen. The gate is measured BY the replay (integration test: recorded
`3070`+`D-216` evidence replays to a catno-rung hit with no `barcode=`
param ever on the wire). Two pre-existing tests used incidental
sub-8-digit fixture barcodes ("123456"/"12345" testing ladder order /
rung suppression, not plausibility) — fixture values updated to
plausible ones, intent preserved (T016 note).
(3) **024 SC-002 closed honestly** (FR-013): 024's quickstart now
records the inconclusive-aggregate reading (catno hits 17 vs baseline
20, conversions all confirmed) and points at replay as the superseding
instrument. Artifacts: `specs/025-eval-replay-barcode-gate/` (spec,
plan, research R1–R8, data-model, quickstart + owner checklist, tasks
T001–T022 all complete except owner-only T022, contracts: TWO second
amendments — `amendment-023-eval-results-2.md` (replay CLI/layout/
record+summary fields/carry-through semantics/invariants 11–14),
`amendment-022-scan-api-2.md` (gate semantics appended to FR-019/020
normalization)). Out of scope kept: vision prompt changes,
recorded-response offline replay (would stop measuring live Discogs
substring behavior — R8), threshold knob, upper-bound barcode gate,
CI eval integration.

Prior feature:
**024-scan-accuracy-followups** (PR #14, merged to main 2026-07-07 —
quickstart SC-002 fresh eval CLOSED by 025 on 2026-07-11: inconclusive
aggregate under vision variance, all target conversions confirmed;
the one physical short-catno scan remains open) — three
evidence-driven follow-ups from 023's FIRST MEASURED EVAL
(94 images: 56.4% strict / 76% per-release; 14-miss live catno
spot-check 2026-07-07, ~30 read-only lookups). `collection-agent` only,
zero new deps, ~40 new tests (410→450).
(1) **Exact-catno re-rank** (the one pipeline change; measured cause:
Discogs catno search substring-matches, so truth `SUB 15` drowned under
`SUB 150/152`, `FD 006` under `SFDB 006`): catno rung ONLY now fetches
one deeper page (`per_page = max(NEW COLLECTION_AGENT_SCAN_CATNO_
SEARCH_DEPTH default 50, candidates cap)` — still 1 request) and
`scan/search.py` stable-partitions RAW results exact-normalized-catno
first (`normalize_catno` strips ` -./_` + casefolds, 022-FR-019-style;
comma-joined multi-catno any-match; no catno ⇒ never exact) before the
unchanged dedup/cap/verbatim Candidate build; no exact match anywhere ⇒
byte-identical to pre-024; non-catno rungs and manual search untouched.
Fix reaches the phone page and the eval (shared pipeline).
(2) **Evidence in eval results** (022 FR-021's lesson resurfaced: 4/14
spot-checked misses were zero-candidate-cause-unknowable):
`EvalResult.evidence` = `ScanEvidence.compact_dump()` — the journal's
exact shape — on every record where vision produced values (incl.
post-vision discogs_error; absent on unlabeled/no_evidence/pre-vision
errors); misses now diagnosable from results.jsonl alone.
(3) **Same-master near-miss metric** (≥4/14 spot-checked misses were
other pressings of the truth's master — "right album, wrong row"):
manifest `release` lines gain `master_id` (from the already-fetched
payload, 0/absent ⇒ None), NEW `eval-dataset --backfill-masters`
upgrades pre-024 datasets (metadata-only fetches; failures skipped
honestly; masterless releases re-checked next run) via the NEW
normative **newest-line-per-release-wins** manifest reader rule (also
formalizes 023's failed→retried duplicate lines; resume semantics
preserved); `Candidate.master_id` verbatim from search results;
`scoring.classify_miss_master` → `miss_master_relation` per miss:
`same_master` / `different` / `unknown` (truth master unknown OR no
candidate masters to compare, incl. zero candidates — "nothing to
compare" ≠ "compared and differed", never guessed; retained source
always unknown, no live lookups); summary gains the three miss buckets
+ `practical_rate` = (hits + same-master near-misses)/strict
denominator, strict rate unchanged and still primary; invariants 8–10
normative (buckets sum to misses; practical ≥ strict, equal iff no
near-misses; evidence present wherever extraction happened). All
additive: 023-format manifests/results/summaries stay readable (new
summary fields default). Artifacts: `specs/024-scan-accuracy-followups/`
(spec, plan, research R1–R7, data-model, quickstart + owner checklist,
tasks T001–T022 all complete, contracts: FOUR amendments —
`amendment-017-discogs-consumption-3.md` (+search `master_id` field,
+catno per_page depth, +backfill get_release use),
`amendment-022-scan-api.md` (Candidate +master_id, catno
exact-match-first ordering), `amendment-023-eval-dataset.md` (manifest
master_id, newest-line-wins, backfill mode),
`amendment-023-eval-results.md` (evidence + miss_master_relation +
practical fields + invariants 8–10)). Out of scope kept: vision prompt
changes, depth on other rungs, master-level scoring as primary,
retained-source master lookups.

Prior feature:
**023-scan-eval-harness** (PR #13, merged to main 2026-07-07 — owner-only
live validation still open: quickstart checklist SC-001 full dataset
build, SC-002 first measured identification rate, SC-004 retained-photo
labeling, SC-006 collection-unchanged audit, SC-007 interrupt/resume) —
the measurement loop for 022's scan identification (closes the gap behind
022's deferred SC-002 batch test; measures, never modifies, the
pipeline). `collection-agent` only, zero new deps. Three pieces:
(1) `eval-dataset` CLI subcommand (`eval/dataset.py`): distinct snapshot
release_ids → `get_release` re-fetch consuming `images[]` (NEW fields on
the already-contracted endpoint; snapshot schema deliberately untouched —
research R1) → NEW `DiscogsClient.download_image` (absolute-URL GET
through the governed `_request` path; CDN sends no ratelimit headers,
governor ignores header-less responses — R2) → gitignored
`data/eval/discogs-images/` labeled by release_id: secondary-preferred
cap `COLLECTION_AGENT_EVAL_IMAGES_PER_RELEASE` (default 2), append-only
fsync'd `manifest.jsonl` (run_header w/ snapshot completeness + one
`release` line each: `downloaded`/`no_images`/`failed`; the MANIFEST, not
the filename, is ground truth), resumable (done skipped, `failed` retried
w/ fresh signed URIs, torn trailing line tolerated), `NOTICE.txt`
licensing containment (uploader-copyrighted: local-only, never
committed/redistributed; guard test pins the `.gitignore` `data/` rule +
all dir defaults under `collection-agent/data/`).
(2) `eval-run --source discogs|retained [--limit N]` (`eval/harness.py`):
each labeled image through the PRODUCTION seams unmodified (FR-011) —
`scan/vision.py::extract_evidence` w/ client from `cli._build_llm_client`
(021 tracing + 45s vision cap apply) → `scan/search.py::find_candidates`
w/ `pending_duplicate_checker` — into run-scoped
`data/eval/runs/<run_id>/results.jsonl` (incremental, fsync'd; outcome
taxonomy hit/miss/no_evidence/error/unlabeled, rank, producing rung =
last rung tried, evidence_kinds, billable `vision_calls`, `elapsed_s`) +
`summary.json` w/ normative sum invariants (identification/top-1 rates
exclude `errors` from the denominator; unlabeled never evaluated = never
billed). Per-image failures are typed data (`vision_error`/
`discogs_error`), never a run abort. STRUCTURALLY read-only: AST guard
(`test_eval_readonly_guard.py`) forbids write-method references and
`scan.journal`/`scan.session` imports in `eval/` (013→014 precedent).
(3) opt-in photo retention (`scan/retention.py::PhotoRetainer` + a
flag-gated hook in `scan/server.py`): `COLLECTION_AGENT_SCAN_RETAIN_
PHOTOS` (default OFF ⇒ byte-identical to 022, all 40 pre-existing scan
tests pass unmodified) saves original upload bytes post-size-gate as
`data/eval/scan-photos/<session>/pending-<n>.<ext>`, atomically renamed
to `<scan_id>.<ext>` at cycle-id assignment; vision-error/superseded
uploads stay `pending-*` = permanently unlabeled; retention I/O failure
is ONE loud log warning, never a scan failure (deliberate contrast w/ the
loud-500 journal rule — journal is audit, retention is diagnostics).
Ground truth joins lazily in `eval/sources.py`: journal `added` line
matching the filename's scan_id → labeled; anything else unlabeled
(journal schema untouched). Five new `Settings` fields (VII(a)); 410
tests (`cd collection-agent && pytest`), no live API calls. Recorded
honesty caveat: Discogs images are clean scans ⇒ discogs-source results
are an UPPER BOUND of real phone accuracy; the retained source is the
true distribution and starts empty. Artifacts:
`specs/023-scan-eval-harness/` (spec, plan, research R1–R10, data-model,
quickstart + owner live-validation checklist, tasks T001–T028 all
complete, contracts: `eval-dataset.md`, `eval-results.md`,
`amendment-017-discogs-consumption-2.md` — SECOND amendment to 017's
discogs-consumption contract: +`images[]` fields, +image binary GET,
explicitly zero new writes). Out of scope kept: pipeline/prompt changes,
CI eval integration, image preprocessing/augmentation, fine-tuning.

Prior feature:
**022-phone-record-scan** (PR #12, merged to main 2026-07-07 — implemented
2026-07-07 on branch `022-phone-record-scan`; owner-only live
validation T038–T041 still open) — scan physical records with the
phone: a `scan` HTTP subcommand inside `collection-agent` (FastAPI +
uvicorn + python-multipart — the component's first HTTP surface) serves
a self-contained phone page (`scan/static/index.html`, native-camera
`capture` input, NOT the `frontend` component) on the home LAN (plain
HTTP, no page auth — recorded v1 risk; default `0.0.0.0:8022`).
Pipeline: photo → `scan/vision.py::extract_evidence` (one
`chat.completions` call w/ `json_object`, model from NEW
`COLLECTION_AGENT_VISION_MODEL` default `gpt-4o-mini`, via 017/021's
`_build_llm_client` seam so LangSmith wraps it; one retry then typed
502) → `scan/search.py` precision ladder over NEW
`DiscogsClient.search_releases` (`GET /database/search`, `type=release`
forced): barcode → catno(+label) → artist+title, lower rung only on
zero results; free-text rung for manual search; dedup, cap 8
(`COLLECTION_AGENT_SCAN_CANDIDATES_MAX`), `more_matches` flag; every
candidate field VERBATIM from the search payload (019 discipline,
audited by unit test). Duplicate overlay
(`snapshot_duplicate_checker`): snapshot counts + session adds;
partial/stale-snapshot absence degrades to explicit `unknown`, never
"not in collection" (FR-010). Write gate (017's y/N translated to
HTTP, research R9): `POST /api/add` requires a session-allowlisted
release_id (LLM output can never reach the write), duplicates need
`confirm_duplicate=true` enforced server-side; add = NEW
`DiscogsClient.add_to_collection` (`POST .../folders/{fid}/releases/
{rid}`, folder `COLLECTION_AGENT_SCAN_FOLDER_ID` default 1, validated
LIVE at startup) → journal `added` → `SnapshotStore.mark_stale()`
(R4: never append sync-shaped records). Append-only fsync'd JSONL
session journal at `data/scan-sessions/<session>.jsonl`
(`COLLECTION_AGENT_SCAN_JOURNAL_DIR`); journal write failure = loud
500, never silent. Uploads capped 10 MiB
(`COLLECTION_AGENT_SCAN_MAX_IMAGE_BYTES`) before any vision work.
Seven new `Settings` fields total (VII(a)); secrets never on the wire
(page is static — grep-guarded test). **Replay addendum 1**
(2026-07-07, live session `20260707-130810Z`: 0/4 identified on two
Crosstown Rebels 12″ singles — diagnosed via the journal + 021's
LangSmith traces): vision put barcode digits in `catno` twice, read
the label as the artist, and parked lead tracks in `notes` (12″
singles print no title); the ladder discarded partial evidence.
Fixes: FR-003 prompt hardening (barcode-vs-catno, label≠artist,
lead-track-is-title, new `tracks` field), FR-019 normalization
(10+-digit separator-stripped catno ⇒ barcode), FR-020 final
free-text rung composed from artist+title/lead-track+label when
structured rungs are absent/empty (journal `evidence_kinds` = rungs
actually TRIED, `text` incl.), FR-021 journal lines carry the compact
extracted evidence values (photo) / query (manual) — LangSmith no
longer needed to debug identification. Owner independently repointed
`COLLECTION_AGENT_VISION_MODEL` to `gpt-5.4-mini`. Live session 2
(`20260707-160209Z`): 2/2 identified via the barcode rung and added
(releases 724223, 297060); SC-004/005/007 + stale→sync→complete
reconciliation validated same day (note in quickstart.md); still
open, DEFERRED post-merge by owner decision 2026-07-07 ("close 022
as-is"): SC-002 10-record batch + SC-003 taps (T038) and the T041
LAN-exposure decision; SC-006 owner-validated (dup marker on re-scan,
post-sync — T039 done); one 80s vision-latency provider outlier on
record. **Replay addendum 2** (2026-07-07, owner request post-SC-006):
FR-022 — a new scan/search auto-closes every still-open cycle
(journaled `skipped`, detail "auto-closed: superseded by a new
scan"), closing the orphan-cycle gap; FR-023 — a new scan supersedes
in-flight identification (page AbortController + server generation
counter: superseded results discarded, 409 `superseded`, no journal/
allowlist effects; scan handlers moved to sync-def threadpool — the
old async handler blocked the event loop during the 80s vision
outlier) + NEW `COLLECTION_AGENT_SCAN_VISION_TIMEOUT_S` (default 45s)
hard-caps each vision call. 344 tests
(`cd collection-agent && pytest`), no live API calls; live replay
tests use the verbatim failing vision replies; `FakeDiscogsClient`
grew scriptable search/add. Artifacts: `specs/022-phone-record-scan/`
(spec + replay addendum 1, plan, research R1–R10, data-model,
quickstart + owner live-validation checklist, tasks T001–T037 +
T042–T050 complete / T038–T041 owner-only, contracts: `scan-api.md`,
`scan-journal-schema.md`, `amendment-017-discogs-consumption.md` —
FIRST amendment to 017's discogs-consumption contract:
+`/database/search` read, +add-to-collection write). Out of scope
kept: OAuth/YouTube, cover-art fingerprints, HTTPS/auth (owner
decision T041).

Prior feature:
**021-langsmith-tracing** (PR #11, merged to main 2026-07-07) —
LangSmith observability for the collection-agent via the `langsmith`
SDK's plain-OpenAI integration, explicitly NOT a LangChain migration
(017 research R2's plain-SDK loop stays the architecture of record).
One trace tree per user turn in the dedicated LangSmith project
`discogs-collection-agent`: `run_turn` chain root (`@traceable` in
`agent.py`); client-level `llm` runs carrying the **as-sent** payload
— incl. the transient `LANGUAGE_REMINDER` (wire truth, never the
persisted session) — plus provider token usage; one tool span per
`_dispatch` (now a traced shell over `_dispatch_impl`) recording the
exact returned payload incl. all four error-dict shapes.
`wrap_openai` happens ONLY at `cli.py::_build_llm_client` (017's
injectable seam — test stubs are never wrapped). Config: four
`Settings` fields reusing the repo `.env`'s existing
`LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_ENDPOINT` names +
dedicated `COLLECTION_AGENT_LANGSMITH_PROJECT` (default
`discogs-collection-agent`; deliberately never inherits `agent/`'s
`LANGSMITH_PROJECT` — separate projects, same org), bridged
settings→`os.environ` at that one site (VII(a); the SDK incl. the
`@traceable` gate reads only `os.environ` — same mismatch+fix as the
OpenAI-key pass-through). Strict no-op when unconfigured: plain
unwrapped client, zero LangSmith traffic; flag-without-key ⇒ one dim
notice + untraced chat, never `EXIT_CONFIG`; autouse `LANGSMITH_*`
env-scrub in conftest keeps the suite offline regardless of the
shell; secrets-hygiene static audit now sanctions 3
`get_secret_value` sites (the env bridge is the third). Single new
dependency `langsmith>=0.3` (resolved 0.9.8). 223 tests
(`cd collection-agent && pytest`), no live API calls; live
SC-001..006 owner-validated same day (note in quickstart.md).
Artifacts: `specs/021-langsmith-tracing/` (spec, plan, research
R1–R6, data-model, quickstart + live-validation note, tasks
T001–T018 all complete, `contracts/tracing.md` — a NEW contract;
017's agent-tools contract and its 018/019/020 amendment deltas are
untouched). Workflow note: single-PR flow — feature + post-merge
CLAUDE.md state land in ONE PR (owner decision 2026-07-07, replaces
the previous two-PR convention).

Prior feature:
**020-youtube-playlist-integration** (PR #9, merged to main
2026-07-06) — closes the deferred "v2 YouTube playlists" scope with a
**read-only** capability, re-scoped mid-flight (2026-07-06, owner
decision) from OAuth account writes to **anonymous play links**; the
OAuth path is preserved in research R6 as the documented follow-up
candidate. New read tool `playlist_links` (`tools/playlist.py`) emits
`{YOUTUBE_WEB_BASE_URL}/watch_videos?video_ids=…` click-to-play links
over the resolved records' stored videos: one click opens a temporary
playlist the owner saves/names **on the YouTube site** — the agent
never touches a YouTube account (no OAuth, no credentials, no new
deps, no write gate — 017's §4 untouched). Video ids come only from
deterministic parsing of `MediaLink.uri`
(`youtube_links.py::video_id_from_uri`; never LLM-supplied — 019
precedent); the URL shape exists only in `build_watch_videos_url`
(grep-enforced). Links chunk record-aligned at
`YOUTUBE_PLAYLIST_MAX_IDS` (default 50) with per-link labels, no
silent truncation; `videos_per_record` `all` (default) | `first`.
Five owner replay rounds hardened it same-day (findings 1–8, spec
replay addenda 1–5): CLI `soft_wrap` (rich's hard-wrap broke cmd+click
mid-URL), honest "play links, never playlists I created" phrasing,
**decision-point language reminder** (`agent.py::LANGUAGE_REMINDER`,
transient system message appended last to every LLM request, never
persisted — standing-prompt rule 4 kept losing to the registry's
Spanish aliases), **lean listing entries** (`filter_records` defaults
to artist/title/year/country/`release_url`; new `include` arg for
user-named extras; non-eq criteria auto-include their attribute;
titles capped at `LISTING_TITLE_MAX_CHARS` 70 — delta 11, supersedes
019 delta 6's entry shape), and a rows-vs-columns arg-schema guardrail
("show all records" = `limit`, not `include`). Live SC-002 audit:
128/128 emitted ids verbatim from the snapshot. YouTube *search* stays
out of scope. 213 tests (`cd collection-agent && pytest`), no live API
calls in tests. Artifacts: `specs/020-youtube-playlist-integration/`
(spec with 5 replay addenda, plan, research R1–R6, data-model,
quickstart, tasks T001–T019, contracts: `youtube-playlists.md` +
deltas 9–11 in `amendment-017-agent-tools.md` — the third amendment to
017's agent-tools contract, after 018's 1–5 and 019's 6–8).

Prior feature:
**019-listing-link-integrity** (PR #7, merged to main 2026-07-05) —
same-day follow-up closing 018's invented-URL candidate: during 018
replays the LLM fabricated `discogs.com/release/<instance_id>` links
(instance_id is a collection-instance id, not a release id — wrong id
space), violating ground rule 1. Fix (collection-agent only, 013→014
precedent — deterministic enforcement over prompt steering): every
per-record listing entry (`filter_records` matches + fallback_matches,
`top_n` all bases, `media_links` per_record) carries a genuine
tool-built `release_url` =
`{DISCOGS_WEB_BASE_URL}/release/{release_id}` (new settings field,
default `https://www.discogs.com`, distinct from the API base;
shared helper `tools/common.py::release_page_url`; `release_id` comes
from the sync instance pass so every existing snapshot works — no
re-sync). `instance_id` stays byte-identical as the opaque follow-up
reference (id obfuscation rejected, research R1: it would break
`media_links` ref resolution and move/ordinal follow-ups). Ground
rule 1 in `prompts/system.md` extended: page links only from
`release_url`, media links only from `media_links`, URL construction
from any identifier forbidden (absent records get no fabricated
link). `media_links` verbatim-URI + explicit-`none` shape preserved;
its note now distinguishes the release *page* from playable media.
Live replay of the 018 incident prompts passed (zero invented URLs,
SC-001); link spot-checked in browser (SC-002). 146 tests
(`cd collection-agent && pytest`), no live API calls;
`collection-agent/uv.lock` is now tracked. Artifacts:
`specs/019-listing-link-integrity/` (spec, plan, research R1–R5,
data-model, quickstart, tasks T001–T018, contract deltas 6–8 in
`contracts/amendment-017-agent-tools.md`, amending 017's agent-tools
§1/§5 — the second amendment to that contract, after 018's deltas
1–5 against §3).

Prior feature:
**018-title-locate-postmortem** (PR #5, merged to main 2026-07-05) —
postmortem fix for the same-day incident where the collection agent
falsely answered "not in your collection" for records it has synced
("Focus On Guido Schneider", "Gone Astray EP"). Root cause: no `title`
attribute in the declarative registry + the LLM passing `limit=1` on
locate-one-record listings, so the target title hid behind truncation.
Fix (collection-agent only), a five-layer escalation ladder — each
layer added after a live replay showed the previous one insufficient:
(1) one `title` text-kind `AttributeSpec` in `registry.py` (SC-003a
held — no tool-code edits for the attribute); (2) procedural "Locating
a specific record" guidance in `prompts/system.md` (artist +
title-contains on a short distinctive substring, strip format noise
like "2xLP", no small limits on presence checks, affirm near-matches
as THE record); (3) FR-009 retry-aware zero-match note in
`tools/browse.py` (the plain anti-hallucination note was steering the
LLM away from the retry at the decision point); (4) FR-010 `contains`
as the effective default op for text-kind criteria when the LLM omits
`op` (pydantic `model_fields_set` check; explicit `eq` honored) — the
biggest single win; (5) FR-011 deterministic `fallback_matches` +
`fallback_count`: on a zero-match with text + non-text criteria,
`filter_records` itself re-runs the non-text criteria so near-miss
titles land in the payload (013→014 precedent: prompt steering →
deterministic enforcement); session last-listing points at the
fallback. Fuzzy/edit-distance matching and `media_links` stayed out of
scope. 131 tests (`cd collection-agent && pytest`). Artifacts:
`specs/018-title-locate-postmortem/` (spec with two replay-postmortem
addenda, plan, research, data-model, quickstart, tasks T001–T021,
contract deltas 1–5 in `contracts/amendment-017-agent-tools.md`,
amending 017's agent-tools §3).
Its known follow-up (the invented-URL 019 candidate) is **resolved by
019** (above).

Prior feature: **017-discogs-collection-agent** (PR #3, merged to main
2026-07-05) — a terminal/CLI conversational agent
over the owner's **live Discogs collection** (personal access token),
grown inside the existing `collection-agent/` directory (promoted from
script experiment to a `src/` layout with its own `pyproject.toml` +
tests; the offline matcher scripts move mechanically to a sibling
package `src/collection_matcher/` as a separate commit — zero behavior
change, no imports between the two packages).
Architecture: OpenAI **tool-calling loop over deterministic tools** —
no LangGraph, no codegen, no sandbox, no DuckDB. Two-phase sync
(collection pages → per-release enrichment, journaled + resumable,
header-driven rate-limit governor) into a local JSON snapshot at
`collection-agent/data/snapshot.json` (gitignored;
complete/partial/stale states). Analytics/filter/link answers are
served from the snapshot at conversational speed; a **declarative
attribute registry** (`registry.py`) makes filters+aggregations
extensible by declaration and is rendered into the system prompt
dynamically (VII(b) analog — no static attribute prose). Writes
(move-to-folder, create-folder) are **live-only and runtime-gated**:
LLM can only `propose_moves`; the CLI itself prompts y/N and only
then executes with per-item live re-validation. Clarified decisions:
CLI surface; snapshot model; top-rated = community avg (vote count
shown); analytics count **instances**; scale target 300–1k records.
Key facts: Discogs 60 req/min authenticated; unique User-Agent
required; token via `.env` `DISCOGS_USER_TOKEN`. Spec + plan +
Phase-1 artifacts: `specs/017-discogs-collection-agent/` (`spec.md`,
`plan.md`, `research.md`, `data-model.md`, `quickstart.md`,
`contracts/discogs-consumption.md`, `contracts/snapshot-schema.md`,
`contracts/agent-tools.md`). API reference:
`docs/discogs_api_reference.md`. v2 (YouTube playlists/search) is
explicitly out of scope. Component runbook:
`collection-agent/README.md`; ~106 tests at merge — 146 after 019,
213 after 020, 223 after 021 (`cd collection-agent && pytest`), no
live API calls.

Prior feature: **016-frontend-plot-layout** — frontend polish: widened
result/chart column in `frontend/src/App.tsx`, horizontal legend line
added to the canonical code shape in
`agent/src/discogs_agent/prompts/code_generator.md`, copy buttons for
run/thread id badges in `frontend/src/components/RunMetadata.tsx`.
Artifacts: `specs/016-frontend-plot-layout/`.

Prior feature: **008-agent-frontend-v1** — Demo Day frontend. A
React + Vite + TypeScript single-page app that turns the existing
agent into a demoable product: type or click a question, see a
chart inline, plus collapsible SQL, a small data preview, and
routing badges. The frontend ships as a **third** component in
this monorepo (alongside `etl/` and `agent/`), runs as a service
in the existing local docker-compose stack, and depends only on
the agent's already-shipped HTTP API plus a single CORS allowance
added to the agent. The frontend never touches DuckDB, Postgres,
ETL files, or local artifacts directly, and never executes
agent-generated Python or SQL. The chart artifact is rendered as
opaque HTML inside a sandboxed `<iframe>` (`sandbox="allow-scripts"`,
no `allow-same-origin`).

Read this feature's plan and its phase-1 artifacts:

- Plan: `specs/008-agent-frontend-v1/plan.md`
- Spec: `specs/008-agent-frontend-v1/spec.md`
- Research: `specs/008-agent-frontend-v1/research.md` (packaging,
  CORS, iframe sandbox, error mapping, state management)
- Data model: `specs/008-agent-frontend-v1/data-model.md`
  (frontend domain types + reducer state + localStorage shape)
- Contracts: `specs/008-agent-frontend-v1/contracts/`
  - `api-consumption.md` — which agent `/query` fields the frontend
    reads, ignores, or maps
  - `amendment-004-api-cors.md` — exact prose for a new §8
    "Cross-origin policy" in `004/contracts/api.md`
  - `curated-questions.md` — the V1 set of 7 demo questions and
    their spread coverage requirement
- Quickstart: `specs/008-agent-frontend-v1/quickstart.md`

Status: phases 1 through 7 are on `main` (the frontend runs as a
service in `docker-compose.yml`). Phase 8 (Polish) is unfinished:
tasks T054–T058 in `specs/008-agent-frontend-v1/tasks.md` remain
unchecked (typecheck/test gates, no-db-deps guard, no-unsafe-html
guard, empty-state copy).

Prior feature: **`015-classifier-carryover`** (merged to main
2026-05-11) — agent-side hardening
triggered by thread `9214f7fb-...` on 2026-05-11, where two
short follow-up questions ("and what is the second one?" and
"and the top 5?") were rejected as `clarification_needed`
because the classifier (router) sees only `{user_query}` +
`{schema_context_block}` — it doesn't receive the multi-turn
carryover preamble that the next node (`query_understanding`)
already consumes. Structural wiring bug: carryover is built and
consumed in `query_understanding`, AFTER the classifier
short-circuits to clarification_needed. Two work items: (US1)
extract `_load_carryover` from `query_understanding.py` to
`_carryover.py` as a public helper; call it in the router
BEFORE invoking `query_classifier`; populate state; pass
`carryover_preamble` into `ClassifierInput`; add
`{carryover_block}` placeholder + follow-up-resolution
instructions to `router.md`. (US2) Persist carryover at
run-start (falls out of US1's earlier state population) so
`metadata_json.carryover` is no longer `null` on 2nd+-turn
clarification_needed runs — operators can see what context
the classifier had. Plus an admin task: 013's pointer
`successor-015-pointer.md` is renumbered to
`successor-016-pointer.md` because 015 is now this spec
(second renumbering of the same pointer; 014 already did
014→015). See
`specs/015-classifier-carryover/plan.md`.

Prior 004-family work (still authoritative):

- `specs/004-agent-v1/` — V1 baseline (graph, API, sandbox, SQL
  safety, generated-code shape, persistence). The frontend's
  consumption shape is anchored against `004/contracts/api.md`.
  010 amended `004/contracts/postgres-schema.md` with the new §7
  JSONB input invariant.
- `specs/005-agent-schema-context/` — schema enrichment + sample
  values + glossary + the `succeeded_empty` zero-row guardrail.
  Amended by 009 with a new "Join graph" section.
- `specs/006-bugfix-postmortem/` — three-bug postmortem and
  Constitution v1.2.0 amendment (Principle VII: Implementation
  Discipline). 009 and 010 are both VII follow-throughs (009 =
  VII.b prompt-authoring; 010 = VII.c-analog write-side).
- `specs/007-sandbox-fsize-budget/` — sandbox `RLIMIT_FSIZE`
  raised to 2 GiB; `004/contracts/code-generation.md §3.1.1`
  amended.
- `specs/009-schema-context-join-graph/` — silent wrong-answer
  bugfix: extends `render_schema_block` with a join-graph section
  delivering FK relationships, cross-grain traversal hints, and
  forbidden-join anti-patterns. Closes the
  `master_fact.master_id = release_artist_bridge.release_id`
  class of LLM hallucination. Merged to main 2026-05-07.
- `specs/010-jsonb-nan-sanitization/` — silent persistence-500
  bugfix: SQLAlchemy `TypeDecorator` chokepoint sanitizes
  NaN/Infinity floats out of every JSONB column write before
  Postgres rejects them. Closes any agent run whose dataframe
  preview legitimately contains NULL cells. Merged to main
  2026-05-08.
- `specs/012-catalog-aggregation-postmortem/` — SDD back-fill of
  three hotfixes against catalog-wide OOM-kills:
  `memory_limit=1GB` in generated DuckDB connect-config, tmpfs
  bumped to 6 GiB, and glossary entry #3 first-round rewrite
  steering the LLM away from `release_unique_view` for catalog-
  wide aggregations.
- `specs/013-filtered-aggregation-postmortem/` — follow-on
  to 012. Observability fix (`oom_killed` named exception_type
  for external SIGKILL) + glossary entry #3 second-round
  rewrite (drops the "catalog-wide" qualifier; blanket ban on
  view-in-JOIN/GROUP-BY regardless of WHERE filters). Triggered
  by the Depeche Mode failure run (`b809ca52-...`). Merged to
  main 2026-05-11.
- `specs/014-cross-grain-join-postmortem/` — follow-on to 013
  + 009. Resolves the contradiction 013 introduced between
  009's cross-grain traversal hint and 013's glossary
  tightening; updates the hint to recommend `release_fact`
  instead of `release_unique_view`; promotes the forbidden-
  joins list to static enforcement in `sql_safety_checker`
  (`rule="forbidden_join"`). Triggered by run `2557c2ce-...`
  on 2026-05-10. Merged to main 2026-05-11.

The published DuckDB contract — produced by the ETL component —
remains authoritative for everything the agent reads:

- `specs/001-discogs-etl/contracts/duckdb-schema.md` — release side
  (`release_fact`, `release_unique_view`, `release_artist_bridge`,
  `release_label_bridge`).
- `specs/003-masters-artists/contracts/duckdb-schema.md` — optional
  `master_fact`. The "Counting / joining rules" section of this
  contract is the source of truth for the join graph 009 renders
  into the LLM-facing schema-context block. Both contracts are
  NULL-tolerant (release_fact.country, master_fact.year, etc.,
  are nullable) — that NULL-tolerance is what produces the NaN
  floats that 010 sanitizes at the persistence boundary.

The agent does NOT import code from `etl/` and does NOT read
non-published artifacts. Statically enforced by
`agent/tests/unit/test_no_etl_imports.py`. The frontend does NOT
import code from either `etl/` or `agent/`, and physically cannot
read `data/` because it never has the volume mounted.

Resolved scope decisions still in force:

- **LLM provider = OpenAI** (`gpt-4o-mini` cheap, `gpt-4o` strong).
- **Multi-turn = light contextual carry-over** — only prior
  user-query *text* (capped at 4 turns / 512 tokens) flows into
  `query_understanding`. No prior SQL/code carry-over.
- **Sandbox file-size budget = 2 GiB** (007 decision).
- **Schema-context join graph** (009 decision; merged to main).
  The rendered block delivers FK edges + cross-grain traversal
  hints + forbidden-join anti-patterns. The 005 contract is
  amended to make the section normative.
- **JSONB input invariant** (010 decision; merged to main). Every
  dict flowing into a JSONB column MUST be RFC-8259-compliant.
  Sanitization happens at the persistence-write boundary via a
  single chokepoint (`_SanitizedJSON` `TypeDecorator` in
  `agent/src/discogs_agent/persistence/models.py`) covering all
  five JSONB columns. The 004 contract gains §7 making this
  invariant normative.
- **Frontend stack = React 18 + Vite + TypeScript + Tailwind**
  (008 decision; matches the source brief at
  `docs/discogs_frontend_initial_spec.md`).
- **Frontend packaging = Vite dev-server in container** for V1
  (008 decision; nginx-served static build deferred to V1.1).
- **CORS allowlist** = settings-sourced env var
  `CORS_ALLOWED_ORIGINS`, defaulting to
  `["http://localhost:5173", "http://localhost:3000"]`,
  `allow_credentials = False`.

Constitution: `.specify/memory/constitution.md` (v1.2.1, amended
2026-07-05). The PATCH amendment recommended by 008's plan and
re-recommended by 017's plan **has landed**: Principle VI is now
"Components & Contracts" — "two or more independently deployable
components", listing all four (`etl/`, `agent/`, `frontend/`,
`collection-agent/`); its operational rules are unchanged.

The constitution prevails on any conflict.
<!-- SPECKIT END -->
