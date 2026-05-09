// MSW-backed end-to-end tests for US3:
// - multi-turn conversation reuses the thread_id;
// - "New conversation" clears state and starts fresh;
// - thread_not_found returns trigger a silent retry with no banner;
// - localStorage thread persists across mounts (US3.3).

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "../../src/App";
import { server } from "../setup";
import { makeQueryResponse } from "../mocks/factories";
import {
  clearCurrentThreadId,
  getCurrentThreadId,
  setCurrentThreadId,
} from "../../src/utils/localStorage";

const BASE_URL = "http://localhost:8000";

type Captured = { thread_id?: string; message: string };

function setupCapturingHandler(
  responseFor: (req: Captured) => Response,
): { captured: Captured[] } {
  const captured: Captured[] = [];
  server.use(
    http.post(`${BASE_URL}/query`, async ({ request }) => {
      const body = (await request.json()) as Captured;
      captured.push(body);
      return responseFor(body) as unknown as Response;
    }),
  );
  return { captured };
}

describe("US3 — multi-turn + reset", () => {
  beforeEach(() => {
    clearCurrentThreadId();
  });

  afterEach(() => {
    clearCurrentThreadId();
  });

  it("reuses the same thread_id across turns within one conversation", async () => {
    const FIXED_THREAD = "thread-multi-turn-001";
    const { captured } = setupCapturingHandler((req) =>
      HttpResponse.json(
        makeQueryResponse({
          thread_id: req.thread_id ?? FIXED_THREAD,
        }),
      ),
    );

    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });

    // Turn 1 — no thread_id sent; backend assigns one.
    await user.type(input, "Show releases by decade");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await screen.findByText("Show releases by decade");
    await waitFor(() =>
      expect(getCurrentThreadId()).toBe(FIXED_THREAD),
    );

    // Turn 2 — prior thread_id should be carried.
    await user.type(input, "Now only for UK");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await screen.findByText("Now only for UK");
    await waitFor(() => expect(captured.length).toBe(2));

    expect(captured[0]).not.toHaveProperty("thread_id");
    expect(captured[1]?.thread_id).toBe(FIXED_THREAD);
  });

  it("New conversation clears the chat, the localStorage key, and the next request omits thread_id", async () => {
    const { captured } = setupCapturingHandler((req) =>
      HttpResponse.json(
        makeQueryResponse({
          thread_id: req.thread_id ?? "thread-A",
          response: req.thread_id ? "follow-up reply" : "first reply",
        }),
      ),
    );

    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });

    // Turn 1.
    await user.type(input, "first question");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await screen.findByText("first question");
    await screen.findByText("first reply");
    await waitFor(() => expect(getCurrentThreadId()).toBe("thread-A"));

    // Click "New conversation".
    await user.click(
      screen.getByRole("button", { name: /new conversation/i }),
    );

    // Visible chat cleared.
    expect(screen.queryByText("first question")).not.toBeInTheDocument();
    expect(screen.queryByText("first reply")).not.toBeInTheDocument();
    // localStorage cleared.
    expect(getCurrentThreadId()).toBe(null);

    // Turn 2 — should start fresh.
    await user.type(input, "fresh question");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => expect(captured.length).toBe(2));
    expect(captured[1]).not.toHaveProperty("thread_id");
  });

  it("thread_not_found returns trigger a silent retry — no banner, conversation continues", async () => {
    // Pre-seed localStorage with a stale id, simulating "user reloaded after
    // backend was reset" per the data-model §3 invariant.
    setCurrentThreadId("stale-thread");

    const seenRequests: Captured[] = [];
    let firstCall = true;
    server.use(
      http.post(`${BASE_URL}/query`, async ({ request }) => {
        const body = (await request.json()) as Captured;
        seenRequests.push(body);
        if (firstCall) {
          firstCall = false;
          return HttpResponse.json(
            { error: { code: "thread_not_found", message: "x" } },
            { status: 404 },
          );
        }
        return HttpResponse.json(
          makeQueryResponse({ thread_id: "fresh-thread" }),
        );
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });
    await user.type(input, "hi");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    // The user should never see an error banner.
    await waitFor(() => expect(seenRequests.length).toBe(2));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // First request carried the stale id; second request did not.
    expect(seenRequests[0]?.thread_id).toBe("stale-thread");
    expect(seenRequests[1]).not.toHaveProperty("thread_id");

    // localStorage now reflects the fresh thread id.
    await waitFor(() => expect(getCurrentThreadId()).toBe("fresh-thread"));
  });

  it("US3.3 — pre-seeded thread_id survives mount; next request carries it", async () => {
    setCurrentThreadId("pre-existing-thread");
    const { captured } = setupCapturingHandler((req) =>
      HttpResponse.json(
        makeQueryResponse({ thread_id: req.thread_id ?? "ignored" }),
      ),
    );

    const user = userEvent.setup();
    render(<App />);

    // The thread display should show the pre-seeded id at mount.
    await waitFor(() =>
      expect(screen.getByTestId("thread-id-display")).toHaveTextContent(
        /pre-/,
      ),
    );

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });
    await user.type(input, "follow-up after refresh");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => expect(captured.length).toBe(1));
    expect(captured[0]?.thread_id).toBe("pre-existing-thread");
  });
});
