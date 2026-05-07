// TypeScript domain types for the Discogs analytics frontend.
//
// Source of truth: specs/008-agent-frontend-v1/data-model.md.
// The agent-side response contract is documented in
// specs/004-agent-v1/contracts/api.md and consumed per
// specs/008-agent-frontend-v1/contracts/api-consumption.md.
//
// Drift between this file and data-model.md is a real bug — fix here, do not
// silence with type assertions.

// ─── Chart artifact ──────────────────────────────────────────────────────────

export type ChartArtifact = {
  artifact_id: string;
  url: string;
  type: "plotly_html";
};

// ─── Response status ────────────────────────────────────────────────────────

export type ResponseStatus =
  | "succeeded"
  | "failed_unsupported"
  | "failed_clarification_needed"
  | "failed_safety"
  | "failed_validation";

// ─── Run metadata (from agent's `route` plus flat fields) ───────────────────

export type RunMetadata = {
  run_id: string;
  thread_id: string;
  complexity?: string;
  selected_model?: string | null;
  rationale?: string | null;
  status: ResponseStatus;
  validation?: { valid: boolean; errors?: string[] };
};

// ─── Carryover (multi-turn) ─────────────────────────────────────────────────

export type Carryover = {
  turn_count: number;
  preamble: string | null;
};

// ─── Chat messages (frontend-built, not received raw from the agent) ────────

export type UserMessage = {
  id: string;
  role: "user";
  content: string;
  createdAt: string;
};

export type AssistantMessage = {
  id: string;
  role: "assistant";
  content: string;
  runId: string;
  artifact: ChartArtifact | null;
  sql: string | null;
  dataframePreview: Record<string, unknown>[];
  metadata: RunMetadata;
  createdAt: string;
};

export type ChatMessage = UserMessage | AssistantMessage;

// ─── Curated questions ──────────────────────────────────────────────────────

export type AgentCapability =
  | "simple-aggregate"
  | "time-series"
  | "format-comparison"
  | "geographic-ranking"
  | "label-diversity"
  | "outlier-detection"
  | "master-grain-join";

export type CuratedQuestion = {
  title: string;
  category:
    | "Trends"
    | "Styles"
    | "Formats"
    | "Geography"
    | "Labels"
    | "Advanced"
    | "Masters";
  query: string;
  description?: string;
  demonstrates: AgentCapability[];
};

// ─── User-facing errors (output of the translation pipeline) ────────────────

export type UserFacingErrorKind = "network" | "http" | "parse";

export type UserFacingError = {
  kind: UserFacingErrorKind;
  copy: string;
};

// ─── Wire types: agent /query request and response ──────────────────────────

export type QueryRequest = {
  thread_id?: string | null;
  message: string;
  debug?: false;
};

export type QueryResponse = {
  thread_id: string;
  run_id: string;
  response: string;
  status: ResponseStatus;
  route: {
    complexity?: string;
    selected_model?: string | null;
    rationale?: string | null;
  };
  sql: string | null;
  // see contracts/api-consumption.md §3.1 — frontend ignores `code` regardless.
  code: null;
  chart_artifact: ChartArtifact | null;
  dataframe_preview: Record<string, unknown>[];
  row_count: number;
  carryover: Carryover;
};

export type ApiErrorEnvelope = {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
};

// ─── Reducer state and actions ──────────────────────────────────────────────

export type AppState = {
  threadId: string | null;
  messages: ChatMessage[];
  current: {
    artifact: ChartArtifact | null;
    sql: string | null;
    dataframePreview: Record<string, unknown>[];
    metadata: RunMetadata | null;
  };
  pending: boolean;
  error: UserFacingError | null;
};

export type Action =
  | { type: "submit"; userMessage: UserMessage }
  | { type: "responseSucceeded"; assistant: AssistantMessage }
  | { type: "responseFailedControlled"; assistant: AssistantMessage }
  | { type: "responseError"; error: UserFacingError }
  | { type: "newConversation" };
