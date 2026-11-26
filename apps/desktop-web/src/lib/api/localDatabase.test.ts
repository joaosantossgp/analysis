import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchLocalDatabaseState } from "./localDatabase";

describe("fetchLocalDatabaseState", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  // #576: on launch pywebview injects the API after React's first fetch.
  it("waits for the desktop bridge instead of returning null before it is injected", async () => {
    vi.useFakeTimers();
    const testWindow = Object.assign(new EventTarget(), {
      setInterval,
      clearInterval,
      setTimeout,
      clearTimeout,
      pywebview: undefined as unknown,
    });
    vi.stubGlobal("window", testWindow);
    const state = { status: "empty" };

    const result = fetchLocalDatabaseState();
    await vi.advanceTimersByTimeAsync(50);
    testWindow.pywebview = { api: { ping: vi.fn(), get_local_database_state: vi.fn(async () => state) } };
    await vi.advanceTimersByTimeAsync(25);

    await expect(result).resolves.toBe(state);
  });

  it("returns null in browser mode once no bridge arrives", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", Object.assign(new EventTarget(), { setInterval, clearInterval, setTimeout, clearTimeout }));

    const result = fetchLocalDatabaseState();
    await vi.advanceTimersByTimeAsync(5_000);

    await expect(result).resolves.toBeNull();
  });
});
