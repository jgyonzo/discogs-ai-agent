import { Loader2 } from "lucide-react";

export function LoadingState() {
  return (
    <div
      className="flex items-center gap-2 text-sm text-slate-600 px-4 py-2"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      <span>Generating analysis...</span>
    </div>
  );
}
