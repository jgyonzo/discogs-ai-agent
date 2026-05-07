// User-facing error translation.
// Source of truth: specs/008-agent-frontend-v1/research.md §R4.
//
// Invariant (data-model.md §1.7): the returned UserFacingError carries only
// `kind` and `copy`. Original payloads (HTTP envelope, network exception,
// parse error) are logged to console for developer visibility but never
// propagated into the React tree.

import type { ApiErrorEnvelope, UserFacingError } from "../api/types";

const HTTP_COPY: Record<string, string> = {
  invalid_request: "The question couldn't be parsed. Try rephrasing it.",
  duckdb_unavailable:
    "The catalog isn't available right now. Check that the agent's database is mounted.",
  database_unavailable: "The agent's session store isn't available right now.",
  internal_error:
    "Something went wrong on the agent side. Try again or rephrase.",
};

const FALLBACK_HTTP_COPY = HTTP_COPY.internal_error;
const NETWORK_COPY =
  "The agent is not reachable. Check that the local stack is running.";
const PARSE_COPY = "The agent returned an unexpected response.";

export function translateHttpError(
  envelope: ApiErrorEnvelope,
): UserFacingError {
  console.warn("[agent] HTTP error envelope:", envelope.error);
  const copy = HTTP_COPY[envelope.error.code] ?? FALLBACK_HTTP_COPY;
  return { kind: "http", copy };
}

export function translateNetworkError(err: unknown): UserFacingError {
  console.error("[agent] network error:", err);
  return { kind: "network", copy: NETWORK_COPY };
}

export function translateParseError(err: unknown): UserFacingError {
  console.error("[agent] parse error:", err);
  return { kind: "parse", copy: PARSE_COPY };
}
