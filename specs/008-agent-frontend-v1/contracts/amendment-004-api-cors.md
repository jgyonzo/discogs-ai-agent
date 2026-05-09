# Amendment to `004/contracts/api.md` — Cross-origin policy

**Source feature**: `008-agent-frontend-v1`
**Target file**: `specs/004-agent-v1/contracts/api.md`
**Insert after**: §7 ("CLI mirror") — as a new top-level §8.

This is the exact prose to land in `004/contracts/api.md` in the same change set as the agent code change (`agent/src/discogs_agent/api.py` adding `CORSMiddleware`, and `agent/src/discogs_agent/config.py` adding the `CORS_ALLOWED_ORIGINS` settings field). Mirrors the structure of the 007 amendment to `004/contracts/code-generation.md §3.1.1`.

---

## Insertion text

```markdown
## 8. Cross-origin policy

The agent is consumed from a browser-based frontend (see `specs/008-agent-frontend-v1/`). FastAPI's `CORSMiddleware` permits cross-origin requests from a configured allowlist of origins.

### 8.1 Default allowlist

| Origin | Purpose |
|--------|---------|
| `http://localhost:5173` | Vite dev-server (default V1 packaging) |
| `http://localhost:3000` | Reserved for the production-shape (nginx-served static build); not yet used |

### 8.2 Override

Settings field: `CORS_ALLOWED_ORIGINS` (comma-separated string parsed into `list[str]`, env-driven via the existing `pydantic-settings` `Settings` class).

```text
# .env.example
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

When set, the value **replaces** the default allowlist (it does not merge). An empty string disables cross-origin entirely.

### 8.3 Allowed methods and headers

| Property | Value | Reason |
|----------|-------|--------|
| `allow_methods` | `["GET", "POST", "OPTIONS"]` | These are the only methods the agent's V1 endpoints use. `OPTIONS` is required for browser CORS preflight on JSON `POST`s. |
| `allow_headers` | `["*"]` | The frontend sends only `Content-Type: application/json`; future headers (e.g., a request id) shouldn't require a contract amendment. |
| `expose_headers` | `[]` | The frontend reads only response bodies; no header-driven behavior. |
| `allow_credentials` | `False` | V1 has no cookie-based or session-bearer authentication. Browsers refuse `*` origins when credentials are allowed; explicit-list-with-no-credentials is both safer and future-flexible. |
| `max_age` | `600` (seconds) | Standard preflight caching window; reduces preflight churn during the demo. |

### 8.4 Endpoints affected

Sections 1-5 (`/query`, `/threads/{id}`, `/runs/{id}`, `/artifacts/{id}`, `/health`) are all affected by this middleware. The middleware runs ahead of all route handlers; per-endpoint behavior is unchanged.

### 8.5 What this policy does NOT do

- Does not bypass admin-mode gating on `/runs/{id}` (§3). `X-Agent-Admin` and the configured token still gate admin-mode responses; CORS only governs which *origins* may attempt the request.
- Does not bypass body-size limits, `message` length validation, or any other request-shape gate.
- Does not interact with the read-only DuckDB invariant (`004/contracts/code-generation.md §3.1.1` — Constitution VII.c). CORS is a network-policy concern; the data layer is unchanged.

### 8.6 Configuration source rationale (Constitution VII.a)

`CORS_ALLOWED_ORIGINS` is settings-sourced rather than hardcoded so that an operator deploying the agent at a different origin can override without editing source. Hardcoded localhost defaults are acceptable as the V1 demo target (Spec NF-005); production deployments will set the env var explicitly.

### 8.7 Named precedent

This subsection was added by feature `008-agent-frontend-v1` ("Agent Frontend V1"). The browser-based UI is the only V1 cross-origin consumer; non-browser consumers (CLI, integration tests) are unaffected because they don't enforce CORS.
```

---

## Why amend `004` rather than create a new `008/contracts/api.md`

Same reasoning as the 007 amendment to `004/contracts/code-generation.md`:

- The agent's HTTP API is a single contract surface owned by `004`. Splitting it across multiple specs would force readers to chase the cross-origin policy through the spec history.
- CORS is not a *new* endpoint or *new* response shape; it's a wire-protocol property of the existing endpoints.
- This pattern keeps `004/contracts/api.md` the single source of truth for "what the agent's HTTP API does" — consistent with how 007 kept `004/contracts/code-generation.md` the single source of truth for "what the sandbox enforces."

## Implementation pointer

The amendment lands together with:

- `agent/src/discogs_agent/api.py` — `app.add_middleware(CORSMiddleware, allow_origins=settings.cors_allowed_origins, allow_methods=["GET","POST","OPTIONS"], allow_headers=["*"], allow_credentials=False, max_age=600)` immediately after the `app = FastAPI(...)` line and before any route module imports.
- `agent/src/discogs_agent/config.py` — `cors_allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]` (using the `pydantic-settings` `field_validator` pattern already in use in that file to parse comma-separated strings into lists).
- `agent/.env.example` — add the `CORS_ALLOWED_ORIGINS` line shown in §8.2.

No new dependencies (`fastapi.middleware.cors` ships with FastAPI). No tests for the middleware itself (it's a one-line FastAPI integration); the cross-origin behavior is covered end-to-end by `frontend/tests/integration/full-flow.test.tsx` running against the live agent in the docker-compose smoke test.
