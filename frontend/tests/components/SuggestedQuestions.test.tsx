import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SuggestedQuestions } from "../../src/components/SuggestedQuestions";
import { curatedQuestions } from "../../src/data/curatedQuestions";
import type { CuratedQuestion } from "../../src/api/types";

describe("SuggestedQuestions", () => {
  it("renders all curated questions with their titles visible", () => {
    render(<SuggestedQuestions onUse={vi.fn()} onRun={vi.fn()} />);
    for (const q of curatedQuestions) {
      expect(screen.getByText(q.title)).toBeInTheDocument();
    }
  });

  it("groups questions by category", () => {
    render(<SuggestedQuestions onUse={vi.fn()} onRun={vi.fn()} />);
    const distinctCategories = new Set(curatedQuestions.map((q) => q.category));
    for (const category of distinctCategories) {
      // Each category becomes a <section data-category="..."> heading.
      expect(
        screen.getByRole("region", { name: category }),
      ).toBeInTheDocument();
    }
  });

  it("calls onUse with the exact query text when Use is clicked", async () => {
    const user = userEvent.setup();
    const onUse = vi.fn();
    render(<SuggestedQuestions onUse={onUse} onRun={vi.fn()} />);
    const buttons = screen.getAllByRole("button", { name: /use/i });
    await user.click(buttons[0]);
    expect(onUse).toHaveBeenCalledTimes(1);
    expect(onUse).toHaveBeenCalledWith(curatedQuestions[0]!.query);
  });

  it("calls onRun with the exact query text when Run is clicked", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    render(<SuggestedQuestions onUse={vi.fn()} onRun={onRun} />);
    const buttons = screen.getAllByRole("button", { name: /run/i });
    await user.click(buttons[0]);
    expect(onRun).toHaveBeenCalledTimes(1);
    expect(onRun).toHaveBeenCalledWith(curatedQuestions[0]!.query);
  });

  it("disables both buttons when disabled=true", () => {
    render(
      <SuggestedQuestions onUse={vi.fn()} onRun={vi.fn()} disabled />,
    );
    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled();
    }
  });

  it("renders nothing visible when given an empty array", () => {
    const { container } = render(
      <SuggestedQuestions onUse={vi.fn()} onRun={vi.fn()} questions={[]} />,
    );
    // The nav element exists but has no question cards.
    expect(container.querySelectorAll("li")).toHaveLength(0);
  });

  it("preserves a custom question set passed via props", () => {
    const custom: CuratedQuestion[] = [
      {
        title: "Solo question",
        category: "Trends",
        query: "test query",
        demonstrates: ["simple-aggregate"],
      },
    ];
    render(
      <SuggestedQuestions onUse={vi.fn()} onRun={vi.fn()} questions={custom} />,
    );
    expect(screen.getByText("Solo question")).toBeInTheDocument();
    // Default curated set should NOT appear.
    expect(screen.queryByText("Releases by decade")).not.toBeInTheDocument();
  });
});
