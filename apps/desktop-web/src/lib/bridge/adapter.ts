/**
 * Single adapter that talks to the Python bridge via window.pywebview.api.
 *
 * Components never touch window.pywebview directly. They go through the
 * typed API facades in ../api/*, which all funnel through callBridge below.
 *
 * Bridge modes:
 *  - "desktop"  real pywebview bridge (normal packaged / desktop dev)
 *  - "browser"  no bridge (plain Vite browser preview)
 *  - "mock"     dev-only fixture bridge (VITE_MOCK_BRIDGE=1 + import.meta.env.DEV)
 */

import type { BridgeApi } from "./types";

export type BridgeMode = "desktop" | "browser" | "mock";

export class BridgeError extends Error {
  public readonly method: string;
  public readonly mode: BridgeMode;

  constructor(method: string, message: string, mode: BridgeMode) {
    super(`[bridge:${method}] ${message}`);
    this.name = "BridgeError";
    this.method = method;
    this.mode = mode;
  }
}

// ---------------------------------------------------------------------------
// Mock bridge — dev-only, gated by VITE_MOCK_BRIDGE=1
// import.meta.env.DEV is a Vite compile-time constant (false in prod builds)
// so the dynamic import below is dead code in production and tree-shaken out.
// ---------------------------------------------------------------------------

let _mockBridgeCache: Partial<BridgeApi> | null | undefined = undefined;
let pendingBridgeReadiness: Promise<BridgeMode> | null = null;

/** True only when running in a Vite dev build with VITE_MOCK_BRIDGE=1. */
export function isMockBridgeEnabled(): boolean {
  return import.meta.env.DEV === true && import.meta.env.VITE_MOCK_BRIDGE === "1";
}

async function getMockBridge(): Promise<Partial<BridgeApi> | null> {
  if (!isMockBridgeEnabled()) return null;
  if (_mockBridgeCache === undefined) {
    // Dynamic import excluded from production bundle by Vite dead-code elimination.
    const { createMockBridge } = await import("./mock");
    _mockBridgeCache = createMockBridge();
  }
  return _mockBridgeCache;
}

// ---------------------------------------------------------------------------

export function isBridgeAvailable(): boolean {
  return (
    typeof window !== "undefined" && typeof window.pywebview?.api !== "undefined"
  );
}

/** A desktop bridge is callable only after a stable status sentinel is installed. */
export function hasCallableBridgeSentinel(): boolean {
  const api = typeof window === "undefined" ? undefined : window.pywebview?.api;
  return typeof api?.ping === "function" || typeof api?.get_app_status === "function";
}

export function getBridgeMode(): BridgeMode {
  if (isMockBridgeEnabled()) return "mock";
  return isBridgeAvailable() ? "desktop" : "browser";
}

/**
 * Resolves when window.pywebview.api is injected. pywebview emits the
 * `pywebviewready` event after the DOM is ready but before user JS executes;
 * however, when React 19 hydrates the root before pywebview finishes its
 * injection, we need to wait. This helper covers both orderings.
 *
 * Resolves immediately in browser mode (no bridge will ever arrive) and
 * in mock mode (fixture bridge is always ready).
 */
export function whenBridgeReady(timeoutMs = 5000): Promise<BridgeMode> {
  if (typeof window === "undefined") {
    return Promise.resolve("browser");
  }
  if (isMockBridgeEnabled()) {
    return Promise.resolve("mock");
  }
  if (hasCallableBridgeSentinel()) {
    return Promise.resolve("desktop");
  }
  if (pendingBridgeReadiness) {
    return pendingBridgeReadiness;
  }

  const readiness = new Promise<BridgeMode>((resolve) => {
    let settled = false;
    let pollIntervalId: number | null = null;
    let timeoutId: number | null = null;
    const finish = (mode: BridgeMode) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("pywebviewready", onReady);
      if (pollIntervalId !== null) window.clearInterval(pollIntervalId);
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      resolve(mode);
    };

    const finishWhenCallable = () => {
      if (hasCallableBridgeSentinel()) finish("desktop");
    };
    const onReady = () => finishWhenCallable();

    window.addEventListener("pywebviewready", onReady, { once: true });
    pollIntervalId = window.setInterval(finishWhenCallable, 25);
    timeoutId = window.setTimeout(() => {
      finish(isBridgeAvailable() ? "desktop" : "browser");
    }, timeoutMs);
    finishWhenCallable();
  });
  pendingBridgeReadiness = readiness;
  void readiness.finally(() => {
    if (pendingBridgeReadiness === readiness) pendingBridgeReadiness = null;
  });
  return readiness;
}

/**
 * Strongly-typed forward to a Python bridge method. Components and API
 * facades should call this instead of touching window.pywebview directly.
 *
 * When mock bridge is enabled (VITE_MOCK_BRIDGE=1 in dev), calls are routed
 * to the in-process fixture implementation instead of the Python backend.
 */
export async function callBridge<K extends keyof BridgeApi>(
  method: K,
  params: Parameters<BridgeApi[K]>[0],
): Promise<Awaited<ReturnType<BridgeApi[K]>>> {
  // Mock bridge path — dev only
  if (isMockBridgeEnabled()) {
    const mock = await getMockBridge();
    if (mock && method in mock) {
      const fn = mock[method] as (
        p: Parameters<BridgeApi[K]>[0],
      ) => Promise<Awaited<ReturnType<BridgeApi[K]>>>;
      return fn(params);
    }
    throw new BridgeError(
      String(method),
      `Method "${String(method)}" not implemented in mock bridge`,
      "mock",
    );
  }

  if (!isBridgeAvailable()) {
    throw new BridgeError(
      String(method),
      "pywebview.api unavailable (running in browser mode?)",
      "browser",
    );
  }
  const api = window.pywebview!.api;
  const fn = api[method] as (
    p: Parameters<BridgeApi[K]>[0],
  ) => Promise<Awaited<ReturnType<BridgeApi[K]>>>;
  if (typeof fn !== "function") {
    throw new BridgeError(
      String(method),
      `method missing from window.pywebview.api`,
      "desktop",
    );
  }
  try {
    return await fn.call(api, params);
  } catch (err) {
    throw new BridgeError(
      String(method),
      err instanceof Error ? err.message : String(err),
      "desktop",
    );
  }
}
