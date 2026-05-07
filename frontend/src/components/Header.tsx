export function Header() {
  return (
    <header className="border-b border-slate-200 bg-white px-6 py-4">
      <h1 className="text-xl font-semibold text-slate-900">
        Discogs Analytics Agent
      </h1>
      <p className="text-sm text-slate-600 mt-1">
        Ask natural language questions about the Discogs releases dataset.
      </p>
    </header>
  );
}
