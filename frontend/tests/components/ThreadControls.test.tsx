import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ThreadControls } from "../../src/components/ThreadControls";

describe("ThreadControls", () => {
  it("renders 'no active thread' when threadId is null", () => {
    render(
      <ThreadControls threadId={null} onNewConversation={vi.fn()} />,
    );
    expect(screen.getByTestId("thread-id-display")).toHaveTextContent(
      /no active thread/i,
    );
  });

  it("renders a truncated thread id when set", () => {
    render(
      <ThreadControls
        threadId="abcd1234-ef56-7890-abcd-ef1234567890"
        onNewConversation={vi.fn()}
      />,
    );
    const display = screen.getByTestId("thread-id-display");
    // First 4 chars present.
    expect(display.textContent).toMatch(/abcd/);
    // Full id is NOT shown verbatim.
    expect(display.textContent).not.toContain(
      "abcd1234-ef56-7890-abcd-ef1234567890",
    );
  });

  it("renders the full id when it is already short (≤ 8 chars)", () => {
    render(<ThreadControls threadId="short" onNewConversation={vi.fn()} />);
    expect(screen.getByTestId("thread-id-display")).toHaveTextContent(/short/);
  });

  it("calls onNewConversation exactly once when the button is clicked", async () => {
    const user = userEvent.setup();
    const onNewConversation = vi.fn();
    render(
      <ThreadControls
        threadId="abc-123"
        onNewConversation={onNewConversation}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: /new conversation/i }),
    );
    expect(onNewConversation).toHaveBeenCalledTimes(1);
  });

  it("button stays clickable even when threadId is null (data-model §2.1: newConversation valid in any state)", async () => {
    const user = userEvent.setup();
    const onNewConversation = vi.fn();
    render(
      <ThreadControls threadId={null} onNewConversation={onNewConversation} />,
    );
    const button = screen.getByRole("button", { name: /new conversation/i });
    expect(button).not.toBeDisabled();
    await user.click(button);
    expect(onNewConversation).toHaveBeenCalledTimes(1);
  });
});
