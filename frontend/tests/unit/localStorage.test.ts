import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearCurrentThreadId,
  getCurrentThreadId,
  setCurrentThreadId,
} from "../../src/utils/localStorage";

const KEY = "discogs.frontend.currentThreadId";

describe("utils/localStorage", () => {
  beforeEach(() => {
    clearCurrentThreadId();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearCurrentThreadId();
  });

  describe("getCurrentThreadId", () => {
    it("returns null when the key is unset", () => {
      expect(getCurrentThreadId()).toBe(null);
    });

    it("returns the exact stored string when the key is set", () => {
      setCurrentThreadId("abc-123");
      expect(getCurrentThreadId()).toBe("abc-123");
    });

    it("returns null when localStorage.getItem throws (private mode)", () => {
      vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
        throw new Error("private mode");
      });
      expect(getCurrentThreadId()).toBe(null);
    });
  });

  describe("setCurrentThreadId", () => {
    it("writes the exact string with no JSON wrapping", () => {
      const setItemSpy = vi.spyOn(window.localStorage, "setItem");
      setCurrentThreadId("abc-123");
      expect(setItemSpy).toHaveBeenCalledWith(KEY, "abc-123");
    });

    it("is a no-op when localStorage.setItem throws (quota exceeded)", () => {
      vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
        throw new Error("QuotaExceededError");
      });
      // Must not throw.
      expect(() => setCurrentThreadId("abc-123")).not.toThrow();
    });
  });

  describe("clearCurrentThreadId", () => {
    it("removes the key", () => {
      setCurrentThreadId("abc-123");
      clearCurrentThreadId();
      expect(getCurrentThreadId()).toBe(null);
    });

    it("is a no-op when localStorage.removeItem throws", () => {
      vi.spyOn(window.localStorage, "removeItem").mockImplementation(() => {
        throw new Error("private mode");
      });
      expect(() => clearCurrentThreadId()).not.toThrow();
    });
  });

  describe("data-model §3 invariant: only the documented key is written", () => {
    it("never writes to any other localStorage key", () => {
      const setItemSpy = vi.spyOn(window.localStorage, "setItem");
      setCurrentThreadId("abc");
      setCurrentThreadId("def");
      const writtenKeys = new Set(
        setItemSpy.mock.calls.map((call) => call[0]),
      );
      expect(writtenKeys.size).toBe(1);
      expect([...writtenKeys][0]).toBe(KEY);
    });
  });
});
