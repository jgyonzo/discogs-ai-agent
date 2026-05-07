// Test data factories. Centralizing here so individual tests don't have to
// re-list every required field of QueryResponse.

import type {
  AssistantMessage,
  ChartArtifact,
  QueryResponse,
  ResponseStatus,
  RunMetadata,
} from "../../src/api/types";

let runIdCounter = 0;
function nextRunId(): string {
  return `run-${(++runIdCounter).toString().padStart(8, "0")}`;
}

let threadIdCounter = 0;
function nextThreadId(): string {
  return `thread-${(++threadIdCounter).toString().padStart(8, "0")}`;
}

let artifactIdCounter = 0;
function nextArtifactId(): string {
  return `artifact-${(++artifactIdCounter).toString().padStart(8, "0")}`;
}

export function makeChartArtifact(
  overrides: Partial<ChartArtifact> = {},
): ChartArtifact {
  const artifact_id = overrides.artifact_id ?? nextArtifactId();
  return {
    artifact_id,
    url: overrides.url ?? `/artifacts/${artifact_id}`,
    type: overrides.type ?? "plotly_html",
  };
}

export function makeQueryResponse(
  overrides: Partial<QueryResponse> = {},
): QueryResponse {
  const status: ResponseStatus = overrides.status ?? "succeeded";
  const isControlledFailure = status !== "succeeded";
  const thread_id = overrides.thread_id ?? nextThreadId();
  const run_id = overrides.run_id ?? nextRunId();

  return {
    thread_id,
    run_id,
    response:
      overrides.response ??
      (isControlledFailure
        ? "I couldn't answer that with the available data."
        : "Generated a chart of releases by decade."),
    status,
    route: overrides.route ?? {
      complexity: isControlledFailure ? "unsupported" : "simple",
      selected_model: isControlledFailure ? null : "gpt-4o-mini",
      rationale: isControlledFailure
        ? "Not in scope of the published catalog."
        : "Single-table aggregation by decade.",
    },
    sql:
      overrides.sql !== undefined
        ? overrides.sql
        : isControlledFailure
          ? null
          : "SELECT decade, COUNT(*) AS releases FROM release_unique_view GROUP BY decade ORDER BY decade",
    code: null,
    chart_artifact:
      overrides.chart_artifact !== undefined
        ? overrides.chart_artifact
        : isControlledFailure
          ? null
          : makeChartArtifact(),
    dataframe_preview:
      overrides.dataframe_preview ??
      (isControlledFailure
        ? []
        : [
            { decade: 1980, releases: 120 },
            { decade: 1990, releases: 450 },
          ]),
    row_count: overrides.row_count ?? (isControlledFailure ? 0 : 2),
    carryover: overrides.carryover ?? { turn_count: 0, preamble: null },
  };
}

export function makeRunMetadata(
  overrides: Partial<RunMetadata> = {},
): RunMetadata {
  return {
    run_id: overrides.run_id ?? nextRunId(),
    thread_id: overrides.thread_id ?? nextThreadId(),
    complexity: overrides.complexity ?? "simple",
    selected_model:
      overrides.selected_model !== undefined
        ? overrides.selected_model
        : "gpt-4o-mini",
    rationale: overrides.rationale ?? "Single-table aggregation by decade.",
    status: overrides.status ?? "succeeded",
    validation: overrides.validation,
  };
}

export function makeAssistantMessage(
  overrides: Partial<AssistantMessage> = {},
): AssistantMessage {
  return {
    id: overrides.id ?? `msg-${Math.random().toString(36).slice(2, 10)}`,
    role: "assistant",
    content: overrides.content ?? "Generated a chart.",
    runId: overrides.runId ?? nextRunId(),
    artifact: overrides.artifact !== undefined ? overrides.artifact : makeChartArtifact(),
    sql:
      overrides.sql !== undefined
        ? overrides.sql
        : "SELECT decade, COUNT(*) FROM release_unique_view GROUP BY decade",
    dataframePreview: overrides.dataframePreview ?? [],
    metadata: overrides.metadata ?? makeRunMetadata(),
    createdAt: overrides.createdAt ?? new Date().toISOString(),
  };
}
