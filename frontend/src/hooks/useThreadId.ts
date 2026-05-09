// Read-mostly mirror of the active conversation identifier.
//
// The reducer in useAgentQuery.ts is the source of truth for the live
// threadId. This hook exists for components that want the *initial*
// stored thread id without participating in the reducer (e.g. a small
// status badge that displays the truncated id near the header).

import { useCallback, useState } from "react";
import {
  clearCurrentThreadId,
  getCurrentThreadId,
  setCurrentThreadId,
} from "../utils/localStorage";

export type UseThreadIdResult = {
  threadId: string | null;
  setThreadId: (id: string) => void;
  clearThreadId: () => void;
};

export function useThreadId(): UseThreadIdResult {
  // Read-on-mount via lazy initialization. Captures whatever localStorage
  // held when the component first mounts; updates flow through the
  // returned setters.
  const [threadId, setThreadIdState] = useState<string | null>(() =>
    getCurrentThreadId(),
  );

  const setThreadId = useCallback((id: string) => {
    setCurrentThreadId(id);
    setThreadIdState(id);
  }, []);

  const clearThreadId = useCallback(() => {
    clearCurrentThreadId();
    setThreadIdState(null);
  }, []);

  return { threadId, setThreadId, clearThreadId };
}
