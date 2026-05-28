/**
 * useBridgeStatus — single source of truth for the pywebview bridge state.
 *
 * Extracted from the original `components/BridgeStatus.tsx` so the
 * TerminalShell `StatusStrip` and the footer indicator can subscribe to the
 * same polling cadence without firing two independent intervals.
 *
 * Uses an in-module subscriber set (not React Context) so any consumer can
 * mount/unmount without triggering global rerenders elsewhere in the tree.
 */

import { useEffect, useSyncExternalStore } from "react";

import {
  callBridge,
  getBridgeMode,
  whenBridgeReady,
  type BridgeMode,
} from "@/lib/bridge/adapter";

export type BridgeProbe =
  | { kind: "init" }
  | { kind: "checking"; mode: BridgeMode }
  | { kind: "ready"; mode: BridgeMode; pingTs: number | null; lastCheckedAt: number }
  | { kind: "browser"; lastCheckedAt: number }
  | { kind: "error"; message: string };

let currentProbe: BridgeProbe = { kind: "init" };
const subscribers = new Set<() => void>();
let pollIntervalId: number | null = null;
let pollerStarted = false;

function notify(): void {
  subscribers.forEach((listener) => listener());
}

function setProbe(probe: BridgeProbe): void {
  currentProbe = probe;
  notify();
}

async function check(): Promise<void> {
  const mode = await whenBridgeReady();
  if (mode === "browser") {
    setProbe({ kind: "browser", lastCheckedAt: Date.now() });
    return;
  }
  setProbe({ kind: "checking", mode });
  try {
    const { ts } = await callBridge("ping", {});
    setProbe({
      kind: "ready",
      mode,
      pingTs: typeof ts === "number" ? ts : null,
      lastCheckedAt: Date.now(),
    });
  } catch (err) {
    setProbe({
      kind: "error",
      message: err instanceof Error ? err.message : String(err),
    });
  }
}

function ensurePollerStarted(): void {
  if (pollerStarted) return;
  pollerStarted = true;
  void check();
  pollIntervalId = window.setInterval(() => {
    if (getBridgeMode() !== "browser") {
      void check();
    }
  }, 30_000);
}

function subscribe(listener: () => void): () => void {
  subscribers.add(listener);
  ensurePollerStarted();
  return () => {
    subscribers.delete(listener);
    // Note: poller intentionally stays running for the app's lifetime —
    // unmount/mount churn of consumer components should not restart it.
  };
}

function getSnapshot(): BridgeProbe {
  return currentProbe;
}

export function useBridgeStatus(): BridgeProbe {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/**
 * Imperatively trigger a fresh check (e.g. after manual reconnect attempt).
 * Returns a promise resolving once the check completes.
 */
export function triggerBridgeCheck(): Promise<void> {
  return check();
}

/**
 * Test-only — clear poller state. Not exported via barrel; reach in by path.
 */
export function __resetBridgeStatusForTesting(): void {
  if (pollIntervalId !== null) {
    window.clearInterval(pollIntervalId);
    pollIntervalId = null;
  }
  pollerStarted = false;
  currentProbe = { kind: "init" };
  subscribers.clear();
}

// Re-export the effect hook below so callers that want a useEffect-style
// subscription without rerender-on-change can opt in. Currently unused but
// covers the case where StatusStrip wants to react only on transitions.
export function useBridgeStatusEffect(
  onChange: (probe: BridgeProbe) => void,
): void {
  useEffect(() => {
    return subscribe(() => onChange(currentProbe));
  }, [onChange]);
}
