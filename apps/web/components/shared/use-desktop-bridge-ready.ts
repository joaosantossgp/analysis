"use client";

import { useEffect, useState } from "react";

import { isDesktopMode } from "@/lib/desktop-bridge";

export type DesktopBridgeReadyState = "waiting" | "ready" | "timeout";

const BRIDGE_READY_MAX_ATTEMPTS = 60;
const BRIDGE_READY_RETRY_MS = 100;

export function useDesktopBridgeReady(loadKey: string): DesktopBridgeReadyState {
  const [snapshot, setSnapshot] = useState<{
    loadKey: string;
    state: DesktopBridgeReadyState;
  }>({ loadKey, state: "waiting" });

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    function checkBridge() {
      if (cancelled) return;

      if (isDesktopMode()) {
        setSnapshot({ loadKey, state: "ready" });
        return;
      }

      attempts += 1;
      if (attempts <= BRIDGE_READY_MAX_ATTEMPTS) {
        timeoutId = setTimeout(checkBridge, BRIDGE_READY_RETRY_MS);
        return;
      }

      setSnapshot({ loadKey, state: "timeout" });
    }

    timeoutId = setTimeout(checkBridge, 0);

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, [loadKey]);

  return snapshot.loadKey === loadKey ? snapshot.state : "waiting";
}
