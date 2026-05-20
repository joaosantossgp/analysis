"use client";

import { useEffect, useRef } from "react";

import {
  type DesktopBridgeReadyState,
  useDesktopBridgeReady,
} from "@/components/shared/use-desktop-bridge-ready";

/**
 * Pairs `useDesktopBridgeReady` with a cancellable async loader so consumers
 * stop hand-rolling the gate / cancel-flag / cleanup boilerplate.
 *
 * The effect re-runs whenever `loadKey` changes — encode every input the
 * loader depends on in the key (the existing desktop loaders already follow
 * this convention).
 */
export function useDesktopLoader(
  loadKey: string,
  load: (isCancelled: () => boolean) => Promise<void>,
): DesktopBridgeReadyState {
  const bridgeReady = useDesktopBridgeReady(loadKey);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (bridgeReady !== "ready") return;
    let cancelled = false;
    void loadRef.current(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [bridgeReady, loadKey]);

  return bridgeReady;
}
