// Curated-question contract verification.
//
// Source of truth: specs/008-agent-frontend-v1/contracts/curated-questions.md
// §5. This test is the regression guard for FR-005 ("at least 5 curated
// questions covering a meaningful spread") and §3 (per-entry constraints).

import { describe, expect, it } from "vitest";
import { curatedQuestions } from "../../src/data/curatedQuestions";
import type { CuratedQuestion } from "../../src/api/types";

const ALLOWED_CATEGORIES: ReadonlySet<CuratedQuestion["category"]> = new Set([
  "Trends",
  "Styles",
  "Formats",
  "Geography",
  "Labels",
  "Advanced",
  "Masters",
]);

describe("Curated questions — V1 contract", () => {
  it("ships at least 5 questions (FR-005 floor)", () => {
    expect(curatedQuestions.length).toBeGreaterThanOrEqual(5);
  });

  it("collectively covers at least 5 distinct AgentCapability values", () => {
    const capabilities = new Set<string>();
    for (const q of curatedQuestions) {
      for (const cap of q.demonstrates) capabilities.add(cap);
    }
    expect(capabilities.size).toBeGreaterThanOrEqual(5);
  });

  it("each entry has the required fields", () => {
    for (const q of curatedQuestions) {
      expect(q.title.length).toBeGreaterThan(0);
      expect(q.query.length).toBeGreaterThan(0);
      expect(q.demonstrates.length).toBeGreaterThan(0);
    }
  });

  it("title length ≤ 40 chars (per contract §3)", () => {
    for (const q of curatedQuestions) {
      expect(q.title.length).toBeLessThanOrEqual(40);
    }
  });

  it("description length ≤ 100 chars when present (per contract §3)", () => {
    for (const q of curatedQuestions) {
      if (q.description !== undefined) {
        expect(q.description.length).toBeLessThanOrEqual(100);
      }
    }
  });

  it("category is one of the allowed enum values", () => {
    for (const q of curatedQuestions) {
      expect(ALLOWED_CATEGORIES.has(q.category)).toBe(true);
    }
  });

  it("drop-one safety: removing any single question still covers ≥ 5 capabilities", () => {
    // Per contract §2: removing any single question from the set still
    // covers ≥ 5 distinct capabilities.
    for (let i = 0; i < curatedQuestions.length; i++) {
      const reduced = curatedQuestions.filter((_, idx) => idx !== i);
      const caps = new Set<string>();
      for (const q of reduced) for (const c of q.demonstrates) caps.add(c);
      expect(caps.size).toBeGreaterThanOrEqual(5);
    }
  });
});
