// MSW-backed end-to-end test for US1: type → submit → chart appears.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "../../src/App";
import { server } from "../setup";
import { makeQueryResponse } from "../mocks/factories";
import { clearCurrentThreadId } from "../../src/utils/localStorage";

const BASE_URL = "http://localhost:8000";

describe("US1 — Ask a question and see the chart", () => {
  afterEach(() => {
    clearCurrentThreadId();
  });

  it("scenario 1: success → user message + assistant message + iframe", async () => {
    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });
    await user.type(input, "Show releases by decade");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // User message renders immediately (this also forces the React tree to
    // settle on the post-submit render).
    expect(
      await screen.findByText("Show releases by decade"),
    ).toBeInTheDocument();

    // Assistant text appears (default factory copy).
    await waitFor(() =>
      expect(
        screen.getByText(/Generated a chart of releases by decade\./i),
      ).toBeInTheDocument(),
    );

    // Iframe renders with absolute URL on the right side.
    const iframe = screen.getByTitle("Generated chart") as HTMLIFrameElement;
    expect(iframe.getAttribute("src")).toMatch(
      /^http:\/\/localhost:8000\/artifacts\//,
    );
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");

    // Input re-enabled after response.
    expect(input).not.toBeDisabled();
  });

  it("disables input while a query is in flight", async () => {
    // Hold the response open so we can observe the pending state.
    let release!: (value: Response) => void;
    const responsePromise = new Promise<Response>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post(`${BASE_URL}/query`, async () => {
        const response = await responsePromise;
        return response;
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });
    await user.type(input, "Show releases by decade");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Pending: input is disabled.
    await waitFor(() => expect(input).toBeDisabled());

    // Release the response and confirm the input re-enables.
    release(HttpResponse.json(makeQueryResponse()) as unknown as Response);
    await waitFor(() => expect(input).not.toBeDisabled());
  });

  it("scenario 2: controlled-failure → assistant text + 'no chart' placeholder, NO error banner", async () => {
    server.use(
      http.post(`${BASE_URL}/query`, async () =>
        HttpResponse.json(
          makeQueryResponse({
            status: "failed_unsupported",
            response:
              "I can't answer that — price data isn't part of the published catalog.",
            chart_artifact: null,
            sql: null,
            dataframe_preview: [],
          }),
        ),
      ),
    );
    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });
    await user.type(input, "Show me prices over time");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(
      await screen.findByText(/price data isn't part of the published catalog/i),
    ).toBeInTheDocument();

    // No iframe; the empty placeholder is shown instead.
    expect(screen.queryByTitle("Generated chart")).not.toBeInTheDocument();
    expect(screen.getByText(/no chart yet/i)).toBeInTheDocument();

    // No error banner — controlled failure is not a banner-worthy error.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("scenario 3: backend unreachable → error banner, input re-enabled, no traceback", async () => {
    server.use(
      http.post(`${BASE_URL}/query`, () => HttpResponse.error()),
    );
    const user = userEvent.setup();
    render(<App />);

    const input = screen.getByRole("textbox", {
      name: /Ask a question about the Discogs catalog/i,
    });
    await user.type(input, "Show releases by decade");
    await user.click(screen.getByRole("button", { name: /send/i }));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(/agent is not reachable/i);

    // Input re-enabled.
    expect(input).not.toBeDisabled();

    // No raw traceback / file paths / error class names in the banner.
    expect(banner.textContent).not.toMatch(/Error|Traceback|\/app\/|src\//);
  });
});
