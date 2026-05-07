// Curated demo questions, grouped by category.
// Per spec §22: each card has title, category badge, description, and two
// buttons "Use" (fills the input) and "Run" (submits immediately).

import { Pencil, Play } from "lucide-react";
import type { CuratedQuestion } from "../api/types";
import { curatedQuestions } from "../data/curatedQuestions";

export type SuggestedQuestionsProps = {
  onUse: (query: string) => void;
  onRun: (query: string) => void;
  disabled?: boolean;
  questions?: readonly CuratedQuestion[];
};

function groupByCategory(
  questions: readonly CuratedQuestion[],
): Array<[CuratedQuestion["category"], CuratedQuestion[]]> {
  const order: CuratedQuestion["category"][] = [];
  const buckets = new Map<CuratedQuestion["category"], CuratedQuestion[]>();
  for (const q of questions) {
    if (!buckets.has(q.category)) {
      buckets.set(q.category, []);
      order.push(q.category);
    }
    buckets.get(q.category)!.push(q);
  }
  return order.map((cat) => [cat, buckets.get(cat)!]);
}

export function SuggestedQuestions({
  onUse,
  onRun,
  disabled = false,
  questions = curatedQuestions,
}: SuggestedQuestionsProps) {
  const groups = groupByCategory(questions);

  return (
    <nav
      aria-label="Suggested questions"
      className="flex flex-col gap-4 p-3 overflow-y-auto h-full"
    >
      {groups.map(([category, items]) => (
        <section
          key={category}
          aria-label={category}
          data-category={category}
          className="flex flex-col gap-2"
        >
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {category}
          </h2>
          <ul className="flex flex-col gap-2">
            {items.map((q) => (
              <li
                key={q.title}
                className="rounded-md border border-slate-200 bg-white p-3 text-sm shadow-sm"
              >
                <div className="font-medium text-slate-900">{q.title}</div>
                {q.description && (
                  <p className="mt-1 text-xs text-slate-600">{q.description}</p>
                )}
                <div className="mt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onUse(q.query)}
                    disabled={disabled}
                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Pencil className="h-3 w-3" aria-hidden="true" />
                    <span>Use</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onRun(q.query)}
                    disabled={disabled}
                    className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-2 py-1 text-xs text-white hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-500 disabled:cursor-not-allowed"
                  >
                    <Play className="h-3 w-3" aria-hidden="true" />
                    <span>Run</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}
