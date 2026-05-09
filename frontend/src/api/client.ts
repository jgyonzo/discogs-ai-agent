// HTTP client for the agent API.
//
// Boundaries:
// - VITE_API_BASE_URL is the only configuration source (Constitution VII.a).
// - The frontend never sends `debug: true` and never reads the `code` field.
// - 404 thread_not_found is silently retried once with no thread_id, per
//   contracts/api-consumption.md §4 special case.

import { clearCurrentThreadId } from "../utils/localStorage";
import {
  translateHttpError,
  translateNetworkError,
  translateParseError,
} from "../utils/errors";
import type {
  ApiErrorEnvelope,
  QueryRequest,
  QueryResponse,
} from "./types";

const FALLBACK_BASE_URL = "http://localhost:8000";

export function getApiBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL;
  if (typeof fromEnv === "string" && fromEnv.length > 0) return fromEnv;
  return FALLBACK_BASE_URL;
}

export function toAbsoluteArtifactUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (url.startsWith("/")) return `${getApiBaseUrl()}${url}`;
  // Defensive: agent might one day return a bare id; preserve it as-is.
  return url;
}

function buildRequestBody(req: QueryRequest): string {
  // Omit thread_id when it's null/undefined/empty per
  // contracts/api-consumption.md §2 (sending null is forbidden).
  const body: { thread_id?: string; message: string } = { message: req.message };
  if (typeof req.thread_id === "string" && req.thread_id.length > 0) {
    body.thread_id = req.thread_id;
  }
  return JSON.stringify(body);
}

async function postQuery(
  baseUrl: string,
  req: QueryRequest,
): Promise<Response> {
  return fetch(`${baseUrl}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: buildRequestBody(req),
  });
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch (err) {
    throw translateParseError(err);
  }
}

function isThreadNotFound(envelope: ApiErrorEnvelope | null): boolean {
  return envelope?.error?.code === "thread_not_found";
}

export async function sendQuery(req: QueryRequest): Promise<QueryResponse> {
  const baseUrl = getApiBaseUrl();

  let response: Response;
  try {
    response = await postQuery(baseUrl, req);
  } catch (err) {
    throw translateNetworkError(err);
  }

  if (response.ok) {
    return parseJsonOrThrow<QueryResponse>(response);
  }

  // Try to parse the error envelope, but don't blow up if the body isn't JSON.
  let envelope: ApiErrorEnvelope | null = null;
  try {
    envelope = (await response.json()) as ApiErrorEnvelope;
  } catch {
    envelope = null;
  }

  // Silent retry on stale thread_id.
  if (response.status === 404 && isThreadNotFound(envelope)) {
    clearCurrentThreadId();
    let retryResponse: Response;
    try {
      retryResponse = await postQuery(baseUrl, { message: req.message });
    } catch (err) {
      throw translateNetworkError(err);
    }
    if (retryResponse.ok) {
      return parseJsonOrThrow<QueryResponse>(retryResponse);
    }
    let retryEnvelope: ApiErrorEnvelope | null = null;
    try {
      retryEnvelope = (await retryResponse.json()) as ApiErrorEnvelope;
    } catch {
      retryEnvelope = null;
    }
    if (retryEnvelope) throw translateHttpError(retryEnvelope);
    throw translateHttpError({
      error: { code: "internal_error", message: "Unparseable error response" },
    });
  }

  if (envelope) throw translateHttpError(envelope);
  throw translateHttpError({
    error: { code: "internal_error", message: "Unparseable error response" },
  });
}

// Optional in V1 — not yet wired into the UI.
export type HealthResponse = {
  status: "ok" | "unavailable";
  checks?: Record<string, { ok: boolean; error?: string | null }>;
};

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${getApiBaseUrl()}/health`);
  return parseJsonOrThrow<HealthResponse>(response);
}
