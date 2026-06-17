import { useEffect, useState } from "react";

import { useBridgeStatus, type BridgeProbe } from "@/hooks/useBridgeStatus";
import { Kbd } from "@/components/ui/Kbd";

import { ModuleNav } from "./ModuleNav";

/**
 * Persistent top app bar. Brand mark + ModuleNav + right cluster (command
 * bar trigger placeholder, bridge pill, UTC clock). 36px tall.
 *
 * The command bar trigger is a placeholder button — UX-2 will wire the
 * Ctrl+K palette behind it.
 */

function useUtcClock(): string {
  const [now, setNow] = useState<Date>(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(id);
  }, []);
  const hh = String(now.getUTCHours()).padStart(2, "0");
  const mm = String(now.getUTCMinutes()).padStart(2, "0");
  const ss = String(now.getUTCSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss} UTC`;
}

function bridgePillStyle(probe: BridgeProbe): { label: string; color: string; border: string } {
  switch (probe.kind) {
    case "init":
    case "checking":
      return {
        label: "BRIDGE",
        color: "var(--color-text-secondary)",
        border: "var(--color-border-default)",
      };
    case "ready":
      return {
        label: "DESKTOP",
        color: "var(--color-state-ok)",
        border: "var(--color-state-ok)",
      };
    case "browser":
      return {
        label: "BROWSER",
        color: "var(--color-state-warn)",
        border: "var(--color-state-warn)",
      };
    case "error":
      return {
        label: "ERROR",
        color: "var(--color-state-err)",
        border: "var(--color-state-err)",
      };
  }
}

type Props = {
  onOpenPalette?: () => void;
};

export function TopBar({ onOpenPalette }: Props) {
  const probe = useBridgeStatus();
  const utc = useUtcClock();
  const pill = bridgePillStyle(probe);

  return (
    <header
      className="flex h-full items-stretch"
      style={{
        background: "var(--color-surface-0)",
        borderBottom: "1px solid var(--color-border-default)",
      }}
    >
      {/* Brand mark */}
      <div
        className="flex items-center px-4 font-mono text-sm font-medium tracking-wider"
        style={{ borderRight: "1px solid var(--color-border-subtle)" }}
      >
        <span style={{ color: "var(--color-id-ticker)" }}>CVM</span>
        <span className="px-1" style={{ color: "var(--color-text-tertiary)" }}>·</span>
        <span style={{ color: "var(--color-text-primary)" }}>ANALYTICS</span>
      </div>

      {/* Module nav */}
      <ModuleNav />

      {/* Right cluster */}
      <div className="ml-auto flex min-w-0 shrink items-center gap-2 px-2 sm:px-4">
        <button
          type="button"
          onClick={onOpenPalette}
          className="hidden min-w-0 max-w-72 items-center gap-2 rounded-sm border px-2 py-1 font-mono text-xs hover:border-[var(--color-border-strong)] md:inline-flex"
          style={{
            background: "var(--color-surface-2)",
            borderColor: "var(--color-border-default)",
            color: "var(--color-text-secondary)",
          }}
          title="Open command palette (Ctrl+K)"
          aria-label="Open command palette"
        >
          <span className="truncate">Search companies, sectors…</span>
          <span className="hidden lg:inline-flex">
            <Kbd>Ctrl K</Kbd>
          </span>
        </button>

        <span
          className="hidden items-center gap-1 rounded-sm border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider lg:inline-flex"
          style={{ borderColor: pill.border, color: pill.color }}
          aria-label={`Bridge status: ${pill.label}`}
        >
          <span aria-hidden="true">●</span>
          {pill.label}
        </span>

        <span
          className="hidden font-mono text-2xs tabular-nums xl:inline"
          style={{ color: "var(--color-text-tertiary)" }}
          aria-label="UTC time"
        >
          {utc}
        </span>
      </div>
    </header>
  );
}
