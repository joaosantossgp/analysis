import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __getBridgeStatusSnapshotForTesting,
  __resetBridgeStatusForTesting,
  triggerBridgeCheck,
} from "./useBridgeStatus";

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

describe("useBridgeStatus probe", () => {
  afterEach(() => {
    vi.useRealTimers();
    __resetBridgeStatusForTesting();
    vi.unstubAllGlobals();
  });

  it("falls back to app status when the desktop bridge does not expose ping", async () => {
    vi.stubGlobal("window", {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      pywebview: {
        api: {
          get_app_status: vi.fn().mockResolvedValue({
            runtime: { bridge_status: "ready" },
          }),
        },
      },
    });

    await triggerBridgeCheck();

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "ready",
      mode: "desktop",
      pingTs: null,
    });
  });

  it("retains the original ping failure when the compatibility fallback also fails", async () => {
    vi.stubGlobal("window", {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      pywebview: {
        api: {
          get_app_status: vi.fn().mockRejectedValue(new Error("status unavailable")),
        },
      },
    });

    await triggerBridgeCheck();

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "error",
      message: expect.stringContaining("[bridge:ping] method missing"),
    });
  });

  it("waits for a transiently incomplete desktop API instead of publishing a missing-method error", async () => {
    const api: Record<string, unknown> = {};
    const testWindow = installDesktopWindow(api);
    const check = triggerBridgeCheck();

    await Promise.resolve();
    expect(__getBridgeStatusSnapshotForTesting()).toEqual({ kind: "init" });

    api.ping = vi.fn().mockResolvedValue({ ts: 123 });
    testWindow.dispatchEvent(new Event("pywebviewready"));
    await check;

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "ready",
      mode: "desktop",
      pingTs: 123,
    });
  });

  it("reports a desktop readiness failure without attempting ping after the API stays incomplete", async () => {
    vi.useFakeTimers();
    installDesktopWindow({});
    const check = triggerBridgeCheck();

    await vi.advanceTimersByTimeAsync(5_000);
    await check;

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "error",
      message: expect.stringContaining("[bridge:readiness]"),
    });
  });

  it("clears a stale error after a later successful check", async () => {
    const ping = vi.fn().mockRejectedValueOnce(new Error("first attempt failed"));
    installDesktopWindow({ ping });

    await triggerBridgeCheck();
    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({ kind: "error" });

    ping.mockResolvedValueOnce({ ts: 456 });
    await triggerBridgeCheck();

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "ready",
      pingTs: 456,
    });
  });

  it("shares overlapping checks so an older result cannot overwrite a newer one", async () => {
    let resolvePing: ((value: { ts: number }) => void) | undefined;
    const ping = vi.fn().mockImplementation(
      () => new Promise<{ ts: number }>((resolve) => {
        resolvePing = resolve;
      }),
    );
    installDesktopWindow({ ping });

    const first = triggerBridgeCheck();
    const second = triggerBridgeCheck();
    await Promise.resolve();

    expect(second).toBe(first);
    expect(ping).toHaveBeenCalledTimes(1);

    resolvePing?.({ ts: 789 });
    await first;

    expect(__getBridgeStatusSnapshotForTesting()).toMatchObject({
      kind: "ready",
      pingTs: 789,
    });
  });
});
