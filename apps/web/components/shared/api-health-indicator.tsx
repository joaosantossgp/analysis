"use client";

import { useEffect, useState } from "react";

import { isDesktopMode } from "@/lib/api";

const HEALTH_RETRY_MS = 30_000;

export function ApiHealthIndicator() {
  const [desktopMode] = useState(() => isDesktopMode());
  const [apiUnavailable, setApiUnavailable] = useState(false);

  useEffect(() => {
    if (desktopMode) {
      return;
    }

    let active = true;

    const checkHealth = async () => {
      try {
        const response = await fetch("/api/health", {
          cache: "no-store",
          signal: AbortSignal.timeout(5_000),
        });
        if (!active) return;
        setApiUnavailable(!response.ok);
      } catch {
        if (!active) return;
        setApiUnavailable(true);
      }
    };

    void checkHealth();
    const intervalId = window.setInterval(() => {
      void checkHealth();
    }, HEALTH_RETRY_MS);
    const onFocus = () => {
      void checkHealth();
    };

    window.addEventListener("focus", onFocus);

    return () => {
      active = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onFocus);
    };
  }, [desktopMode]);

  if (desktopMode || !apiUnavailable) {
    return null;
  }

  return (
    <div className="border-b border-amber-500/25 bg-amber-500/10 px-4 py-2 text-center text-xs font-medium text-amber-800 dark:text-amber-300">
      API indisponivel - leituras podem falhar.
    </div>
  );
}
