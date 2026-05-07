import { useState } from "react";
import { Send } from "lucide-react";

export type QueryInputProps = {
  disabled: boolean;
  value?: string;
  onChange?: (next: string) => void;
  onSubmit: (message: string) => void;
};

const MAX_LENGTH = 2000;

export function QueryInput({
  disabled,
  value,
  onChange,
  onSubmit,
}: QueryInputProps) {
  const [internal, setInternal] = useState("");
  const isControlled = value !== undefined;
  const text = isControlled ? (value ?? "") : internal;

  const setText = (next: string) => {
    if (isControlled) {
      onChange?.(next);
    } else {
      setInternal(next);
    }
  };

  const trimmed = text.trim();
  const tooLong = text.length > MAX_LENGTH;
  const canSubmit = !disabled && trimmed.length > 0 && !tooLong;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <form
      className="flex flex-col gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        handleSubmit();
      }}
    >
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          maxLength={MAX_LENGTH + 100}
          aria-label="Ask a question about the Discogs catalog"
          placeholder="Ask a question about the Discogs catalog…"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:bg-slate-100 disabled:text-slate-500"
        />
        <button
          type="submit"
          disabled={!canSubmit}
          className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-2 text-sm text-white hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-500"
        >
          <Send className="h-4 w-4" aria-hidden="true" />
          <span>Send</span>
        </button>
      </div>
      {tooLong && (
        <p className="text-xs text-red-700">
          Question is too long. Keep it under {MAX_LENGTH} characters.
        </p>
      )}
    </form>
  );
}
