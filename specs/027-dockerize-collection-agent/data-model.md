# Data Model: Dockerize the collection-agent

**Feature**: `027-dockerize-collection-agent` · **Date**: 2026-07-12

This feature introduces no new runtime data — no models, no Settings fields,
no journal/snapshot/eval schema changes (FR-009). Its "entities" are packaging
artifacts and the boundaries between them. The normative shapes live in
`contracts/docker-packaging.md`; this file records the entities and their
relationships.

## Entities

### Container image (`collection-agent`)

One build artifact for the whole component.

| Property | Value | Source of truth |
|---|---|---|
| Build context | `collection-agent/` only (never repo root) | Dockerfile location + compose `build.context` |
| Contents | `pyproject.toml`, `src/`, `README.md`, installed deps — nothing else | Dockerfile COPY allowlist + `.dockerignore` denylist (R7) |
| Install mode | Editable at `/app/collection-agent` | R2 — anchors `_COMPONENT_ROOT` |
| Entrypoint | `python -m collection_agent` | FR-001 |
| Default command | `scan` | FR-001 (CLI's own default is `chat`; the image pins the service mode) |
| Excluded | secrets, `.env`, `data/` contents, `.venv/` | FR-007, SC-004 |

**Invariant**: the image is stateless and personal-data-free; deleting and
rebuilding it loses nothing.

### Compose service (`collection-agent`, opt-in)

The scan server's long-running definition inside the existing
`docker-compose.yml`.

| Property | Value | Why |
|---|---|---|
| `profiles` | `["collection"]` | FR-003 — invisible to profile-less `up` |
| `ports` | `8022:8022` | FR-002, R8 |
| `env_file` | repo-root `.env` | FR-007, R5 |
| `volumes` | `./collection-agent/data:/app/collection-agent/data` | FR-006, R2 |
| `depends_on` | none, in either direction | FR-005 |
| `restart` | none (default `"no"`) | FR-010, R3 — startup validation failure must not retry-loop |
| `healthcheck` | none | R3 — no dependent to gate |

**Invariant**: the default (unprofiled) service set of the compose file is
exactly `{postgres, agent-api, frontend}`, pinned by guard test (FR-004).

### State mount

The single writable boundary shared between host-venv and container runs.

| Host path | Container path | Contents |
|---|---|---|
| `collection-agent/data/` | `/app/collection-agent/data/` | `snapshot.json`, `scan-sessions/*.jsonl`, `eval/discogs-images/`, `eval/runs/`, `eval/scan-photos/` |

**Relationship**: every path-typed Settings default resolves under
`_COMPONENT_ROOT/data/` (settings.py:17 anchoring), which the editable
install places at `/app/collection-agent/data/` — i.e. inside this mount.
Host and container therefore read/write the *same files* with no overrides
(R2). State transitions (snapshot complete/partial/stale, journal
append-only, eval resume) are untouched — they are properties of the
process, not the packaging.

### Environment flow

The single configuration path for both run styles.

```
repo-root .env ──(host venv: pydantic-settings env_file)──▶ Settings
repo-root .env ──(compose env_file → process env)─────────▶ Settings
```

**Invariant**: identical variable names, identical precedence outcome
(process env wins; absent env-file paths are ignored) — a variable set in
`.env` configures both run styles identically. No variable is duplicated
into `environment:` blocks (R5).

## New test surface (guards, not data)

| Guard | Pins | FR |
|---|---|---|
| Default-service-set parse | `{postgres, agent-api, frontend}` unprofiled, exactly | FR-004 |
| Profile presence | `collection-agent` service carries `collection` profile | FR-003 |
| Isolation | no `depends_on` touching `collection-agent`; no `restart:` on it | FR-005, FR-010 |
| Dockerfile hygiene | COPY allowlist only; no `.env`/`data/` references; CMD is `scan` | FR-001, FR-007 |
| `.dockerignore` hygiene | `data/`, `.env`, `.venv/` excluded | FR-007 |
