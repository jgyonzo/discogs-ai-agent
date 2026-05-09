import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sendQuery, toAbsoluteArtifactUrl } from "../../src/api/client";
import {
  clearCurrentThreadId,
  getCurrentThreadId,
  setCurrentThreadId,
} from "../../src/utils/localStorage";
import { server } from "../setup";

describe("api/client", () => {
  describe("toAbsoluteArtifactUrl", () => {
    it("prepends the base URL to a relative path", () => {
      // VITE_API_BASE_URL is unset in the test env; the fallback wins.
      expect(toAbsoluteArtifactUrl("/artifacts/abc")).toBe(
        "http://localhost:8000/artifacts/abc",
      );
    });

    it("preserves an absolute URL", () => {
      expect(toAbsoluteArtifactUrl("http://example.com/x")).toBe(
        "http://example.com/x",
      );
      expect(toAbsoluteArtifactUrl("https://example.com/x")).toBe(
        "https://example.com/x",
      );
    });
  });

  describe("sendQuery", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let fetchSpy: any;

    beforeEach(() => {
      // We bypass MSW for fine-grained control of the response shape & errors.
      server.close();
    });

    afterEach(() => {
      vi.restoreAllMocks();
      clearCurrentThreadId();
      // Bring MSW back up for any subsequent test.
      server.listen({ onUnhandledRequest: "error" });
    });

    it("returns the parsed body on a 200 OK response", async () => {
      const responseBody = {
        thread_id: "t-1",
        run_id: "r-1",
        response: "ok",
        status: "succeeded",
        route: { complexity: "simple", selected_model: "gpt-4o-mini" },
        sql: "SELECT 1",
        code: null,
        chart_artifact: null,
        dataframe_preview: [],
        row_count: 0,
        carryover: { turn_count: 0, preamble: null },
      };
      fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(JSON.stringify(responseBody), { status: 200 }),
      );
      const result = await sendQuery({ message: "hi" });
      expect(result).toEqual(responseBody);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it("omits thread_id from the body when null/undefined", async () => {
      fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(
          JSON.stringify({
            thread_id: "t-1",
            run_id: "r-1",
            response: "ok",
            status: "succeeded",
            route: {},
            sql: null,
            code: null,
            chart_artifact: null,
            dataframe_preview: [],
            row_count: 0,
            carryover: { turn_count: 0, preamble: null },
          }),
          { status: 200 },
        ),
      );
      await sendQuery({ thread_id: null, message: "hi" });
      const body = JSON.parse(
        (fetchSpy.mock.calls[0]?.[1] as RequestInit).body as string,
      );
      expect(body).toEqual({ message: "hi" });
      expect(body).not.toHaveProperty("thread_id");
    });

    it("includes thread_id in the body when present", async () => {
      fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(
          JSON.stringify({
            thread_id: "t-1",
            run_id: "r-1",
            response: "ok",
            status: "succeeded",
            route: {},
            sql: null,
            code: null,
            chart_artifact: null,
            dataframe_preview: [],
            row_count: 0,
            carryover: { turn_count: 0, preamble: null },
          }),
          { status: 200 },
        ),
      );
      await sendQuery({ thread_id: "abc", message: "hi" });
      const body = JSON.parse(
        (fetchSpy.mock.calls[0]?.[1] as RequestInit).body as string,
      );
      expect(body).toEqual({ message: "hi", thread_id: "abc" });
    });

    it("throws a UserFacingError with kind=http on a 500 response", async () => {
      vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "internal_error", message: "boom" },
          }),
          { status: 500 },
        ),
      );
      await expect(sendQuery({ message: "hi" })).rejects.toMatchObject({
        kind: "http",
        copy: "Something went wrong on the agent side. Try again or rephrase.",
      });
    });

    it("uses the unknown-code fallback for unfamiliar error codes", async () => {
      vi.spyOn(global, "fetch").mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "some_brand_new_error", message: "x" },
          }),
          { status: 500 },
        ),
      );
      await expect(sendQuery({ message: "hi" })).rejects.toMatchObject({
        kind: "http",
        copy: "Something went wrong on the agent side. Try again or rephrase.",
      });
    });

    it("throws a UserFacingError with kind=network on fetch rejection", async () => {
      vi.spyOn(global, "fetch").mockRejectedValue(
        new TypeError("Failed to fetch"),
      );
      await expect(sendQuery({ message: "hi" })).rejects.toMatchObject({
        kind: "network",
        copy: "The agent is not reachable. Check that the local stack is running.",
      });
    });

    it("throws a UserFacingError with kind=parse on malformed JSON", async () => {
      vi.spyOn(global, "fetch").mockResolvedValue(
        new Response("not json", { status: 200 }),
      );
      await expect(sendQuery({ message: "hi" })).rejects.toMatchObject({
        kind: "parse",
      });
    });

    it("silently retries on 404 thread_not_found and clears localStorage", async () => {
      setCurrentThreadId("stale-thread-id");
      const successBody = {
        thread_id: "fresh-thread-id",
        run_id: "r-2",
        response: "ok",
        status: "succeeded",
        route: {},
        sql: null,
        code: null,
        chart_artifact: null,
        dataframe_preview: [],
        row_count: 0,
        carryover: { turn_count: 0, preamble: null },
      };
      fetchSpy = vi
        .spyOn(global, "fetch")
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              error: { code: "thread_not_found", message: "x" },
            }),
            { status: 404 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify(successBody), { status: 200 }),
        );

      const result = await sendQuery({
        thread_id: "stale-thread-id",
        message: "hi",
      });

      expect(result).toEqual(successBody);
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      // Second call must NOT carry thread_id.
      const retryBody = JSON.parse(
        (fetchSpy.mock.calls[1]?.[1] as RequestInit).body as string,
      );
      expect(retryBody).toEqual({ message: "hi" });

      // localStorage was cleared as part of the silent retry. (Verified via
      // the project utility — the request-body assertion above is the
      // primary proof that the silent retry happened correctly.)
      expect(getCurrentThreadId()).toBe(null);
    });

    it("propagates the retry's error if the silent retry also fails", async () => {
      setCurrentThreadId("stale");
      vi.spyOn(global, "fetch")
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              error: { code: "thread_not_found", message: "x" },
            }),
            { status: 404 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              error: { code: "internal_error", message: "x" },
            }),
            { status: 500 },
          ),
        );

      await expect(
        sendQuery({ thread_id: "stale", message: "hi" }),
      ).rejects.toMatchObject({
        kind: "http",
        copy: "Something went wrong on the agent side. Try again or rephrase.",
      });
    });
  });
});
