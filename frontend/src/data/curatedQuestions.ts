// V1 curated demo questions for one-click runs.
//
// Source of truth: specs/008-agent-frontend-v1/contracts/curated-questions.md.
// This file is normative — its contents must equal the contract at merge time.
// Drift is detected by frontend/tests/integration/curated-questions-spread.test.ts.

import type { CuratedQuestion } from "../api/types";

export const curatedQuestions: readonly CuratedQuestion[] = [
  {
    title: "Releases by decade",
    category: "Trends",
    query: "Show releases by decade as a bar chart",
    description: "Basic decade-grain trend using release_unique_view.",
    demonstrates: ["simple-aggregate", "time-series"],
  },
  {
    title: "Techno over time",
    category: "Styles",
    query: "Show the evolution of Techno releases over time",
    description:
      "Line chart using release_fact and COUNT(DISTINCT release_id) over a style filter.",
    demonstrates: ["time-series", "simple-aggregate"],
  },
  {
    title: "Vinyl vs CD",
    category: "Formats",
    query: "Compare Vinyl and CD releases by decade",
    description:
      "Format comparison over time — exercises the has_*_format flags on release_fact.",
    demonstrates: ["format-comparison", "time-series"],
  },
  {
    title: "Top countries",
    category: "Geography",
    query: "What are the top 15 countries by number of releases?",
    description: "Ranking of countries by release count.",
    demonstrates: ["geographic-ranking", "simple-aggregate"],
  },
  {
    title: "Label diversity",
    category: "Labels",
    query: "Which labels have the most stylistic diversity?",
    description:
      "Complex query joining labels, releases, and styles; uses release_label_bridge.",
    demonstrates: ["label-diversity", "simple-aggregate"],
  },
  {
    title: "House outliers",
    category: "Advanced",
    query: "Detect outlier years for House releases",
    description:
      "Outlier detection using z-scores or IQR over a style-filtered time series.",
    demonstrates: ["outlier-detection", "time-series"],
  },
  {
    title: "Works with most versions",
    category: "Masters",
    query: "Which works have the most versions?",
    description:
      "Uses master_fact (optional table) — exercises the master-grain join.",
    demonstrates: ["master-grain-join"],
  },
] as const;
