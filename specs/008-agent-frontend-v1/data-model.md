# Data Model: Agent Frontend V1

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

The frontend has **no database**. It persists nothing across sessions except a single string. This document captures the in-memory domain types and the localStorage shape — together they are the entire "data model" of the frontend.

All TypeScript types below are normative: `frontend/src/api/types.ts` and the file that owns the reducer state must match. Drift is detectable at compile time.

---

## 1. Domain types

### 1.1 `ChartArtifact`

Mirrors the agent's `chart_artifact` field (`004/contracts/api.md §1`). Opaque to the frontend — never inspected, only rendered.

```ts
export type ChartArtifact = {
  artifact_id: string;       // UUID; pass-through, used as React key
  url: string;               // Agent-supplied relative URL ("/artifacts/<uuid>"); normalized to absolute by api/client.ts
  type: "plotly_html";       // V1 always; widening to a union when CSV/json artifacts arrive in V1.1
};
```

**Invariants**:
- `url` is always present (the agent never returns a `chart_artifact` object without one).
- `url` is **not** trusted by the frontend for display logic — it's only assigned to `<iframe src>`. We never parse it, log it, or branch on it.

### 1.2 `RunMetadata`

Mirrors the agent's `route` block plus a few flat fields. All optional, all display-only.

```ts
export type RunMetadata = {
  run_id: string;                  // Always present
  thread_id: string;               // Always present
  complexity?: string;             // e.g., "simple", "complex", "unsupported", "clarification_needed"
  selected_model?: string | null;  // e.g., "gpt-4o-mini", "gpt-4o"; null on controlled failures
  rationale?: string | null;       // Free-form text; shown only in a tooltip (out-of-scope for V1)
  status: ResponseStatus;          // See §1.3
  validation?: { valid: boolean; errors?: string[] };  // Future-proofing; agent's V1 doesn't currently emit this
};
```

**Display rule** (US4 acceptance scenario 3): badges show only fields that are present *and* non-null. `selected_model: null` (controlled failure) hides the model badge instead of rendering "null."

### 1.3 `ResponseStatus`

The agent's `status` field. Mirrored verbatim from `004/contracts/api.md §1`.

```ts
export type ResponseStatus =
  | "succeeded"
  | "failed_unsupported"
  | "failed_clarification_needed"
  | "failed_safety"
  | "failed_validation";
```

**Frontend behavior by status**:

| `status` | Chart artifact | Error banner | Assistant text |
|---------|---------------|--------------|----------------|
| `succeeded` | rendered if present | none | shown |
| `failed_unsupported` | "no chart available" placeholder | none (controlled failure) | shown |
| `failed_clarification_needed` | "no chart available" placeholder | none | shown (the agent's question to the user) |
| `failed_safety` | "no chart available" placeholder | none | shown ("agent couldn't safely answer") |
| `failed_validation` | "no chart available" placeholder | none | shown ("agent couldn't correctly answer") |

HTTP 4xx/5xx errors take a separate path (see `R4` in `research.md` and `utils/errors.ts`); they are not values of `ResponseStatus`.

### 1.4 `Carryover`

Mirrors the agent's `carryover` field. Frontend stores it but never displays `preamble` directly.

```ts
export type Carryover = {
  turn_count: number;
  preamble: string | null;
};
```

The `turn_count` may be surfaced in dev mode as a small "(turn N)" annotation on the assistant message; the `preamble` is never shown. (Reason: it's the agent's internal multi-turn prompt-augmentation prose, not user-facing copy.)

### 1.5 `ChatMessage`

The frontend's per-turn record in the timeline. Constructed by the reducer; never received from the agent in this exact shape.

```ts
export type ChatMessage =
  | UserMessage
  | AssistantMessage;

export type UserMessage = {
  id: string;                      // Client-generated UUID
  role: "user";
  content: string;
  createdAt: string;               // Client-side ISO 8601 UTC
};

export type AssistantMessage = {
  id: string;                      // Client-generated UUID
  role: "assistant";
  content: string;                 // The agent's `response` field
  runId: string;                   // From the agent
  artifact: ChartArtifact | null;
  sql: string | null;
  dataframePreview: Record<string, unknown>[];
  metadata: RunMetadata;
  createdAt: string;               // Client-side ISO 8601 UTC; not the agent's `finished_at`
};
```

**Invariants**:
- A `UserMessage` is appended *before* the network call, so the timeline reflects the user's submission immediately (Spec FR-002 + FR-015).
- An `AssistantMessage` is appended *only after* a 200 OK response from the agent. Network/HTTP errors don't append an assistant message — they set `state.error` instead.
- `messages` is ordered by `createdAt` ascending. Append-only within a conversation. Cleared by `newConversation` action.

### 1.6 `CuratedQuestion`

Static content shipped in `frontend/src/data/curatedQuestions.ts`. The contract for V1's set is in [`contracts/curated-questions.md`](./contracts/curated-questions.md).

```ts
export type CuratedQuestion = {
  title: string;                   // ≤ 40 chars; appears as the card heading
  category: string;                // One of: "Trends" | "Styles" | "Formats" | "Geography" | "Labels" | "Advanced" | "Masters"
  query: string;                   // The actual user-facing prompt to send to the agent
  description?: string;            // Sub-line under the title; explains what the question demonstrates
  demonstrates: AgentCapability[]; // Internal tag; used by tests to verify spread coverage
};

export type AgentCapability =
  | "simple-aggregate"
  | "time-series"
  | "format-comparison"
  | "geographic-ranking"
  | "label-diversity"
  | "outlier-detection"
  | "master-grain-join";
```

**Invariants**:
- The set has **at least 5** entries (Spec FR-005).
- The set's `demonstrates` tags collectively cover at least 5 distinct `AgentCapability` values (this is the "meaningful spread" check, verified by `tests/integration/curated-questions-spread.test.ts`).
- `category` is informational; it does **not** drive any frontend logic beyond visual grouping.

### 1.7 `UserFacingError`

The output of the error-translation pipeline (`utils/errors.ts`). What `ErrorBanner` consumes.

```ts
export type UserFacingError = {
  kind: "network" | "http" | "parse";
  copy: string;                    // The user-facing message; one of the curated strings from research.md R4
  // No `details`, no `traceback`, no `originalError`. The translation layer drops everything privileged.
};
```

**Invariant**: `UserFacingError` instances **must not** carry references to the underlying error object. The translation layer is a one-way reduction; the original error is logged to `console.error` (developer-facing) but does not propagate into the React tree.

---

## 2. Reducer state shape

The single source of truth for what's on screen.

```ts
export type AppState = {
  threadId: string | null;         // Mirrors localStorage; null until first response
  messages: ChatMessage[];
  current: {
    artifact: ChartArtifact | null;
    sql: string | null;
    dataframePreview: Record<string, unknown>[];
    metadata: RunMetadata | null;
  };
  pending: boolean;                // True while a /query is in flight
  error: UserFacingError | null;   // Cleared on the next submit
};

export type Action =
  | { type: "submit"; userMessage: UserMessage }
  | { type: "responseSucceeded"; assistant: AssistantMessage }
  | { type: "responseFailedControlled"; assistant: AssistantMessage }
  | { type: "responseError"; error: UserFacingError }
  | { type: "newConversation" };
```

### 2.1 State transitions

```text
INITIAL
  threadId: null, messages: [], current: empty, pending: false, error: null

submit(userMsg) → APPENDED
  messages.append(userMsg), pending: true, error: null

responseSucceeded(assistant) → IDLE_WITH_RESULT
  messages.append(assistant), threadId: assistant.metadata.thread_id,
  current = { artifact, sql, dataframePreview, metadata } from assistant,
  pending: false

responseFailedControlled(assistant) → IDLE_WITH_PARTIAL_RESULT
  Same as responseSucceeded, but `current.artifact` may be null (controlled failure).
  Still appends an AssistantMessage; no error banner.

responseError(error) → IDLE_WITH_ERROR
  pending: false, error = error
  No new message appended (the user's message is already in the timeline from `submit`).

newConversation → INITIAL (preserves nothing)
  threadId: null (also: localStorage cleared by side effect),
  messages: [], current: empty, pending: false, error: null
```

### 2.2 Forbidden transitions

- `submit` while `pending: true` is a no-op (Spec FR-015 — input is disabled while a query is in flight, but the reducer is the second line of defense in case a UI bug ever queues two).
- `responseSucceeded` / `responseFailedControlled` / `responseError` while `pending: false` is a no-op (response races).
- `current` is **never** populated in `INITIAL` or `IDLE_WITH_ERROR` states. The error path leaves `current` carrying the *previous* successful response — preserving what the user was last looking at.

---

## 3. Persistence (localStorage)

Single key. Single value.

```ts
const KEY = "discogs.frontend.currentThreadId";

// Read on mount
const stored = localStorage.getItem(KEY);  // string | null

// Write on responseSucceeded / responseFailedControlled
localStorage.setItem(KEY, threadId);

// Clear on newConversation, on thread_not_found, and on storage failure
localStorage.removeItem(KEY);
```

**Invariants**:
- The key is the *only* thing the frontend writes to `localStorage`. No conversation history. No suggested-question recency cache. No user preferences.
- `localStorage` failures (`QuotaExceededError`, browser-private-mode disabling storage) are caught at the boundary and treated as "no stored thread" — the app continues to work, just without conversation continuity across reloads.
- The key is **not** namespaced per-user (V1 has no users) but is namespaced per-app (`discogs.frontend.*`) so coexistence with future siblings is straightforward.

---

## 4. The agent response contract (consumed shape)

This is the load-bearing contract for "the frontend reads the agent's responses correctly." The full shape is documented at [`contracts/api-consumption.md`](./contracts/api-consumption.md); the type below is the consumed projection.

```ts
export type QueryResponse = {
  thread_id: string;
  run_id: string;
  response: string;                // Always present
  status: ResponseStatus;
  route: {
    complexity?: string;
    selected_model?: string | null;
    rationale?: string | null;
  };
  sql: string | null;
  code: null;                      // We send debug: false, so this is always null
  chart_artifact: ChartArtifact | null;
  dataframe_preview: Record<string, unknown>[];
  row_count: number;
  carryover: Carryover;
};

export type QueryRequest = {
  thread_id?: string | null;
  message: string;
  debug?: false;                   // V1 always omits or sets false
};

export type ApiErrorEnvelope = {
  error: {
    code: string;                  // See research.md R4 for the V1 code dictionary
    message: string;
    details?: Record<string, unknown>;
  };
};
```

**Frontend doesn't read** (intentional; documented so it doesn't accidentally start):
- `code` — generated Python; FR-018.
- `errors[].traceback` — only present in admin mode; FR-016.
- The full `tool_calls` and `model_usage` arrays from `GET /runs/{id}` (V1 doesn't fetch from `/runs/{id}` — that's a future feature for the demo gallery / inspector view).

---

## 5. Volatile vs. durable

| Item | Lifetime | Where |
|------|----------|-------|
| `threadId` | Across page reloads, until "New conversation" or `thread_not_found` | `localStorage` |
| `messages` | Until "New conversation" or page reload | React reducer |
| `current.*` | Until next response or "New conversation" | React reducer |
| `pending` | Per request (typically 5-15s) | React reducer |
| `error` | Until next submit clears it | React reducer |
| Curated question set | Build-time constant | `frontend/src/data/curatedQuestions.ts` |
| API base URL | Build-time / runtime via Vite env injection | `import.meta.env.VITE_API_BASE_URL` |

V1 deliberately does not persist `messages`. Restoring the on-screen chat after a reload would require either (a) shipping per-message persistence the spec calls out as future work (FR-010 forbids it) or (b) reading `GET /threads/{id}` and reconstituting from runs — possible but not enough information per run to fully re-render (the agent's contract returns `user_query` per run, not the assistant's text reply, until you fetch each `/runs/{id}`). Either path is an enhancement, not V1.
