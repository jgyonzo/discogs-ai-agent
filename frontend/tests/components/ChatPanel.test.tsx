import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatPanel } from "../../src/components/ChatPanel";
import { makeAssistantMessage } from "../mocks/factories";
import type { ChatMessage } from "../../src/api/types";

describe("ChatPanel", () => {
  it("renders the welcome state when messages is empty", () => {
    render(<ChatPanel messages={[]} />);
    expect(
      screen.getByText(
        /Ask a question about the Discogs catalog, or pick one of the suggested questions to start\./i,
      ),
    ).toBeInTheDocument();
  });

  it("renders user and assistant messages in DOM order", () => {
    const messages: ChatMessage[] = [
      {
        id: "u1",
        role: "user",
        content: "Show releases by decade",
        createdAt: new Date().toISOString(),
      },
      makeAssistantMessage({
        id: "a1",
        content: "Generated a chart of releases by decade.",
      }),
    ];
    render(<ChatPanel messages={messages} />);
    const userBubble = screen.getByText("Show releases by decade");
    const assistantBubble = screen.getByText(
      "Generated a chart of releases by decade.",
    );
    expect(userBubble).toHaveAttribute("data-role", "user");
    expect(assistantBubble).toHaveAttribute("data-role", "assistant");
    expect(
      userBubble.compareDocumentPosition(assistantBubble) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("scrolls the container to the bottom when messages grows", () => {
    const m1 = makeAssistantMessage({ id: "a1", content: "first" });
    const { rerender } = render(<ChatPanel messages={[m1]} />);
    const container = screen.getByTestId("chat-scroll");
    // Force a scrollHeight to assert against. jsdom defaults to 0, so we
    // overwrite it.
    Object.defineProperty(container, "scrollHeight", {
      configurable: true,
      value: 1000,
    });
    const m2 = makeAssistantMessage({ id: "a2", content: "second" });
    rerender(<ChatPanel messages={[m1, m2]} />);
    // The effect has run with the new messages.length; scrollTop should be set.
    expect(container.scrollTop).toBe(1000);
  });
});
