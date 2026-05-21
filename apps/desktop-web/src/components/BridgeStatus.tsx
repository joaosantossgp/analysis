import { useEffect, useState } from "react";

import {
  callBridge,
  getBridgeMode,
  whenBridgeReady,
  type BridgeMode,
} from "@/lib/bridge/adapter";

type Probe =
  | { kind: "init" }
  | { kind: "checking"; mode: BridgeMode }
  | { kind: "ready"; mode: BridgeMode; pingTs: number | null; lastCheckedAt: number }
  | { kind: "browser"; lastCheckedAt: number }
  | { kind: "error"; message: string };

/**
 * Footer indicator that surfaces the live bridge state. Calls `ping` once
 * on mount (and again every 30 s) so the user can see whether the
 * pywebview <-> Python connection is alive without opening DevTools.
 */
export function BridgeStatus() {
  const [probe, setProbe] = useState<Probe>({ kind: "init" });

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const mode = await whenBridgeReady();
      if (cancelled) return;
      if (mode === "browser") {
        setProbe({ kind: "browser", lastCheckedAt: Date.now() });
        return;
      }
      setProbe({ kind: "checking", mode });
      try {
        const { ts } = await callBridge("ping", {});
        if (cancelled) return;
        setProbe({
          kind: "ready",
          mode,
          pingTs: typeof ts === "number" ? ts : null,
          lastCheckedAt: Date.now(),
        });
      } catch (err) {
        if (cancelled) return;
        setProbe({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }

    check();
    const interval = window.setInterval(() => {
      if (getBridgeMode() === "desktop") {
        void check();
      }
    }, 30_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500"
    >
      <ModeBadge probe={probe} />
      <Detail probe={probe} />
    </div>
  );
}

function ModeBadge({ probe }: { probe: Probe }) {
  const { label, classes } = badgeFor(probe);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 font-mono ${classes}`}
    >
      <span aria-hidden="true">●</span>
      {label}
    </span>
  );
}

function Detail({ probe }: { probe: Probe }) {
  switch (probe.kind) {
    case "init":
      return <span>Detecting bridge…</span>;
    case "checking":
      return <span>Pinging Python…</span>;
    case "ready":
      return (
        <span>
          last ping ok
          {probe.pingTs ? ` at ${new Date(probe.pingTs * 1000).toLocaleTimeString("pt-BR")}` : null}
        </span>
      );
    case "browser":
      return (
        <span>
          Open via <code className="font-mono">python scripts/phase1_pywebview_smoke.py --manual</code> for real data.
        </span>
      );
    case "error":
      return <span className="text-rose-400">bridge error: {probe.message}</span>;
  }
}

function badgeFor(probe: Probe): { label: string; classes: string } {
  switch (probe.kind) {
    case "init":
      return { label: "init", classes: "border-zinc-700 bg-zinc-900 text-zinc-300" };
    case "checking":
      return {
        label: probe.mode === "desktop" ? "desktop · checking" : "browser",
        classes: "border-zinc-700 bg-zinc-900 text-zinc-300",
      };
    case "ready":
      return {
        label: "desktop · bridge ready",
        classes: "border-emerald-800 bg-emerald-950/60 text-emerald-300",
      };
    case "browser":
      return {
        label: "browser · no bridge",
        classes: "border-amber-800 bg-amber-950/60 text-amber-200",
      };
    case "error":
      return {
        label: "bridge error",
        classes: "border-rose-800 bg-rose-950/60 text-rose-200",
      };
  }
}
