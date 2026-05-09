import { describe, expect, it, vi } from "vitest";
import {
  translateHttpError,
  translateNetworkError,
  translateParseError,
} from "../../src/utils/errors";

describe("utils/errors", () => {
  describe("translateHttpError", () => {
    it.each([
      ["invalid_request", "The question couldn't be parsed. Try rephrasing it."],
      [
        "duckdb_unavailable",
        "The catalog isn't available right now. Check that the agent's database is mounted.",
      ],
      [
        "database_unavailable",
        "The agent's session store isn't available right now.",
      ],
      [
        "internal_error",
        "Something went wrong on the agent side. Try again or rephrase.",
      ],
    ])("maps code %s to its curated copy", (code, expected) => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      const result = translateHttpError({
        error: { code, message: "anything" },
      });
      expect(result.kind).toBe("http");
      expect(result.copy).toBe(expected);
    });

    it("falls back to the internal_error copy for unknown codes", () => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      const result = translateHttpError({
        error: { code: "totally_unknown_code", message: "x" },
      });
      expect(result.copy).toBe(
        "Something went wrong on the agent side. Try again or rephrase.",
      );
    });

    it("returns only kind+copy keys (data-model §1.7 invariant)", () => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      const result = translateHttpError({
        error: {
          code: "invalid_request",
          message: "/agent/internal/path:42",
          details: { secret: "leak" },
        },
      });
      expect(Object.keys(result).sort()).toEqual(["copy", "kind"]);
    });
  });

  describe("translateNetworkError", () => {
    it("returns the network copy regardless of input", () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const result = translateNetworkError(new TypeError("Failed to fetch"));
      expect(result.kind).toBe("network");
      expect(result.copy).toBe(
        "The agent is not reachable. Check that the local stack is running.",
      );
    });

    it("returns only kind+copy keys", () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const err = new Error("with stack");
      const result = translateNetworkError(err);
      expect(Object.keys(result).sort()).toEqual(["copy", "kind"]);
    });
  });

  describe("translateParseError", () => {
    it("returns the parse copy", () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      const result = translateParseError(new SyntaxError("unexpected"));
      expect(result.kind).toBe("parse");
      expect(result.copy).toBe("The agent returned an unexpected response.");
    });
  });
});
