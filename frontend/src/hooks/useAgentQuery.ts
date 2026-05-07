// Agent-query reducer + submit thunk.
//
// Source of truth for state shape and transitions: data-model.md §2.
// The submit thunk's branching by response.status is described in
// contracts/api-consumption.md §3.2.

import { useCallback, useReducer } from "react";
import { sendQuery } from "../api/client";
import {
  clearCurrentThreadId,
  getCurrentThreadId,
  setCurrentThreadId,
} from "../utils/localStorage";
import type {
  Action,
  AppState,
  AssistantMessage,
  QueryResponse,
  UserFacingError,
  UserMessage,
} from "../api/types";

// Built lazily inside the hook (via useReducer's third argument) so that
// localStorage is read at component-mount time, not at module-load time.
// This preserves the US3.3 acceptance scenario: a browser refresh mid-
// conversation must leave the active thread_id discoverable.
export function buildInitialState(): AppState {
  return {
    threadId: getCurrentThreadId(),
    messages: [],
    current: {
      artifact: null,
      sql: null,
      dataframePreview: [],
      metadata: null,
    },
    pending: false,
    error: null,
  };
}

// Kept for backwards compatibility / type ergonomics in tests that just
// want a representative AppState. Always reflects an empty localStorage —
// the runtime hook calls `buildInitialState()` lazily instead.
export const initialState: AppState = {
  threadId: null,
  messages: [],
  current: {
    artifact: null,
    sql: null,
    dataframePreview: [],
    metadata: null,
  },
  pending: false,
  error: null,
};

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "submit": {
      // Forbidden transition: submit while already pending → no-op.
      if (state.pending) return state;
      return {
        ...state,
        messages: [...state.messages, action.userMessage],
        pending: true,
        error: null,
      };
    }
    case "responseSucceeded": {
      // Forbidden transition: response while not pending → no-op.
      if (!state.pending) return state;
      const { assistant } = action;
      return {
        ...state,
        threadId: assistant.metadata.thread_id,
        messages: [...state.messages, assistant],
        current: {
          artifact: assistant.artifact,
          sql: assistant.sql,
          dataframePreview: assistant.dataframePreview,
          metadata: assistant.metadata,
        },
        pending: false,
        error: null,
      };
    }
    case "responseFailedControlled": {
      if (!state.pending) return state;
      const { assistant } = action;
      return {
        ...state,
        threadId: assistant.metadata.thread_id,
        messages: [...state.messages, assistant],
        current: {
          // Controlled failure may include a chart (rare) but typically null.
          artifact: assistant.artifact,
          sql: assistant.sql,
          dataframePreview: assistant.dataframePreview,
          metadata: assistant.metadata,
        },
        pending: false,
        error: null,
      };
    }
    case "responseError": {
      if (!state.pending) return state;
      // Preserve `current` (last successful result stays visible) per
      // data-model.md §2.1 IDLE_WITH_ERROR rule.
      return {
        ...state,
        pending: false,
        error: action.error,
      };
    }
    case "newConversation": {
      return {
        threadId: null,
        messages: [],
        current: {
          artifact: null,
          sql: null,
          dataframePreview: [],
          metadata: null,
        },
        pending: false,
        error: null,
      };
    }
    default: {
      const exhaustive: never = action;
      return exhaustive;
    }
  }
}

function nextId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

function buildAssistantMessage(response: QueryResponse): AssistantMessage {
  return {
    id: nextId(),
    role: "assistant",
    content: response.response,
    runId: response.run_id,
    artifact: response.chart_artifact,
    sql: response.sql,
    dataframePreview: response.dataframe_preview,
    metadata: {
      run_id: response.run_id,
      thread_id: response.thread_id,
      complexity: response.route.complexity,
      selected_model: response.route.selected_model,
      rationale: response.route.rationale,
      status: response.status,
    },
    createdAt: new Date().toISOString(),
  };
}

export type UseAgentQueryResult = {
  state: AppState;
  submit: (message: string) => Promise<void>;
  newConversation: () => void;
};

export function useAgentQuery(): UseAgentQueryResult {
  const [state, dispatch] = useReducer(reducer, undefined, buildInitialState);

  const submit = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (trimmed.length === 0) return;

      const userMessage: UserMessage = {
        id: nextId(),
        role: "user",
        content: trimmed,
        createdAt: new Date().toISOString(),
      };
      dispatch({ type: "submit", userMessage });

      // Read threadId fresh from state at the moment of submit. The reducer
      // dispatch above hasn't updated `state` yet (same closure), so we
      // read from the same `state` object — safe because submit-while-pending
      // is a no-op in the reducer.
      try {
        const response = await sendQuery({
          thread_id: state.threadId,
          message: trimmed,
        });
        setCurrentThreadId(response.thread_id);
        const assistant = buildAssistantMessage(response);
        if (response.status === "succeeded") {
          dispatch({ type: "responseSucceeded", assistant });
        } else {
          dispatch({ type: "responseFailedControlled", assistant });
        }
      } catch (err) {
        // sendQuery only throws UserFacingError via the translation layer.
        const error = err as UserFacingError;
        dispatch({ type: "responseError", error });
      }
    },
    [state.threadId],
  );

  const newConversation = useCallback(() => {
    clearCurrentThreadId();
    dispatch({ type: "newConversation" });
  }, []);

  return { state, submit, newConversation };
}
