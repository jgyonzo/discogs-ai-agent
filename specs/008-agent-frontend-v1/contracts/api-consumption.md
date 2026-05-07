# Contract: Frontend → Agent API consumption

**Plan**: [../plan.md](../plan.md) | **Spec**: [../spec.md](../spec.md) | **Backend contract**: [`specs/004-agent-v1/contracts/api.md`](../../004-agent-v1/contracts/api.md)

This contract documents the agent HTTP API shape **as the frontend consumes it**. It is one-way: the agent's contract (`004/contracts/api.md`) is authoritative for the response *shape*; this document defines which fields the frontend reads, ignores, or maps. Drift here against `004` is detectable at compile time (TypeScript types) and at runtime (MSW-backed integration tests).

---

## 1. Endpoints used

| Method | Path | When | Required for V1 |
|--------|------|------|-----------------|
| `POST` | `/query` | On every user submission | Yes |
| `GET` | `/artifacts/{artifact_id}` | Loaded by `<iframe src>` after a successful query | Yes |
| `GET` | `/health` | Optional, for a status badge | Optional (deferred) |
| `GET` | `/threads/{thread_id}` | NOT USED in V1 | No |
| `GET` | `/runs/{run_id}` | NOT USED in V1 | No |

The frontend MUST NOT depend on `/threads/{id}` or `/runs/{id}`. They exist; using them would push us past V1 scope (chat-restore-on-reload is future work).

---

## 2. `POST /query` — request

The frontend sends:

```json
{
  "thread_id": "<from localStorage if present, else omitted>",
  "message": "<user input, 1-2000 chars>"
}
```

**Frontend behavior**:

- `debug` is **never** sent. (Equivalent to `false` per the agent's contract.)
- `thread_id` is included **only** when the frontend has a stored value. Sending `null`, `undefined`, or `""` is forbidden — omit the field.
- `message` is the user's input, trimmed of leading/trailing whitespace, with no client-side rewriting.
- `Content-Type: application/json`. No other headers (no `Authorization`, no `X-Agent-Admin` — V1 has no auth path).

**Validation done client-side before submit** (Spec FR-001 + sane defaults):

- Non-empty after trimming.
- ≤ 2000 chars (mirrors the agent-side limit per `004/contracts/api.md §1`).

If client-side validation fails, the request is not sent and the input is re-enabled with a small inline hint. No banner, no toast.

---

## 3. `POST /query` — response (success and controlled-failure)

HTTP 200 always for these — both success and the agent's classified failure modes. Distinguished by the `status` field.

**Consumed shape** (TypeScript projection; full shape in `004/contracts/api.md §1`):

```ts
type QueryResponse = {
  thread_id: string;                                                    // ALWAYS read
  run_id: string;                                                       // READ for metadata badge
  response: string;                                                     // ALWAYS read; assistant text
  status:
    | "succeeded"
    | "failed_unsupported"
    | "failed_clarification_needed"
    | "failed_safety"
    | "failed_validation";                                              // ALWAYS read; drives UI branching
  route: {
    complexity?: string;
    selected_model?: string | null;
    rationale?: string | null;
  };                                                                    // READ for metadata badges; missing fields hidden
  sql: string | null;                                                   // READ; null hides SQL panel
  code: null;                                                           // IGNORED; FR-018 forbids display
  chart_artifact: { artifact_id: string; url: string; type: "plotly_html" } | null;  // READ; null hides chart
  dataframe_preview: Record<string, unknown>[];                         // READ; capped to first 20 rows on display
  row_count: number;                                                    // IGNORED in V1 (could be shown as "(5 rows)" later)
  carryover: { turn_count: number; preamble: string | null };           // turn_count READ in dev mode; preamble IGNORED
};
```

### 3.1 Field-by-field consumption rules

- **`thread_id`**: Stored in `localStorage` on every successful response. The agent may issue a fresh `thread_id` even when the request didn't carry one, or echo back a continuing one — the frontend does not branch on which. It always replaces the stored value.
- **`run_id`**: Displayed in the metadata-badges area (small, secondary). Used as a stable key for the assistant message in the React tree.
- **`response`**: Rendered as the assistant message body. May contain Markdown-ish prose (the agent's response synthesizer is plain prose today; see `004/contracts/api.md`). V1 renders as plain text — Markdown rendering is a polish task, not a contract.
- **`status`**: Drives the `ResponseStatus`-based branching in `data-model.md §1.3`. Any value not in the documented enum is a contract violation; the frontend logs to console, treats as `failed_safety`, and continues.
- **`route.complexity`** / **`route.selected_model`** / **`route.rationale`**: Each becomes a badge if present and non-null. `selected_model: null` hides the badge (controlled-failure case). `rationale` is **not** shown as a badge — it's reserved for a tooltip that V1 does not implement.
- **`sql`**: Populated → `SqlViewer` renders, collapsed by default. `null` → `SqlViewer` does not render.
- **`code`**: Always `null` for V1 (we send `debug: false`). Even if it weren't, FR-018 forbids displaying it. Defensive: if a future agent build sets this field unexpectedly, the frontend ignores it.
- **`chart_artifact`**: Object → render `<iframe src={normalize(url)} sandbox="allow-scripts">`. `null` → render the empty-state placeholder. The frontend treats `chart_artifact.type === "plotly_html"` as the only V1 type and renders unknown types as the empty placeholder rather than guessing.
- **`dataframe_preview`**: Array of zero-or-more row objects. Render the first 20 rows; ignore beyond. Empty array → render the "no data preview available" placeholder.
- **`row_count`**: V1 ignores this field. (When `dataframe_preview.length < row_count`, this is the agent telling us the preview was truncated — we could surface it, but it's not gated by FR.)
- **`carryover.turn_count`**: V1 may surface this in a small "(turn N)" annotation on the assistant message. Optional polish.
- **`carryover.preamble`**: NEVER displayed. It's the agent's internal multi-turn prompt augmentation, not user-facing copy.

### 3.2 UI branching by `status`

| `status` value | Source-of-truth section in `004/contracts/api.md` | Frontend branch |
|---------------|---|---|
| `succeeded` | §1, "200 OK (success path)" | Render assistant message; render chart; render SQL/preview/metadata as available. |
| `failed_unsupported` | §1, "200 OK (controlled-failure paths)" | Render assistant message; show "no chart available" placeholder. **No error banner.** |
| `failed_clarification_needed` | Same | Render assistant message (the agent is asking the user for clarification). No chart. |
| `failed_safety` | Same | Render assistant message. No chart. The agent's text already explains "couldn't safely answer." |
| `failed_validation` | Same | Render assistant message. No chart. Same as `failed_safety` semantically from the user's POV. |

---

## 4. `POST /query` — error responses

HTTP 4xx/5xx return the agent's standard error envelope (`004/contracts/api.md` "Error envelope"):

```json
{
  "error": {
    "code": "<short_machine_readable_code>",
    "message": "<human-readable>",
    "details": { ... }
  }
}
```

**Frontend behavior**:

- The frontend reads `error.code` only.
- Maps `error.code` through the dictionary in [`research.md` R4](../research.md) to a curated user-facing string, displayed in `ErrorBanner`.
- `error.message` is **logged to console** (`console.warn`) and **not shown to the user**. Reason: `error.message` may legitimately include backend internals (file paths, table names, error class names) that we don't want surfaced verbatim. The translation layer keeps copy in our control.
- `error.details` is **logged to console** at debug level and not shown.
- `404 thread_not_found` is a **special case**: silently clear `localStorage.currentThreadId`, drop `thread_id` from the in-flight request payload, and retry the request **once**. If the retry also fails, fall through to the normal error banner (with whatever code that retry returned).

---

## 5. `GET /artifacts/{artifact_id}`

The frontend never directly fetches this URL with `fetch()`. It is **only** assigned to `<iframe src>`. The browser issues the GET; the iframe receives `text/html`; Plotly inline JS runs inside the sandboxed iframe.

**Implications**:

- The frontend doesn't see HTTP status codes for the artifact load. If the iframe fails to load (404, 5xx, network error, content-type mismatch), the iframe paints a browser-default error page inside its frame. Spec edge case: "Chart artifact URL fails to load in the embedded frame: the frame area shows a fallback message; the rest of the response remains visible and usable." The fallback is browser-default; V1 does not custom-style it.
- The iframe `sandbox="allow-scripts"` (no `allow-same-origin`) means the iframe is in an opaque origin. It cannot read `document.cookie` of the parent, cannot reach into the parent DOM, cannot post-message back unless the parent listens (it doesn't). The agent's artifact contract states the HTML is self-contained Plotly inline-JS — no further isolation needed.

---

## 6. `GET /health`

**Optional in V1.** The brief recommends a status badge; the spec doesn't require it (no FR mandates a health check). If implemented, the frontend polls every 30s and shows a small green/red dot. If unimplemented, no UI element exists.

If implemented:

- 200 OK with `status: "ok"` → green dot.
- 503 with `status: "unavailable"` → red dot, hover tooltip showing which check failed (`duckdb`, `postgres`).
- Network/timeout → red dot, hover tooltip "Agent unreachable."

The frontend never branches submission behavior on health status — `/query` is the source of truth for what the agent can actually do.

---

## 7. Endpoints the frontend MUST NOT call in V1

- `GET /threads/{thread_id}` — the data exists, but using it pulls "restore visible chat after reload" into V1 scope. Deferred.
- `GET /runs/{run_id}` — same reason. Plus, the admin path (`?admin=true` + `X-Agent-Admin`) is explicitly forbidden by FR-018/FR-022.
- Any non-listed path — failing fast on a 404 or unknown route is fine.

---

## 8. Backwards-compat assumptions

The contract this document depends on is `004/contracts/api.md` as it stands at the start of the 008 work. Future agent changes that:

- Add new fields to the `/query` 200 response → frontend ignores them silently. Safe.
- Add new `status` values → frontend logs and falls back to `failed_safety` semantics. Safe-ish (the new status's failure copy from the agent's `response` field is still shown).
- Add new `error.code` values → frontend uses the unknown-code fallback message. Safe.
- Change `chart_artifact.type` from `"plotly_html"` to something else → frontend renders the empty placeholder rather than the iframe. Safe (no broken render).
- Remove fields the frontend currently reads (`thread_id`, `run_id`, `response`, `status`) → **breaking change** on the agent side. The frontend will throw at the type boundary and `ErrorBanner` will show "The agent returned an unexpected response."

These are the same backwards-compat properties the agent's contract claims for itself (`004/contracts/api.md §6`); we just record the frontend-side interpretation explicitly.
