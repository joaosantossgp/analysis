/**
 * desktop-data-events.ts — sinal global pra forçar componentes desktop
 * a re-buscar dados após uma operação de mutação (refresh on-demand).
 *
 * Por que existe: no modo desktop não há servidor Next, então
 * `router.refresh()` não reexecuta loaders client-side. Em vez disso,
 * os loaders escutam este sinal e bumpam a chave de fetch.
 */

"use client";

import { useEffect, useState } from "react";

const EVENT_NAME = "desktop-data-refreshed";

type Detail = { cdCvm?: number; scope?: "company" | "sectors" | "all" };

export function dispatchDesktopDataRefreshed(detail: Detail = {}): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<Detail>(EVENT_NAME, { detail }));
}

/**
 * Retorna um contador que incrementa a cada `desktop-data-refreshed`
 * cujo `detail` casa com os filtros. Use no array de deps do useEffect
 * do loader para forçar refetch.
 */
export function useDesktopDataRefreshTick(
  filter: { cdCvm?: number; scope?: "company" | "sectors" | "all" } = {},
): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;

    function handler(event: Event) {
      const ce = event as CustomEvent<Detail>;
      const detail = ce.detail ?? {};

      if (filter.cdCvm !== undefined && detail.cdCvm !== undefined) {
        if (detail.cdCvm !== filter.cdCvm) return;
      }

      if (filter.scope && detail.scope && detail.scope !== filter.scope) {
        if (detail.scope !== "all") return;
      }

      setTick((t) => t + 1);
    }

    window.addEventListener(EVENT_NAME, handler);
    return () => window.removeEventListener(EVENT_NAME, handler);
  }, [filter.cdCvm, filter.scope]);

  return tick;
}
