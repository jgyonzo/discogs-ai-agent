# Feature Specification: Dockerize the collection-agent

**Feature Branch**: `027-dockerize-collection-agent`
**Created**: 2026-07-12
**Status**: Draft
**Input**: User description: "Dockerize the collection-agent component. One Docker image for the whole component with entrypoint `python -m collection_agent`, so every existing mode runs containerized: the `scan` phone record-scan HTTP server as a long-running docker-compose service on port 8022, and `sync`/`status`/`chat`/`eval-dataset`/`eval-run` as one-shot/interactive invocations via `docker compose run`. State stays on the host: `collection-agent/data/` is volume-mounted so container and host venv runs see the same data. Configuration comes from the existing repo-root `.env` (env_file), same as agent-api; secrets never baked into the image. Critical constraint: the existing demo stack (postgres, agent-api, frontend) must be completely unaffected — the new service goes behind a docker-compose profile so plain `docker compose up` starts exactly the same service set as today (pinned with a guard). The scan server validates the Discogs folder id live at startup and needs DISCOGS_USER_TOKEN — the profile guard exists precisely so token-less demo users never start it. Long-term context: deploying the whole stack to AWS for third-party users; this feature is only the containerization groundwork. Out of scope: AWS deployment, multi-tenancy, Discogs OAuth, auth/TLS on the scan server, a web chat surface, containerizing collection_matcher, and any behavior change to the collection-agent itself."

## Context

The collection-agent is the only one of the repo's four components without a
container story: `agent/` and `frontend/` build images and run as
docker-compose services, `etl/` produces the published artifacts they consume,
but the collection-agent runs only from a host virtualenv. The owner's
long-term goal is to deploy the whole stack to a cloud host for third-party
users; that future requires multi-tenancy, per-user authorization, and secured
surfaces, **none of which this feature attempts**. This feature is the
groundwork step that is valuable on its own today: the component becomes
startable on any Docker host with one command, its state boundary
(`collection-agent/data/`) and configuration boundary (repo-root `.env`)
become explicit, and the full four-component stack can be brought up from one
compose file.

The component is not a single service. It is a multi-mode command-line
program: `scan` is a long-running HTTP server (the phone record-scan page,
port 8022), while `sync`, `status`, `eval-dataset`, and `eval-run` are
one-shot commands and `chat` is an interactive terminal conversation. The
containerization must serve all modes from one image without changing any of
their behavior.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the scan server as a containerized service (Priority: P1)

The owner starts the phone record-scan server with a single compose command
instead of activating a virtualenv. The phone page works exactly as it does
today — photograph a record, review candidates, confirm an add — and every
outcome lands in the same on-host data files (`snapshot.json` staleness mark,
`data/scan-sessions/<session>.jsonl` journals) that the host-venv workflow
reads.

**Why this priority**: The scan server is the component's one long-running
service and the natural container citizen; it is the mode where "start it
anywhere with one command" pays off most (it currently requires a venv, a
shell, and a laptop that stays awake). It also exercises every containerization
concern at once: config from `.env`, live Discogs startup validation, LAN
reachability from the phone, and writes into the mounted data directory.

**Independent Test**: On a machine with Docker and a populated repo-root
`.env`, run the documented single compose command; open the printed URL from a
phone on the same network; complete one scan-and-add; verify the journal line
and the snapshot staleness mark appear under the host's
`collection-agent/data/`.

**Acceptance Scenarios**:

1. **Given** a valid `.env` at the repo root and no host virtualenv, **When**
   the owner starts the collection-agent compose service, **Then** the scan
   server starts, validates the configured Discogs folder live (as today), and
   serves the phone page on port 8022 reachable from a phone on the same
   network.
2. **Given** the containerized scan server is running, **When** a scan is
   completed and an add confirmed from the phone, **Then** the add reaches
   Discogs, the session journal file appears under the host's
   `collection-agent/data/scan-sessions/`, and the host-side snapshot is
   marked stale — byte-for-byte the same observable outcomes as a host-venv
   run.
3. **Given** the containerized scan server is running, **When** the container
   is stopped and the host-venv scan server is started instead, **Then** it
   sees the same snapshot, journals, and eval data with no migration step.

---

### User Story 2 - The demo stack is provably untouched (Priority: P1)

A person who only wants the Demo Day stack (database, agent API, frontend)
runs the same startup command they run today and gets exactly the same three
services — the collection-agent service does not start, does not require a
Discogs token in their `.env`, and does not attempt any network call. The
collection-agent service starts only when explicitly requested by name or
profile.

**Why this priority**: Non-interference is the feature's hard constraint, not
a nice-to-have. The collection-agent's scan mode performs a live Discogs
validation at startup and exits without credentials; if it joined the default
service set, a token-less demo user's `docker compose up` would gain a
crash-looping container making outbound calls. Equal-top priority because
shipping US1 in a way that violates this would be a regression for the two
existing components.

**Independent Test**: With the feature merged, run the default stack startup
command with a `.env` containing no Discogs token; verify exactly the same
service set starts as on the commit before the feature, all healthy, and that
no collection-agent container was created. An automated guard pins the default
service set.

**Acceptance Scenarios**:

1. **Given** the feature is merged, **When** `docker compose up` is run with
   no profile, **Then** the started service set is exactly the pre-feature set
   (database, agent API, frontend) — the collection-agent service is not
   created, even when `.env` lacks a Discogs token.
2. **Given** the existing demo stack definition, **When** this feature's
   changes are diffed against it, **Then** the existing services' images,
   build contexts, ports, volumes, environment, and dependency/startup order
   are unchanged, and no existing service depends on the new one (nor the
   reverse).
3. **Given** the repository test suites, **When** they run after the feature,
   **Then** an automated guard fails if the default (profile-less) compose
   service set ever gains or loses a service, and all pre-existing
   collection-agent tests pass unmodified.

---

### User Story 3 - One-shot and interactive modes run containerized (Priority: P2)

The owner runs `sync`, `status`, `chat`, `eval-dataset`, or `eval-run` inside
the same container image via a documented one-off invocation — no virtualenv
required — and each behaves exactly as its host equivalent: `sync` writes the
same resumable snapshot, `status` reads it, `chat` holds an interactive
conversation in the terminal, eval commands read and write the same
`data/eval/` locations. Container and host invocations are interchangeable
mid-workflow (e.g. sync in the container, chat from the venv, or the reverse).

**Why this priority**: Completes "the component runs anywhere Docker runs" —
without it, a container-only host still cannot produce the snapshot the scan
server's duplicate detection depends on. Lower than US1/US2 because the owner
retains the venv workflow, so nothing breaks if this lands later.

**Independent Test**: On a fresh clone with only Docker and a populated
`.env`, run the documented one-off `sync` invocation, then `status`; verify a
complete snapshot exists under the host's `collection-agent/data/` and its
reported counts match a host-venv `status` reading the same file.

**Acceptance Scenarios**:

1. **Given** no snapshot exists, **When** the owner runs the documented
   containerized `sync`, **Then** the snapshot is created under the host's
   `collection-agent/data/` and a subsequent host-venv `status` reports it
   complete — and vice versa (host-created snapshots are read identically
   inside the container).
2. **Given** a containerized `sync` is interrupted, **When** it is re-run
   (from container or host), **Then** it resumes from the journal exactly as
   the host workflow does today.
3. **Given** the documented containerized `chat` invocation, **When** the
   owner converses, **Then** the interactive terminal experience (prompt,
   streaming replies, `/refresh`, `/exit`, confirmation gates for moves)
   works as on the host.
4. **Given** any containerized invocation exits, **When** its exit status is
   inspected, **Then** the component's documented exit codes (0 ok, 1
   unexpected, 2 configuration, 3 partial sync) are preserved verbatim.

---

### Edge Cases

- **Missing/invalid Discogs token with the profile explicitly requested**: the
  scan service starts, fails its live startup validation, and exits with the
  component's configuration exit code — a loud, attributable failure. It must
  never silently retry-loop against Discogs without logging, and it must be
  reachable only by explicit opt-in (see US2).
- **Repo-relative default paths**: the component's defaults
  (`collection-agent/data/...` for snapshot, journals, eval dirs) are relative
  to the repo layout. Inside the container these must resolve to the mounted
  host directory — via working-directory/mount layout or explicit environment
  overrides, **not** source changes — so that a path written by the container
  is the same file the host venv reads (US1/US3 interchangeability).
- **File ownership across the boundary**: files created by the containerized
  process (snapshot, journals, retained photos) must remain readable and
  writable by the host-venv workflow afterwards, and vice versa.
- **Phone reachability**: publishing port 8022 must expose the page on the
  Docker host's LAN address (the phone reaches the host, not the container
  network). The banner URL the server prints reflects its bind address inside
  the container; documentation must state that the phone should use the
  host's LAN IP.
- **Container stop while a scan cycle is open**: stopping the service is
  equivalent to today's Ctrl-C — journals are append-only and fsync'd per
  line, so no corruption; any in-flight cycle simply has no closing entry
  (the known, accepted shutdown behavior — unchanged by this feature).
- **Interactive `chat` needs a terminal**: the documented one-off invocation
  must allocate an interactive terminal; a non-interactive invocation of
  `chat` failing cleanly is acceptable, silently hanging is not.
- **Image hygiene**: the built image must contain no secrets, no
  `collection-agent/data/` contents (snapshots, journals, eval images are
  personal/licensed data), and the repo-root `.env` must never enter the
  build context.
- **`.env` absent entirely**: compose invocations that reference the env file
  must fail with a clear message (or documented fallback), not start a
  half-configured service.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A single container image MUST run every existing
  collection-agent mode (`sync`, `status`, `chat`, `scan`, `eval-dataset`,
  `eval-run`) via the component's existing command-line entrypoint, with the
  scan server as the image's default command.
- **FR-002**: The scan server MUST be startable as a long-running
  docker-compose service publishing port 8022, reachable from devices on the
  Docker host's local network.
- **FR-003**: The new compose service MUST be excluded from the default
  service set: plain `docker compose up` (no profile, no explicit service
  name) MUST start exactly the pre-feature services. Activation MUST require
  an explicit opt-in (profile or service name).
- **FR-004**: An automated guard MUST pin the default compose service set, so
  any future change that adds or removes a default service fails a test.
- **FR-005**: The existing services' definitions (images, build contexts,
  ports, volumes, environment, healthchecks, dependency order) MUST be
  unchanged, and no dependency edge may exist in either direction between the
  new service and any existing service.
- **FR-006**: The host's `collection-agent/data/` directory MUST be mounted
  into the container such that all component state (snapshot, scan-session
  journals, eval datasets, eval runs, retained photos) is read from and
  written to the same host files the host-venv workflow uses —
  interchangeably, in both directions, with no migration step and no source
  changes to path handling.
- **FR-007**: Configuration MUST come from the repo-root `.env` at container
  start (the same file and mechanism the agent API service uses). Secrets
  MUST never be baked into the image, and the image build MUST NOT read
  `.env` or any `collection-agent/data/` contents (enforced by build-context
  exclusion).
- **FR-008**: One-shot modes MUST be runnable as documented one-off container
  invocations that exit with the component's existing exit codes verbatim;
  `chat` MUST be runnable with an interactive terminal.
- **FR-009**: The component's Python source and its observable behavior MUST
  be unchanged: zero edits under `collection-agent/src/`, all 536 existing
  tests pass unmodified, and no new Settings fields are introduced unless a
  container-path override proves strictly necessary (in which case it must
  default to today's behavior).
- **FR-010**: The scan server's live startup validation failure inside the
  container MUST surface as a loud container exit with the configuration exit
  code — never a silent retry loop.
- **FR-011**: The component README MUST document the containerized
  equivalents of every documented host command (start scan service, one-off
  sync/status/chat/eval, and how the phone reaches the page), alongside — not
  replacing — the host-venv instructions.
- **FR-012**: The `collection_matcher` package MAY be importable inside the
  image (it shares the component's dependency set) but its workflows
  (published-DuckDB access) are explicitly not containerized, configured, or
  documented by this feature.

### Key Entities

- **Container image**: one build artifact for the whole component; contains
  code and dependencies only — no state, no secrets, no personal data.
- **Compose service (opt-in)**: the scan server's long-running definition;
  profile-gated so it is invisible to the default demo-stack startup.
- **State mount**: the single host directory (`collection-agent/data/`)
  holding snapshot, journals, and eval artifacts; the only writable boundary
  shared between host and container runs.
- **Environment file**: the repo-root `.env`; the only source of secrets and
  configuration for both host and container runs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a machine with Docker and a populated `.env`, the scan
  server goes from "nothing running" to serving the phone page with one
  documented command, and a phone on the same network completes one
  scan-and-add whose journal line and snapshot staleness mark appear under
  the host's `collection-agent/data/` — with no Python installed on the host.
- **SC-002**: `docker compose up` with no profile and a token-less `.env`
  starts exactly the same service set as the commit before this feature
  (verified by listing created containers), and the automated guard fails
  when a service is added to or removed from the default set.
- **SC-003**: A snapshot produced by a containerized `sync` is reported
  complete, with identical counts, by a host-venv `status` — and one produced
  on the host is reported identically inside the container (state
  interchangeability in both directions).
- **SC-004**: An audit of the built image finds no `.env` content, no Discogs
  or OpenAI credentials, and no files from `collection-agent/data/`.
- **SC-005**: All 536 pre-existing collection-agent tests pass unmodified,
  and `git diff` for the feature shows zero changes under
  `collection-agent/src/`.
- **SC-006**: A containerized invocation that fails configuration (e.g.
  missing token on an explicit scan-service start) exits with the component's
  configuration exit code and a human-readable error, observable via the
  container's exit status and logs.

## Assumptions

- The deployment target for this feature is the owner's machine (Docker
  Desktop on macOS) and, later, any single Linux Docker host; multi-tenant
  cloud deployment is a future feature and imposes no requirements here.
- Publishing container port 8022 on the host makes the page reachable from
  phones on the same network (the established pattern already used by the
  agent API and frontend services); host-network mode is not required.
- The repo-root `.env` already exists and is gitignored; it remains the
  single configuration source for all components (established by the agent
  API service and by 021's variable-naming separation, which already resolved
  the only known cross-component variable collision).
- The host-venv workflow remains fully supported; containerization is
  additive, not a replacement, and the two may be mixed freely within one
  workflow because all state lives in the mounted directory.
- The scan server's trusted-LAN, plain-HTTP, no-page-auth stance (recorded as
  a v1 risk in 022 and reaffirmed at T041) is unchanged; running in a
  container neither widens nor narrows that exposure as long as the port is
  published only on the home LAN.
- Image registry publication, CI image builds, and image versioning are out
  of scope; the image is built locally by compose.
- Out of scope (owner-confirmed): AWS deployment work, multi-tenancy, Discogs
  OAuth, auth/TLS on the scan server, a web surface for `chat`, and
  containerizing the `collection_matcher` workflows.
