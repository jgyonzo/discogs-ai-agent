import { AlertCircle, X } from "lucide-react";
import type { UserFacingError } from "../api/types";

export type ErrorBannerProps = {
  error: UserFacingError;
  onDismiss?: () => void;
};

export function ErrorBanner({ error, onDismiss }: ErrorBannerProps) {
  return (
    <div
      className="flex items-start gap-2 border border-red-200 bg-red-50 text-red-900 px-4 py-3 rounded-md"
      role="alert"
    >
      <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" aria-hidden="true" />
      <p className="flex-1 text-sm">{error.copy}</p>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-red-900 hover:text-red-700"
          aria-label="Dismiss error"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
