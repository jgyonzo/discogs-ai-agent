# Research: Agent Frontend V1

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

This document records the five non-trivial decisions taken during Phase 0 of the plan. Each decision states what was chosen, why, what was rejected, and what would change the answer in the future.

---

## R1 — Container packaging strategy

**Question**: ship V1 with Vite's dev server in the container, or with nginx serving a static build?

### Decision

V1 ships the **Vite dev server** in the container. Port 5173, command `npm run dev -- --host 0.0.0.0`.

### Rationale

- **Simplicity wins on a local demo path.** The dev server has zero build-cache/zero-stage-image complexity. It's one `npm install && npm run dev` and the `Dockerfile` is six lines.
- **Hot reload helps demo prep.** During the morning of Demo Day, tweaking copy or styling without rebuilding the image is genuinely useful.
- **Performance delta is irrelevant.** Spec NF-005 makes V1 local-only; the user is the presenter on a single laptop, not 1k req/s. The dev server's HMR overhead is sub-100ms and the bundle is tiny.
- **Backend speed dominates.** End-to-end time is gated by the LLM call (single-digit seconds for cheap-model). Dev-server bundle vs. nginx-served static delta is in the tens of milliseconds — invisible behind a 5-15s agent run.
- **Operational consistency.** The agent component in this repo runs in dev shape too (no nginx in front of FastAPI). One demo, one operational shape.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Multi-stage `Dockerfile` building a static bundle, served by nginx on port 80 | Production-shape adds two image layers (`node` build, `nginx` serve), a `.dockerignore`, and an `nginx.conf`. None of it serves the V1 demo. Captured below as the upgrade recipe in case V1.1 wants it. |
| Build static, serve with `python -m http.server` from the `agent` container | Conflates the frontend into the agent — violates Principle VI (each component has its own packaging). |
| Run frontend on the host (no container), backend in compose | Splits the bring-up command in half. Spec SC-007 requires one documented command for the whole stack. |

### What would flip this decision

- A real production deployment (out of V1 scope per NF-005). The static-build path documented below would land then.
- A Demo Day environment that blocks WebSocket upgrades (Vite HMR uses ws). Unlikely on a presenter's laptop, but if so, switch to the static-build path.

### Upgrade recipe (V1.1, deferred)

When the static path is needed, replace the Dockerfile with a two-stage build:

```dockerfile
# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: serve
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

The compose service maps `3000:80`, the env var `VITE_API_BASE_URL` is baked at build time (Vite inlines `import.meta.env.*`), and the `default.conf` adds a `try_files $uri $uri/ /index.html;` rule so client-side routes 404-resolve to the SPA shell.

---

## R2 — CORS configuration on the agent

**Question**: where does the agent's CORS allowance live, and what does it allow?

### Decision

Add `fastapi.middleware.cors.CORSMiddleware` in `agent/src/discogs_agent/api.py` directly after the `FastAPI(...)` constructor and before any route registration. Allowed origins come from a new `CORS_ALLOWED_ORIGINS` field on the existing `Settings` (`pydantic-settings`) class, defaulting to `["http://localhost:5173", "http://localhost:3000"]`. Allowed methods: `["GET", "POST", "OPTIONS"]`. Allowed headers: `["*"]`. **`allow_credentials = False`** — V1 does not use cookies or session-bearer auth.

The exact prose to add to `004/contracts/api.md` (a new section "8. Cross-origin policy") is captured in [`contracts/amendment-004-api-cors.md`](./contracts/amendment-004-api-cors.md).

### Rationale

- **Principle VII.a**: origins are settings-sourced, not hardcoded. An operator can override per-environment without editing source.
- **Tightest reasonable defaults**: the two ports the spec already nails down (`5173` for dev-server V1, `3000` reserved for the V1.1 static-build path). Anything else is opt-in via env.
- **`allow_credentials = False` is non-negotiable for V1**: the frontend does not send cookies and the agent has no per-user state. Granting credentials would be a footgun (browsers refuse `*` origins when credentials are allowed, so it would also remove our future flexibility).
- **`OPTIONS` is required**: browsers preflight POSTs with `Content-Type: application/json`. Without `OPTIONS`, the browser blocks the actual `POST /query`.
- **Centralizing in `api.py`** keeps the agent's wiring readable; route modules (`api_query.py`, `api_admin.py`) attach to the same `app` and inherit the middleware.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| `allow_origins = ["*"]` (wildcard) | Works for the demo but trains a bad pattern and breaks immediately on the day someone wants to add credentials. Settings-driven explicit list is no harder. |
| Origin allowance in nginx (production-shape) | V1 doesn't have nginx (R1). Even when V1.1 adds it, CORS-at-the-app is simpler than CORS-at-the-proxy: the app already has settings; the proxy would need its own template. |
| Per-route CORS decoration | Splits the policy across files; makes drift inevitable. CORS is an app-wide policy. |
| Hardcoded origin list inside `api.py` | Direct violation of Principle VII.a. |

### What would flip this decision

- A multi-origin demo where the frontend is served from a different host than the agent. Settings already supports overrides — set `CORS_ALLOWED_ORIGINS=["https://demo.example.com"]` in `.env`, no code change.
- Adding cookie-based auth in a future feature. That's a deliberate change with cascading review (`allow_credentials=true` interacts with same-site cookies, secure-context requirements, and explicit-origins).

---

## R3 — Iframe sandbox attributes

**Question**: how do we render the agent's chart artifact (an HTML file with inline Plotly JS) safely in the page?

### Decision

```tsx
<iframe
  src={absoluteArtifactUrl}
  sandbox="allow-scripts"
  title="Generated chart"
/>
```

- `src` is the absolute URL to `/artifacts/{artifact_id}` (computed by the API client from `VITE_API_BASE_URL` + the agent-supplied relative URL).
- `sandbox="allow-scripts"` — required because Plotly inline-JS must execute.
- **No** `allow-same-origin`. **No** `allow-forms`. **No** `allow-popups`.

### Rationale

- **`allow-scripts` alone keeps the iframe in a unique opaque origin.** Even though the artifact is served by the same agent backend, browsers treat it as a different origin from the host page (different scheme:host:port pairs once you cross the iframe boundary), and the lack of `allow-same-origin` means the iframe cannot read the parent's cookies, localStorage, or DOM, and the parent cannot reach in either.
- **`srcDoc` was rejected.** That pattern requires fetching the HTML, embedding it as a string, and re-rendering. It (a) duplicates the network round-trip, (b) brings Plotly's bytes into our React tree state, (c) requires `dangerouslySetInnerHTML`-adjacent semantics to inject — the spec FR-021 explicitly bans those patterns.
- **`dangerouslySetInnerHTML` was rejected.** Spec FR-021. Period.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| `srcDoc={htmlString}` (fetch HTML, then inline) | Two round-trips, more state, no security benefit, costs ~4 MB of React state per chart. |
| `dangerouslySetInnerHTML` | Bans imposed by FR-021 + general XSS hygiene. Plotly HTML *should* be safe, but our trust boundary stops at the agent — we don't re-inherit its HTML into our origin. |
| Render Plotly charts client-side from JSON specs (Plotly.js in the frontend) | This is the V1.1 stretch ("CSV browser rendering", spec NF-004). Defers correctly to a later feature. |
| Webview/`object`/`embed` tags | Same isolation properties as `iframe` but with worse browser support and no compelling reason to pick them. |

### What would flip this decision

- A chart artifact format that requires same-origin (e.g., a chart that loads data via `fetch('/some-relative-url')`). The agent's V1 charts are self-contained Plotly HTML, so this isn't a current concern.
- A future feature where the iframe needs to communicate user actions back to the parent (e.g., "user clicked a bar in the chart, drill down"). At that point, deliberately add `postMessage`-based communication — *still* without `allow-same-origin`.

---

## R4 — Error message translation

**Question**: the agent has two failure surfaces (controlled-failure HTTP-200 with `status: "failed_*"`, and HTTP 4xx/5xx with the standard error envelope). How does the frontend map each to user-visible copy?

### Decision

Two-tier mapping, implemented in `frontend/src/utils/errors.ts`:

1. **HTTP 200 with `status: "succeeded"`** → render the chart, the SQL panel, the data preview, and the metadata badges. No error UI.
2. **HTTP 200 with `status: "failed_*"`** → render the agent's `response` field as the assistant's text reply (it's already user-friendly per `004/contracts/api.md` "controlled-failure paths"). Show the "no chart available" placeholder. Show the SQL/preview/metadata panels only if their fields happen to be populated. **Do not** show an error banner — these are agent-classified expected outcomes.
3. **HTTP 4xx / 5xx with `{ "error": { "code", "message", "details" }}`** → look up `error.code` in a small dictionary and show the mapped user-facing string in `ErrorBanner`. Unknown codes fall back to a generic "Something went wrong on the agent side. Try again or rephrase." message.
4. **Network error / unreachable backend** → show "The agent is not reachable. Check that the local stack is running." This covers `TypeError: Failed to fetch`, abort errors, and timeouts.
5. **Malformed JSON / shape mismatch** → show a generic "The agent returned an unexpected response." message and log the parse error to the browser console (developer-facing, not user-facing).

### The mapping dictionary (V1)

| `error.code` from agent | User-facing copy |
|------------------------|------------------|
| `invalid_request` | "The question couldn't be parsed. Try rephrasing it." |
| `thread_not_found` | (Special-case: silently start a new conversation; do not show a banner.) |
| `duckdb_unavailable` | "The catalog isn't available right now. Check that the agent's database is mounted." |
| `database_unavailable` | "The agent's session store isn't available right now." |
| `internal_error` | "Something went wrong on the agent side. Try again or rephrase." |
| (unknown) | "Something went wrong on the agent side. Try again or rephrase." |
| (network) | "The agent is not reachable. Check that the local stack is running." |
| (parse) | "The agent returned an unexpected response." |

The `thread_not_found` case is intentionally silent: the only way the frontend produces this is by sending a stale `thread_id` from `localStorage` after the backend was reset. Spec edge-case behavior says "the next submission starts a new conversation transparently; the user sees no error." Implementation: on `thread_not_found`, clear `localStorage.currentThreadId`, drop the `thread_id` from the request payload, and retry once.

### Rationale

- **Spec FR-016 forbids raw tracebacks**, which the agent already enforces server-side (`final_response` never carries traceback prose; tracebacks live in admin-mode `errors[].traceback` only). The frontend never surfaces tracebacks — its only inputs are the user-friendly fields.
- **Controlled-failure HTTP-200 is by-design**, not an error. Treating it as an error would crowd the UI with banners every time the agent says "I can't answer that — price data isn't part of the catalog." The agent has already authored a friendly message; the frontend's job is to display it.
- **Unknown-code fallback** prevents the UI from blanking when the agent is updated with a new error code the frontend doesn't yet recognize.

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Show `error.message` verbatim from the agent's error envelope | Risks exposing internal details (file paths, DB names) the agent might include. Curated dictionary keeps user copy in our control. |
| Treat `failed_*` HTTP-200 as errors and show banners | Conflates "agent can't answer this question" with "agent crashed." Different mental models for the user. |
| Auto-retry on any 5xx | Spec FR-015 disables input during a single in-flight request; auto-retrying without user consent would queue submissions the user thinks were dropped. Better to surface and let the user re-submit. |
| Toast-style ephemeral errors | A persistent banner is harder to miss. The spec says "concise, non-technical" — concise is fine in a banner. |

### What would flip this decision

- A failure mode the agent expects the frontend to *act* on (e.g., "user must re-authenticate"). V1 has no auth (NF-001), so this isn't on the table.

---

## R5 — State management

**Question**: do we need a state-management library?

### Decision

No external library. The app uses:

- `useState` for transient UI state (input text, panel collapsed/expanded, copy-to-clipboard state).
- A single `useReducer` in `App.tsx` for the chat-message timeline + active-query state machine.
- One custom hook `useThreadId()` that wraps `localStorage` access and keeps the in-memory view in sync.

The reducer's state shape is captured in [`data-model.md`](./data-model.md).

### Rationale

- **Spec is bounded.** Single page, single conversation in flight, no cross-route persistence, no multi-component data sharing beyond a parent-child tree. `useReducer` plus prop drilling covers it.
- **Reducer-not-state is justified by the message-append flow.** The message-timeline transitions (add user message → start loading → add assistant message → end loading; or → error → end loading) need to be atomic and testable. A reducer with named action types makes those transitions visible and unit-testable in isolation. `useState` alone would scatter the same logic across multiple `setState` calls.
- **No external store avoids learning-curve overhead** and avoids one more dependency to keep current.

### State shape (preview; full schema in `data-model.md`)

```ts
type AppState = {
  threadId: string | null;
  messages: ChatMessage[];          // append-only; new conversation clears
  current: {
    artifact: ChartArtifact | null;
    sql: string | null;
    dataframePreview: Record<string, unknown>[];
    metadata: RunMetadata | null;
  };
  pending: boolean;                  // a query is in flight
  error: UserFacingError | null;
};

type Action =
  | { type: "submit"; userMessage: string }
  | { type: "responseSucceeded"; assistant: ChatMessage; ... }
  | { type: "responseFailedControlled"; assistant: ChatMessage; ... }
  | { type: "responseError"; error: UserFacingError }
  | { type: "newConversation" };
```

### Alternatives considered

| Alternative | Why rejected |
|------------|--------------|
| Redux (or RTK) | Overkill for one page. The brief explicitly recommends against it. |
| Zustand | Lower ceremony than Redux but still adds a dep for no clear benefit. |
| `useState` everywhere, no reducer | Possible, but the message-append-with-error-fork flow is exactly what reducers are for. Multiple `setState` in series is a known race-shape. |
| React Query / SWR for the `/query` call | Tempting (it would cache and dedupe), but `/query` is explicitly non-idempotent (`004/contracts/api.md` §6) — caching would be wrong, and we never re-fetch a stale value. The custom mutation flow is simple. |

### What would flip this decision

- Multiple pages or routes sharing in-memory conversation state. Out of V1 scope.
- Real-time streaming responses (token-by-token). The agent's `/query` is request/response; streaming is future work.

---

## Cross-decision invariants

A handful of things were decided implicitly across multiple research items; recording them here so they don't get lost:

- **The frontend never reads the response's `code` field.** `004/contracts/api.md` defines `code` as the generated Python (only populated when `debug=true`). The frontend always sends `debug: false` (or omits the field). FR-018 forbids exposing it; even if the backend sent it, we wouldn't display it.
- **The frontend never sends the `X-Agent-Admin` header.** The admin token is a backend-internal mechanism, and `004/contracts/api.md` §3 explicitly notes admin mode requires the header. V1 has no admin UI.
- **The frontend ignores `carryover.preamble`.** That field is internal to the agent's prompt-augmentation logic. The spec only requires that follow-up questions continue the conversation (US3), which is handled by sending the `thread_id` — not by inspecting carryover state.
- **Artifact URLs are normalized at the API client boundary.** The agent returns `chart_artifact.url = "/artifacts/<id>"` (relative). The client wraps it in `${VITE_API_BASE_URL}${url}` when consumed. This is the only place URL composition happens.
