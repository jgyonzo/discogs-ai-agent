# Feature Specification: Scan Identification Eval Dataset & Harness

**Feature Branch**: `023-scan-eval-harness`
**Created**: 2026-07-07
**Status**: Draft
**Input**: User description: "Scan identification eval dataset + harness for the collection-agent. Two data sources, one eval loop, all owner-run and offline from CI's perspective: (1) Discogs-image eval dataset: a script that walks the existing local snapshot's release_ids, fetches each release's images from the Discogs API (authenticated, rate-limit governed like sync), and downloads the images into a gitignored local dataset directory, labeled by release_id (ground truth). Prefer secondary images (back covers with barcodes, center-label shots) over primary front-cover scans where available. Images are uploader-copyrighted: dataset stays local-only, never committed, never redistributed. (2) Opt-in real-photo retention in the 022 scan server: a new settings flag (default OFF) that, when enabled, saves each uploaded scan photo to a gitignored retention directory keyed by session/cycle id; the journal's cycle outcome gives the ground-truth label after the fact. No behavior change when off. (3) Eval harness: an owner-run script (NOT part of pytest — live vision + Discogs search calls) that feeds each labeled image through the existing identification pipeline and scores: was the true release_id among the candidates, at which rank, via which ladder rung. Outputs per-image JSONL + a summary. Works over both dataset sources. Out of scope: changes to the identification pipeline itself, CI integration, image preprocessing/augmentation, fine-tuning, committing any image anywhere."

## Context

Feature 022 shipped phone-based record scanning: photo → vision evidence extraction →
a precision ladder of Discogs searches → owner-confirmed add. Its live validation
surfaced real identification failures (replay addendum 1: 0/4 on two 12″ singles)
that were fixed by prompt and ladder changes — but the project has **no repeatable way
to measure identification accuracy**. Each accuracy claim so far rests on a handful of
manual live scans (2/2 in live session 2). The still-open SC-002 of 022 ("10-record
batch") exists precisely because there is no dataset to run against.

This feature builds the measurement loop: two labeled image datasets (one downloadable
today from Discogs' own release images, one accumulating over time from real phone
scans) and an owner-run eval harness that replays the production identification
pipeline over them and reports accuracy with per-rung attribution.

Known honesty caveat, recorded up front: Discogs-hosted images are flat, well-lit
scans — the *easy* end of the input distribution — so results over that dataset are an
upper bound, not an estimate, of real phone-scan accuracy. Preferring secondary images
(back covers, center labels) narrows but does not close the gap. The retained-photo
dataset is the ground-truth distribution; it just starts empty.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Build a labeled eval dataset from my own collection's Discogs images (Priority: P1)

As the collection owner, I run one command that walks my already-synced collection,
downloads release images from Discogs for each release, and stores them locally
labeled with the release they belong to — so I immediately have a few hundred
ground-truth-labeled test images without photographing a single record.

**Why this priority**: Everything else in this feature consumes a labeled dataset;
this is the only source that exists on day one. It also carries the licensing
constraint (local-only) that shapes the whole feature.

**Independent Test**: With a synced snapshot present, run the dataset builder and
verify a local dataset directory appears containing images organized under the
release they belong to, with a manifest recording ground truth and provenance —
and that none of it is committable to git.

**Acceptance Scenarios**:

1. **Given** a complete snapshot of the owner's collection, **When** the owner runs
   the dataset builder, **Then** for each distinct release in the snapshot the builder
   fetches that release's image list, downloads up to the configured number of images,
   and records each image's ground-truth release, image kind (primary/secondary), and
   source in a manifest.
2. **Given** a release that has both primary and secondary images, **When** images are
   selected for download, **Then** secondary images are preferred over the primary
   front-cover image, up to the per-release cap.
3. **Given** the builder is interrupted partway (network failure, Ctrl-C), **When**
   the owner re-runs it, **Then** already-downloaded images are skipped and the run
   completes the remainder — no duplicate downloads, no corrupted manifest.
4. **Given** the dataset directory is populated, **When** the owner runs `git status`,
   **Then** no dataset file appears as trackable (the directory is gitignored), and an
   automated guard test enforces this.
5. **Given** a release with zero images on Discogs, **When** the builder processes it,
   **Then** it is recorded in the manifest as image-less (not silently skipped) and
   the run continues.

---

### User Story 2 - Measure identification accuracy over a labeled dataset (Priority: P2)

As the collection owner, I run the eval harness over a labeled image dataset and get
a per-image results file plus a summary that tells me: what fraction of images the
scan pipeline identified correctly, at what candidate rank, and which ladder rung
produced the hit — so accuracy claims about the scan feature become measurements
instead of anecdotes.

**Why this priority**: This is the payoff — the measurement loop. It is P2 only
because it needs a dataset (US1) to run against; with even two hand-placed labeled
images it is independently testable.

**Independent Test**: Point the harness at a directory containing a small number of
labeled images and verify it produces one result line per image and a summary whose
counts add up, without writing anything to the live Discogs collection.

**Acceptance Scenarios**:

1. **Given** a labeled dataset, **When** the owner runs the harness, **Then** each
   image is fed through the same vision-extraction → search-ladder pipeline the scan
   server uses in production (no eval-only shortcuts), and one result record is
   appended per image containing: the true release, whether it appeared among the
   returned candidates, its rank if present, the ladder rung that produced the
   candidate list, and the evidence kinds the vision step extracted.
2. **Given** a completed run, **When** the owner reads the summary, **Then** it
   reports overall identification rate, top-1 rate, per-rung hit counts, and counts
   of images where vision extracted no usable evidence — and the per-category counts
   sum to the total number of images evaluated.
3. **Given** any eval run, **When** it finishes, **Then** the owner's live Discogs
   collection is unchanged — the harness has no code path that can add, move, or
   modify collection items.
4. **Given** a vision or search call fails for one image (timeout, provider error),
   **When** the run continues, **Then** that image is recorded as errored (with the
   error kind) rather than aborting the whole run, and errored images are reported
   separately from misses.
5. **Given** the owner wants a cheap smoke run, **When** they pass a limit, **Then**
   only that many images are evaluated and the summary says the run was limited.

---

### User Story 3 - Accumulate a real-photo dataset from actual scans (Priority: P3)

As the collection owner, I flip an opt-in setting so that every photo I upload
through the phone scan page is also saved locally, keyed to its scan session and
cycle — so that over time I accumulate a test dataset with the *real* input
distribution (angles, glare, center labels), automatically labeled whenever I
confirm an add for that cycle.

**Why this priority**: Highest long-term value (it is the true distribution) but
zero images on day one, and the eval loop already works without it via US1.

**Independent Test**: Enable the flag, perform a scan through the phone page,
verify the uploaded photo bytes appear in the retention directory keyed by
session/cycle; disable the flag and verify behavior is byte-identical to today
(existing scan tests pass unchanged).

**Acceptance Scenarios**:

1. **Given** retention is OFF (the default), **When** any scan happens, **Then** no
   photo is written anywhere and the scan flow is unchanged from 022's merged
   behavior.
2. **Given** retention is ON, **When** a photo is uploaded for identification,
   **Then** the original uploaded bytes are saved under the retention directory,
   keyed by session id and cycle id, before any identification outcome is known.
3. **Given** retained photos exist and the journal records a confirmed add for their
   cycle, **When** the harness runs over the retention source, **Then** those photos
   are scored against the journaled release as ground truth; photos whose cycles
   never reached a confirmed add are reported as unlabeled and excluded from
   accuracy math (but counted).
4. **Given** retention is ON and the retention write fails (disk full, bad
   directory), **When** a scan is in flight, **Then** the scan itself still works —
   retention failure is loudly visible in server output but never breaks or blocks
   identification (unlike the journal, retention is diagnostic, not the audit
   record).
5. **Given** the retention directory is populated, **When** the owner runs
   `git status`, **Then** no photo is trackable (gitignored, guard-tested — same
   discipline as the dataset directory).

---

### Edge Cases

- Snapshot is partial or stale: the builder runs over whatever release ids the
  snapshot has, and stamps the snapshot state into the manifest so an eval report
  can say what it covered. A missing snapshot is a clear, actionable error.
- The same release appears as multiple instances in the collection: the builder
  deduplicates — one dataset entry per distinct release.
- A release's images include only a primary image: the primary is taken (secondary
  preference, not secondary requirement).
- Discogs rate limiting mid-build: the builder honors the same header-driven
  governor discipline as sync — it slows down, it does not error out or hammer.
- An image URL returns an error or non-image payload: recorded as a failed download
  in the manifest; the build continues.
- A retained photo's cycle was auto-closed or skipped (022's FR-022): it stays
  unlabeled — only a journaled confirmed add labels a photo.
- Two eval runs started back-to-back: each run writes to its own run-scoped results
  location; runs never interleave lines in one file.
- Dataset and retention directories may not exist yet when the harness runs: an
  empty or missing source is a clear message ("nothing to evaluate"), not a crash.
- The eval's vision calls cost real money: the limit control (US2, scenario 5) is
  the cost throttle; the summary always states how many billable calls were made.

## Requirements *(mandatory)*

### Functional Requirements

**Dataset builder (US1)**

- **FR-001**: The builder MUST derive its worklist from the distinct release ids in
  the existing local snapshot (deduplicating multiple instances of the same release)
  and MUST fail with an actionable message when no snapshot exists.
- **FR-002**: The builder MUST fetch each release's image list and download images
  using authenticated, rate-limit-governed Discogs access with the same restraint
  discipline as the existing sync (header-driven backoff; never a retry storm).
- **FR-003**: For each release the builder MUST download at most a configurable
  number of images (default 2), preferring secondary images over the primary image
  when both exist.
- **FR-004**: The builder MUST write a manifest that records, per downloaded image:
  ground-truth release id, image kind (primary/secondary), source URI, and fetch
  timestamp — and, per release: zero-image and failed-download outcomes. The
  manifest is the single source of ground truth for the harness.
- **FR-005**: The builder MUST be resumable: re-running skips images already
  downloaded and completes the remainder, never duplicating files or corrupting the
  manifest.
- **FR-006**: The dataset directory MUST be gitignored, and an automated guard test
  MUST fail if the dataset or retention directories ever become trackable by git.
  Images are uploader-copyrighted: nothing under these directories may ever be
  committed or redistributed; the dataset directory MUST contain a short notice
  file stating this.

**Real-photo retention (US3)**

- **FR-007**: Photo retention MUST be controlled by a new settings flag that
  defaults to OFF; with the flag off, scan-server behavior is unchanged from 022
  (existing tests pass without modification).
- **FR-008**: With retention ON, the server MUST persist the original uploaded
  photo bytes keyed by scan session id and cycle id at upload time, before the
  identification outcome is known.
- **FR-009**: Retention failures MUST be loudly visible in server output but MUST
  NOT fail, block, or alter the scan flow — retention is diagnostic, never the
  audit record (the journal keeps that role).
- **FR-010**: Ground truth for retained photos MUST come only from the session
  journal: a cycle whose journal shows a confirmed add labels its photo with the
  added release id; all other retained photos are "unlabeled" and excluded from
  accuracy computation while still being counted in reports.

**Eval harness (US2)**

- **FR-011**: The harness MUST evaluate images through the same production
  identification pipeline the scan server uses (vision evidence extraction followed
  by the search ladder), with no eval-only alternative pipeline.
- **FR-012**: The harness MUST support both dataset sources — the Discogs-image
  dataset (manifest ground truth) and the retention directory (journal-joined
  ground truth) — and report them distinguishably.
- **FR-013**: Per image, the harness MUST record: ground-truth release id, the
  candidate list outcome (hit or miss), the rank of the true release when present,
  the ladder rung that produced the candidate list, the evidence kinds extracted,
  and per-image timing. Results are written incrementally, one record per image, to
  a run-scoped results file.
- **FR-014**: Per run, the harness MUST produce a summary reporting: images
  evaluated, identification rate (true release anywhere in candidates), top-1 rate,
  per-rung hit attribution, no-evidence count, error count, unlabeled count (for
  the retention source), source dataset, and the number of billable vision calls
  made. Category counts (hits, misses, no-evidence, errors, unlabeled) MUST sum
  to the total number of images seen; errors are excluded from the
  identification-rate denominator but always reported beside it (the exact
  invariants are normative in `contracts/eval-results.md` §3).
- **FR-015**: A single image's vision/search failure MUST be recorded as an errored
  result and MUST NOT abort the run.
- **FR-016**: The harness MUST be strictly read-only against Discogs: it MUST have
  no code path that can write to the collection (no add, move, or folder calls),
  and it MUST NOT write scan-session journals or touch the scan server's session
  state.
- **FR-017**: The harness MUST accept a limit on the number of images evaluated
  (cost control); the summary states when a run was limited.
- **FR-018**: The harness and builder MUST be owner-run commands, never executed by
  the automated test suite: the test suite continues to make zero live API calls,
  while the harness's and builder's pure logic (image selection, manifest handling,
  journal joining, scoring, summary math) MUST be covered by offline unit tests.

### Key Entities

- **Eval dataset**: A local, gitignored directory of images plus a manifest; each
  image belongs to exactly one release (its ground truth). Two sources exist:
  Discogs-image (built by the builder) and retained-photo (accumulated by the scan
  server).
- **Manifest entry**: One downloaded (or attempted) image: ground-truth release id,
  image kind, source URI, fetch time, download outcome.
- **Retained photo**: Original uploaded scan-photo bytes keyed by session id +
  cycle id; label resolved lazily from the journal (confirmed add → release id;
  otherwise unlabeled).
- **Eval run**: One harness invocation over one source: run id, source, limit,
  per-image results, summary.
- **Result record**: One evaluated image: ground truth, hit/miss/error, rank, rung,
  evidence kinds, timing.
- **Summary**: Aggregate counts and rates for a run; internally consistent (counts
  sum to total).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Starting from a synced snapshot, one builder command produces a
  labeled dataset covering at least 95% of the snapshot's distinct releases that
  have images on Discogs, without a single rate-limit violation error surfacing to
  the owner.
- **SC-002**: One harness command over the built dataset yields a per-image results
  file and a summary whose identification rate, top-1 rate, per-rung attribution,
  no-evidence, and error counts are internally consistent (sum check) — giving the
  project its first measured identification-accuracy number.
- **SC-003**: With retention at its default (off), the complete pre-existing scan
  test suite passes unchanged.
- **SC-004**: With retention on, a real scan session that ends in a confirmed add
  yields a retained photo that the harness scores with zero manual labeling steps.
- **SC-005**: At no point can `git status` show any image or dataset file as
  trackable; the guard test fails the suite if the ignore rules are ever removed.
- **SC-006**: An eval run makes zero write calls to the live Discogs collection —
  verified structurally (no write capability in the harness) and observably
  (collection unchanged after a full run).
- **SC-007**: Interrupting the builder at any point and re-running it converges to
  the same complete dataset (idempotent resume), with no duplicate or corrupt
  entries.

## Assumptions

- A synced snapshot already exists locally (017's sync); the builder reads release
  ids from it rather than re-crawling the collection. Collection scale remains
  300–1k records, so a full dataset build fits comfortably within Discogs rate
  limits in one sitting (minutes, not hours).
- Discogs serves release images to authenticated API users; per-image licensing
  remains with uploaders, which is why the dataset is local-only and never
  redistributed. This mirrors the existing snapshot's gitignored handling.
- The eval harness spends real money on vision calls (one per evaluated image, at
  the configured vision model); the default invocation therefore favors explicit
  limits, and cost visibility (billable-call count) is part of every summary.
- Retention stores the original upload bytes (no resizing/re-encoding), matching
  the existing upload size cap; disk usage is bounded by scan frequency and is the
  owner's to manage.
- "Correct identification" means the ground-truth release id appears in the
  candidate list the pipeline returns for the image; rank 1 is reported separately.
  Master-vs-release ambiguity (a different pressing of the same album) is
  deliberately scored as a miss in v1 — the scan feature adds specific releases.
- Retention failure tolerance (FR-009) is a deliberate contrast with 022's
  loud-journal-failure rule: the journal is the audit record, retained photos are
  diagnostics. This is recorded here so the difference is a decision, not an
  accident.

## Out of Scope

- Any change to the scan identification pipeline itself (prompts, ladder, models) —
  this feature measures it; improving it is a follow-up informed by the numbers.
- CI integration of the eval (it stays owner-run; the test suite stays offline).
- Image preprocessing, augmentation, or synthetic distortion of Discogs images to
  simulate phone conditions.
- Any model fine-tuning or training.
- Committing, publishing, or redistributing any image, anywhere, ever.
- Cover-art fingerprinting / image-similarity matching (already rejected in 022).
