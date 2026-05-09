import { useEffect, useRef } from "react";
import clsx from "clsx";
import type { ChatMessage } from "../api/types";

export type ChatPanelProps = {
  messages: ChatMessage[];
};

const WELCOME_COPY =
  "Ask a question about the Discogs catalog, or pick one of the suggested questions to start.";

export function ChatPanel({ messages }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-slate-500 px-6 text-center">
        {WELCOME_COPY}
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="flex flex-col gap-3 overflow-y-auto h-full px-2 py-2"
      data-testid="chat-scroll"
    >
      {messages.map((message) => (
        <div
          key={message.id}
          className={clsx(
            "max-w-[90%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap",
            message.role === "user"
              ? "self-end bg-slate-900 text-white"
              : "self-start bg-white text-slate-900 border border-slate-200",
          )}
          data-role={message.role}
        >
          {message.content}
        </div>
      ))}
    </div>
  );
}
