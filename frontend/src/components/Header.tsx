import type { ReactNode } from "react";

export type HeaderProps = {
  children?: ReactNode;
};

export function Header({ children }: HeaderProps) {
  return (
    <header className="border-b border-slate-200 bg-white px-6 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">
            Discogs Analytics Agent
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Ask natural language questions about the Discogs releases dataset.
          </p>
        </div>
        {children && <div className="flex-shrink-0">{children}</div>}
      </div>
    </header>
  );
}
