# Contract: collection-agent Docker packaging

**Feature**: `027-dockerize-collection-agent` · **Status**: normative once merged
**Scope**: how the collection-agent component is built into an image, wired
into the repo compose file, and invoked. This is a NEW contract — it amends
nothing: the component's CLI surface, scan API (022 + amendments), journal
schema, eval layouts, and Discogs consumption (017 + amendments) are all
byte-identical inside and outside the container.

## 1. Image contract

- **Build context**: `collection-agent/` — never the repo root. The build
  MUST NOT be able to read the repo-root `.env` or any sibling component.
- **Contents allowlist**: the Dockerfile COPYs exactly `pyproject.toml`,
  `src/`, and `README.md` into `/app/collection-agent/`. Nothing else enters
  a layer.
- **Context denylist**: `collection-agent/.dockerignore` MUST exclude at
  least `data/`, `.env`, `.venv/`, `__pycache__/`, `*.pyc`,
  `.pytest_cache/`, `notebooks/`, `tests/`.
- **Install**: editable (`pip install -e /app/collection-agent`), so that
  `settings.py`'s `_COMPONENT_ROOT` (`Path(__file__).resolve().parents[2]`)
  resolves to `/app/collection-agent` and every path-typed Settings default
  lands under `/app/collection-agent/data/` (research R2). A non-editable
  install is a contract violation — it silently breaks every default path.
- **Entrypoint/command**: `ENTRYPOINT ["python", "-m", "collection_agent"]`,
  `CMD ["scan"]`. Every CLI subcommand (`sync`, `status`, `chat`, `scan`,
  `eval-dataset`, `eval-run`) MUST be reachable by argument substitution.
- **Statelessness**: the image contains no secrets, no `.env` content, no
  `collection-agent/data/` content. Rebuilding from a clean checkout loses
  nothing.
- **Exit codes**: the container's exit status is the CLI's exit code,
  verbatim: `0` ok · `1` unexpected · `2` configuration · `3` partial sync.

## 2. Compose contract

The service is added to the existing repo-root `docker-compose.yml`:

```yaml
  collection-agent:
    build:
      context: ./collection-agent
      dockerfile: Dockerfile
    profiles: ["collection"]
    env_file:
      - .env
    ports:
      - "8022:8022"
    volumes:
      - ./collection-agent/data:/app/collection-agent/data
```

Normative properties (each guard-tested, §4):

- **Opt-in only**: `profiles: ["collection"]`. Plain `docker compose up`
  MUST create exactly the pre-027 service set: `postgres`, `agent-api`,
  `frontend`. Any change to the default set — in either direction, from any
  future feature — is a contract violation.
- **Isolation**: no `depends_on` on the `collection-agent` service, and no
  existing service may name it. The existing services' definitions are
  unchanged by this feature.
- **Failure posture**: NO `restart:` policy. The scan server validates the
  Discogs folder live at startup and exits `2` on failure; an auto-restart
  would convert that loud single exit into an unbounded live-API retry loop
  (spec FR-010). If a future feature adds a restart policy it MUST first
  solve startup-validation backoff.
- **No healthcheck** (v1): nothing depends on the service; container status
  and logs are the observability surface.
- **Configuration**: `env_file: .env` (repo root) only. Variables MUST NOT
  be duplicated into `environment:` blocks; the `.env` file is the single
  configuration source for host and container runs alike.
- **State**: exactly one bind mount, `./collection-agent/data` ↔
  `/app/collection-agent/data`, read-write. No other host path is visible.

## 3. Invocation contract

| Host-venv form | Containerized form |
|---|---|
| `python -m collection_agent scan` | `docker compose --profile collection up collection-agent` (service; port published) |
| `python -m collection_agent sync` | `docker compose run --rm collection-agent sync` |
| `python -m collection_agent status` | `docker compose run --rm collection-agent status` |
| `python -m collection_agent chat` | `docker compose run --rm collection-agent chat` (TTY allocated by `run`) |
| `python -m collection_agent eval-dataset [...]` | `docker compose run --rm collection-agent eval-dataset [...]` |
| `python -m collection_agent eval-run [...]` | `docker compose run --rm collection-agent eval-run [...]` |

- `docker compose run` auto-activates the named service's profile — one-off
  invocations need no `--profile` flag.
- `run` does not publish ports; `scan` via `run` is therefore NOT a
  documented form (use `up`).
- Both forms read and write the same host `collection-agent/data/` files;
  mixing forms within one workflow (sync in container, chat on host, etc.)
  is supported and requires no migration in either direction.
- The phone reaches the scan page at `http://<host-LAN-IP>:8022` — the
  in-container startup banner's self-reported URL is not authoritative for
  phones (research R8).
- Ctrl-C semantics (sync resume journaling, scan-cycle abandonment) are the
  process's own and identical in both forms.

## 4. Guards (enforcement)

New tests in `collection-agent/tests/unit/` (stdlib-only; the compose file
is parsed structurally, not with a YAML dependency — research R4):

1. default (unprofiled) compose service set == `{postgres, agent-api,
   frontend}` exactly;
2. `collection-agent` service exists with profile `collection`;
3. no `depends_on` edge touches `collection-agent`; no `restart:` key on it;
4. Dockerfile: COPY allowlist only, no `.env`/`data/` reference anywhere,
   ENTRYPOINT is `python -m collection_agent`, CMD is `scan`;
5. `.dockerignore`: `data/`, `.env`, `.venv/` present.

All 536 pre-existing collection-agent tests MUST pass unmodified; the
feature adds zero files under `collection-agent/src/`.
