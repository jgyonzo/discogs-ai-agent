# Research: Dockerize the collection-agent

**Feature**: `027-dockerize-collection-agent` · **Date**: 2026-07-12

Each entry: Decision / Rationale / Alternatives considered.

## R1 — Base image & install strategy: mirror `agent/Dockerfile`, editable install

**Decision**: `python:3.12-slim` base; copy only `pyproject.toml`, `src/`,
`README.md` into `/app/collection-agent/`; `pip install -e
/app/collection-agent` (no extras — `dev` is pytest only, not needed at
runtime); `PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1`.
No `build-essential`: every dependency (openai, httpx, pydantic(-settings),
rich, langsmith, fastapi, uvicorn, python-multipart, duckdb, pandas,
rapidfuzz) ships manylinux wheels for amd64 and arm64 on Python 3.12. No
`curl` (no healthcheck — see R3).

**Rationale**: `agent/Dockerfile` is the repo's proven pattern
(python:3.12-slim + editable install under `/app/<component>/`); parity keeps
the two Dockerfiles reviewable side by side. The editable install is
load-bearing, not stylistic — see R2. Dropping build tools keeps the image
smaller than the agent's and is safe because the dependency set is
wheel-complete; if a future dependency needs compilation the build fails
loudly at image-build time, not at runtime.

**Alternatives considered**: (a) Non-editable install — rejected, breaks path
anchoring (R2). (b) Multi-stage build with a venv — rejected as complexity
without a driver; the single-stage editable install is what the agent ships.
(c) Installing `[dev]` to run pytest in-container — rejected; tests run on
the host (repo convention: `cd collection-agent && pytest`), and the guard
tests need repo-root files that aren't in the image anyway.

**Note on image weight**: `duckdb`/`pandas`/`rapidfuzz` are in the manifest
only for the `collection_matcher` sibling package (FR-012: importable, not
containerized as a workflow). One component = one manifest = one image
(Constitution VI); the ~150 MB they add is accepted rather than forking the
dependency manifest.

## R2 — Path anchoring: editable install at a repo-shaped path makes every default resolve into the mount (the spec's FR-006/FR-009 tension dissolves)

**Decision**: The image places the component at `/app/collection-agent` and
installs it editable; compose mounts `./collection-agent/data` at
`/app/collection-agent/data`. No path-related environment overrides, no new
Settings fields, no source changes.

**Rationale**: `settings.py:17` anchors all path defaults to the *source file
location*, not the CWD:

```
_COMPONENT_ROOT = Path(__file__).resolve().parents[2]   # collection-agent/
_REPO_ROOT = _COMPONENT_ROOT.parent                      # repo root
```

With an editable install, `settings.py` stays at
`/app/collection-agent/src/collection_agent/settings.py`, so
`_COMPONENT_ROOT = /app/collection-agent` and every default —
`snapshot_path`, `scan_journal_dir`, `eval_dataset_dir`, `eval_results_dir`,
`scan_retention_dir` — resolves under `/app/collection-agent/data/...`, i.e.
inside the mount, i.e. onto the same host files the venv workflow uses.
`_REPO_ROOT/.env` resolves to `/app/.env`, which does not exist in the
container — harmless, because configuration arrives as process environment
(R5) and pydantic-settings treats a missing `env_file` path as empty, exactly
as it does today on hosts without a component-local `.env`.

This satisfies FR-006 (state interchangeability) **and** FR-009 (zero source
changes) simultaneously; the escape hatch FR-009 reserved (a defaulted
path-override Settings field) is not needed.

**Alternatives considered**: (a) Non-editable install — `__file__` lands in
`site-packages`, `parents[2]` points at
`/usr/local/lib/python3.12`, every default path breaks; would force env
overrides for all five path fields and make container behavior diverge from
host behavior. Rejected. (b) Env-var overrides for all paths in the compose
file — works but duplicates five settings that already default correctly
under (this) R2's layout, and each duplicate is a drift site (VII(a) spirit).
Rejected. (c) A new `COLLECTION_AGENT_DATA_DIR` umbrella setting — source
change, violates FR-009 for no gain. Rejected.

## R3 — Service gating & failure posture: compose profile, no restart policy, no healthcheck

**Decision**: The compose service is named `collection-agent`, carries
`profiles: ["collection"]`, has **no** `restart:` policy (default `"no"`),
**no** `healthcheck`, and **no** `depends_on` in either direction.

**Rationale**: Profiles are the compose-native opt-in: services with a
profile are excluded from profile-less `docker compose up` (US2/FR-003), and
`docker compose --profile collection up` or explicitly naming the service
starts it. The absent restart policy is deliberate and load-bearing: the scan
server validates the configured Discogs folder **live at startup** and exits
`EXIT_CONFIG` (2) on failure; under `restart: unless-stopped` (the agent-api
pattern) that exit becomes an infinite loop of live Discogs calls — exactly
the "silent retry loop" FR-010 forbids. One loud exit, visible in
`docker compose ps`/logs, is the correct failure posture for an
owner-operated LAN tool. No healthcheck because nothing depends on the
service (no `depends_on` consumer exists to gate on it) and adding one would
require `curl` in the image; container up/exited status plus logs is the v1
observability surface.

**Alternatives considered**: (a) `restart: unless-stopped` for agent-api
parity — rejected per above (agent-api's restart never calls a third party;
this one would). (b) Healthcheck against `GET /` — rejected v1: adds curl and
answers a question nobody (human or compose) is asking; revisit if a future
feature adds a dependent service. (c) Gating via a separate compose file
(`docker-compose.collection.yml` + `-f` stacking) — rejected: profiles are
first-class, keep one file authoritative, and the guard test (R4) can pin one
file's default service set.

## R4 — The default-service-set guard: stdlib structural parse, zero new dependencies

**Decision**: New unit test module in `collection-agent/tests/unit/`
(working title `test_docker_packaging.py`) reads the repo-root
`docker-compose.yml` (path derived from the test file location, the 023
precedent of pinning the repo-root `.gitignore`) and asserts, via a minimal
indentation-based parse (stdlib only — no PyYAML):

1. the set of top-level services carrying **no** `profiles:` key is exactly
   `{postgres, agent-api, frontend}` (FR-004 — fails if a default service is
   ever added or removed);
2. the `collection-agent` service exists and its `profiles` list contains
   `collection` (FR-003);
3. the `collection-agent` service block contains no `depends_on:` and no
   other service's block references `collection-agent` (FR-005);
4. the `collection-agent` service block contains no `restart:` key (R3's
   posture, pinned).

Sibling grep-guards in the same module pin the hygiene surface: the
`.dockerignore` excludes `data/`, `.env`, and `.venv/` (FR-007); the
Dockerfile COPYs only the sanctioned set and never references `.env` or
`data/`; the Dockerfile's default command is `scan`.

**Rationale**: The component has a zero-new-dependencies streak (025, 026)
worth keeping for a packaging feature of all things; the compose file is
hand-maintained, two-space-indented YAML whose *service-name / profiles /
depends_on / restart* shape is fully recoverable from line structure —
the guard needs exactly that shape, not a YAML object model. Structural
grep-guards are the repo's established enforcement idiom (019 URL shapes,
022 secrets-never-on-the-wire, 023 gitignore pin, 026 link-shape guards).

**Alternatives considered**: (a) PyYAML — a new dependency to parse one file
whose relevant shape is line-structural; rejected. (b) `docker compose
config --format json` in the test — requires a Docker daemon in the test
environment; the suite is hermetic/offline by hard convention; rejected.
(c) Pinning by file hash — brittle against unrelated compose edits; rejected.

## R5 — Configuration flow: compose `env_file` → process environment; no `.env` inside the container

**Decision**: The service uses `env_file: [.env]` exactly like agent-api.
The image contains no `.env` (never COPYed; `.dockerignore` excludes a
hypothetical component-local one as defense in depth). All configuration
reaches the process as real environment variables.

**Rationale**: pydantic-settings precedence puts process env above
`env_file` sources, and `Settings.model_config` treats its two `env_file`
paths as optional — on the host today, `collection-agent/.env` doesn't exist
and loading works; in the container, `/app/.env` won't exist and loading
works identically. The secrets boundary (constitution: `.env` never
committed, never baked) holds because the build context can't even see the
repo root (context = `./collection-agent`), and the runtime file never enters
the image — compose injects values at container start. Missing `.env` at
`docker compose` invocation fails with compose's own clear "env file not
found" error, the same behavior agent-api users already get (spec edge case
"`.env` absent entirely" satisfied).

**Alternatives considered**: (a) Mounting `.env` into the container — puts a
secrets file inside a running container's filesystem for zero benefit over
env injection; rejected. (b) `environment:` blocks enumerating variables —
a drift site per variable (VII(a) spirit: one source, not a copied list);
rejected.

## R6 — One-off and interactive modes: `docker compose run --rm`

**Decision**: Document `docker compose run --rm collection-agent <subcommand>
[flags]` as the containerized form of `sync`, `status`, `chat`,
`eval-dataset`, and `eval-run`. The image's ENTRYPOINT is
`python -m collection_agent` with CMD `scan`, so `run` arguments replace only
the subcommand.

**Rationale**: `docker compose run` starts an explicitly named service even
when its profile is not activated (compose auto-enables the named service's
profiles), so one-off commands need no `--profile` flag. It allocates a TTY
and attaches stdin by default when the invoking terminal is interactive —
`chat`'s rich prompt loop and the y/N write-confirmation gates work
unchanged; from a non-interactive caller, stdin is closed and `chat` ends
cleanly rather than hanging (the spec's edge case). `run` propagates the
container's exit status verbatim, so `EXIT_OK/ERROR/CONFIG/PARTIAL`
(0/1/2/3) reach the calling shell untouched (FR-008), and Ctrl-C during
`sync` delivers SIGINT — the journal-resume semantics are the process's own,
unchanged. `--rm` keeps one-off containers from accumulating. Note: `run`
does not publish ports by default — irrelevant here, since the only
port-bearing mode (`scan`) runs via `up`; the CLI's *own* default subcommand
is `chat`, which is why the image CMD pins `scan` explicitly for the service
path while `run` always names its subcommand.

**Alternatives considered**: (a) `docker compose exec` into the running scan
service — wrong tool: requires the scan service to be up, shares its
container, and `sync` would then race the server's own snapshot reads;
rejected. (b) Separate compose services per mode (`collection-sync:` etc.) —
five near-identical service blocks to keep in sync; rejected. (c) Raw
`docker run` documentation — loses env_file/volume wiring that compose
already encodes; rejected as the primary form (the compose file IS the
wiring's single source of truth).

## R7 — Build-context hygiene: new `collection-agent/.dockerignore`

**Decision**: Add `collection-agent/.dockerignore` excluding at minimum:
`data/` (32 MB today, unbounded with eval images — and personal/
uploader-copyrighted content), `.venv/` (hundreds of MB), `.env` (defense in
depth; none exists today), `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`notebooks/`, `tests/`. The Dockerfile additionally COPYs only
`pyproject.toml`, `src/`, `README.md` — the allowlist and the denylist
back each other up. Guard-tested (R4).

**Rationale**: FR-007/SC-004 make "no secrets, no personal data in image or
build context" normative. COPY discipline alone leaves the *context upload*
carrying `data/` and `.venv/` to the daemon on every build (slow, and
personal data leaves the working tree even if no layer retains it);
`.dockerignore` alone is one typo away from a leak. Belt and suspenders,
each pinned by a grep-guard. (`agent/` has no `.dockerignore` — its context
is code-only; ours is not, so the asymmetry is justified, not drift.)

**Alternatives considered**: Relying on COPY discipline only (agent parity) —
rejected per above: this component's directory contains the owner's personal
collection data and licensed eval images; 32 MB context uploads are also just
wasteful.

## R8 — LAN reachability: standard port publish; the phone uses the host's LAN IP

**Decision**: `ports: ["8022:8022"]` on the service;
`COLLECTION_AGENT_SCAN_HOST` stays default `0.0.0.0` (required inside a
container for the publish to work). README documents: open
`http://<host-LAN-IP>:8022` on the phone — the startup banner's URL
reflects the *container's* view of its interfaces and is not the address the
phone should use.

**Rationale**: Publishing binds the host's interfaces (all of them,
including the LAN address) on both Docker Desktop/macOS and native Linux —
the same mechanism that already exposes agent-api :8000 and frontend :5173.
The banner caveat is a documentation matter, not a code one (FR-009: the
banner code is not edited; it was written for the host-venv case where its
printed URL is correct).

**Alternatives considered**: (a) `network_mode: host` — not functional on
Docker Desktop for macOS (the "host" is a VM), and unnecessary; rejected.
(b) Restricting the publish to the LAN interface IP — hardcodes a
DHCP-assigned address into the compose file; the 022 trusted-LAN stance
makes all-interfaces acceptable and unchanged in exposure (the host venv
already binds 0.0.0.0). Rejected.

## R9 — File ownership across the container/host boundary

**Decision**: Run as the image default user (root), no `user:` directive in
v1. Document the Linux-host caveat.

**Rationale**: The deployment target of record (spec assumption) is Docker
Desktop on macOS, whose VirtioFS bind-mount mapping presents container-
written files to the host as the desktop user — snapshot/journals written by
the container are fully usable by the venv workflow and vice versa
(SC-003's bidirectional check validates exactly this). On a native Linux
host, container-root-owned files under `collection-agent/data/` would need
`chown`/`user:` handling — a real but out-of-target concern, documented in
the README rather than engineered for (the future AWS feature owns the Linux
runtime story properly, per the spec's context section). Matches agent-api,
which already runs as root with a bind mount on the same hosts.

**Alternatives considered**: `user: "${UID}:${GID}"` plus env plumbing —
solves a problem the target platform doesn't have, at the cost of compose-
file complexity and a new failure mode (unset UID var); rejected for v1.

## R10 — Lockfile: pip-from-pyproject in the image; `uv.lock` stays a host-venv artifact

**Decision**: The image installs with pip resolving from `pyproject.toml`
ranges (agent parity). `uv.lock` (tracked since 019) is not consumed by the
build.

**Rationale**: Reproducible-image builds are a deployment-pipeline concern
that belongs to the future AWS feature (alongside registries, versioning,
CI builds — all spec'd out of scope). Introducing uv into the image now
adds a second installer to the repo's container story for a property nobody
consumes yet; the agent image has shipped on pip-from-ranges since 004.

**Alternatives considered**: `uv sync --frozen` in a multi-stage build —
strictly better reproducibility, and the natural upgrade when the AWS
feature lands CI-built, registry-pushed images; recorded here as the
follow-up candidate rather than done now.
