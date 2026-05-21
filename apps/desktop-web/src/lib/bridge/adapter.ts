/**
 * Single adapter that talks to the Python bridge via window.pywebview.api.
 *
 * Components never touch window.pywebview directly. They go through the
 * typed API facades in ../api/*, which all funnel through callBridge below.
 *
 * Phase 1 scope:
 *  - Detect bridge availability (true inside pywebview, false in browser dev).
 *  - Wait for the pywebviewready event so React boots before the API arrives.
 *  - Forward method calls and standardise error shape.
 *
 * Phase 2 will extend this with:
 *  - Optional HTTP fallback for browser-mode dev iteration.
 *  - Retry / timeout policy aligned with TanStack Query.
 */

import type { BridgeApi } from "./types";

export type BridgeMode = "desktop" | "browser";

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

export function isBridgeAvailable(): boolean {
  return (
    typeof window !== "undefined" && typeof window.pywebview?.api !== "undefined"
  );
}

export function getBridgeMode(): BridgeMode {
  return isBridgeAvailable() ? "desktop" : "browser";
}

/**
 * Resolves when window.pywebview.api is injected. pywebview emits the
 * `pywebviewready` event after the DOM is ready but before user JS executes;
 * however, when React 19 hydrates the root before pywebview finishes its
 * injection, we need to wait. This helper covers both orderings.
 *
 * Resolves immediately in browser mode (no bridge will ever arrive) — the
 * caller should branch on getBridgeMode().
 */
export function whenBridgeReady(timeoutMs = 5000): Promise<BridgeMode> {
  if (typeof window === "undefined") {
    return Promise.resolve("browser");
  }
  if (isBridgeAvailable()) {
    return Promise.resolve("desktop");
  }
  return new Promise<BridgeMode>((resolve) => {
    let settled = false;
    const finish = (mode: BridgeMode) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("pywebviewready", onReady);
      clearTimeout(timer);
      resolve(mode);
    };
    const onReady = () => finish("desktop");
    window.addEventListener("pywebviewready", onReady, { once: true });
    const timer = setTimeout(() => {
      finish(isBridgeAvailable() ? "desktop" : "browser");
    }, timeoutMs);
  });
}

/**
 * Strongly-typed forward to a Python bridge method. Components and API
 * facades should call this instead of touching window.pywebview directly.
 */
export async function callBridge<K extends keyof BridgeApi>(
  method: K,
  params: Parameters<BridgeApi[K]>[0],
): Promise<Awaited<ReturnType<BridgeApi[K]>>> {
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
