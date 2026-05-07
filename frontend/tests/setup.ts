import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import { setupServer } from "msw/node";
import { handlers } from "./mocks/handlers";

// Node 25 ships an experimental built-in `localStorage` that is half-broken
// when `--localstorage-file` is not provided (it warns once and silently
// no-ops set/get). It overrides jsdom's localStorage in vitest's runtime.
// Replace it with an in-memory store that mirrors the Storage interface.
class MemoryStorage implements Storage {
  private readonly store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  key(index: number) {
    return [...this.store.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}

const memoryLocalStorage = new MemoryStorage();
Object.defineProperty(window, "localStorage", {
  configurable: true,
  writable: true,
  value: memoryLocalStorage,
});
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  writable: true,
  value: memoryLocalStorage,
});

export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  memoryLocalStorage.clear();
  server.resetHandlers();
});
afterAll(() => server.close());
