// localStorage wrapper for the active conversation identifier.
// Single key, plain string value (no JSON wrapping).
// All operations are exception-safe: private-mode browsers and quota errors
// degrade silently per data-model.md §3.

const KEY = "discogs.frontend.currentThreadId";

export function getCurrentThreadId(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setCurrentThreadId(id: string): void {
  try {
    window.localStorage.setItem(KEY, id);
  } catch {
    // no-op: private mode, quota exceeded, etc.
  }
}

export function clearCurrentThreadId(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // no-op
  }
}
