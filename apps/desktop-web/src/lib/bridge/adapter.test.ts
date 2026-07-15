import { afterEach, describe, expect, it, vi } from "vitest";

import { whenBridgeReady } from "./adapter";

function installDesktopWindow(api: Record<string, unknown>): EventTarget & { pywebview: { api: Record<string, unknown> } } {
  const testWindow = Object.assign(new EventTarget(), {
    pywebview: { api },
    setInterval,
    clearInterval,
    setTimeout,
    clearTimeout,
  });
  vi.stubGlobal("window", testWindow);
  return testWindow;
}

describe("whenBridgeReady", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("waits for a callable bridge method when pywebview injects an empty API object", async () => {
    const api: Record<string, unknown> = {};
    const testWindow = installDesktopWindow(api);
    let resolved = false;

    const readiness = whenBridgeReady(100).then((mode) => {
      resolved = true;
      return mode;
    });

    await Promise.resolve();
    expect(resolved).toBe(false);

    api.ping = vi.fn();
    testWindow.dispatchEvent(new Event("pywebviewready"));

    await expect(readiness).resolves.toBe("desktop");
  });

  it("detects callable methods installed on a replacement API object", async () => {
    vi.useFakeTimers();
    const testWindow = installDesktopWindow({});
    const readiness = whenBridgeReady(100);

    testWindow.pywebview.api = { get_app_status: vi.fn() };
    await vi.advanceTimersByTimeAsync(25);

    await expect(readiness).resolves.toBe("desktop");
  });

  it("resolves immediately when the compatibility status sentinel is already callable", async () => {
    installDesktopWindow({ get_app_status: vi.fn() });

    await expect(whenBridgeReady()).resolves.toBe("desktop");
  });

  it("does not silently classify an incomplete desktop API as browser at timeout", async () => {
    vi.useFakeTimers();
    installDesktopWindow({});
    const readiness = whenBridgeReady(100);

    await vi.advanceTimersByTimeAsync(100);

    await expect(readiness).resolves.toBe("desktop");
  });

  it("keeps plain browser mode explicit when no pywebview namespace exists", async () => {
    vi.stubGlobal("window", undefined);

    await expect(whenBridgeReady()).resolves.toBe("browser");
  });

  it("uses the bounded browser detection path when a window exists without pywebview", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "window",
      Object.assign(new EventTarget(), { setInterval, clearInterval, setTimeout, clearTimeout }),
    );
    const readiness = whenBridgeReady(100);

    await vi.advanceTimersByTimeAsync(100);

    await expect(readiness).resolves.toBe("browser");
  });
});
