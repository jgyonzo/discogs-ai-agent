// "New conversation" control + a compact display of the current thread id.
// Per spec §21.2: clicking the button clears the visible chat, severs the
// active conversation identifier, and starts a fresh conversation on the
// next submission.

import { RotateCcw } from "lucide-react";

export type ThreadControlsProps = {
  threadId: string | null;
  onNewConversation: () => void;
};

const NO_THREAD_LABEL = "no active thread";

function truncate(id: string): string {
  if (id.length <= 8) return id;
  return `${id.slice(0, 4)}…${id.slice(-3)}`;
}

export function ThreadControls({
  threadId,
  onNewConversation,
}: ThreadControlsProps) {
  return (
    <div className="flex items-center gap-3 text-xs text-slate-600">
      <span data-testid="thread-id-display">
        thread:{" "}
        <span className="font-mono">
          {threadId ? truncate(threadId) : NO_THREAD_LABEL}
        </span>
      </span>
      <button
        type="button"
        onClick={onNewConversation}
        className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 hover:bg-slate-100"
      >
        <RotateCcw className="h-3 w-3" aria-hidden="true" />
        <span>New conversation</span>
      </button>
    </div>
  );
}
