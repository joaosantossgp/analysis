import { useBridgeStatus, type BridgeProbe } from "@/hooks/useBridgeStatus";

/**
 * Bottom status strip — single-row 24px. Mirrors the bridge probe + an
 * environment label. Last-refresh timestamp is a placeholder until UX-2 wires
 * the central refresh-job hook.
 */

const ENV_LABEL = import.meta.env.DEV ? "DEV" : "PROD";

function bridgeLabel(probe: BridgeProbe): { label: string; color: string } {
  switch (probe.kind) {
    case "init":
      return { label: "BRIDGE · INIT", color: "var(--color-text-tertiary)" };
    case "checking":
      return {
        label:
          probe.mode === "desktop"
            ? "BRIDGE · CHECKING"
            : probe.mode === "mock"
              ? "BRIDGE · MOCK · CHECKING"
              : "BRIDGE · BROWSER",
        color: "var(--color-text-tertiary)",
      };
    case "ready":
      return probe.mode === "mock"
        ? { label: "BRIDGE · MOCK", color: "#c4b5fd" }
        : { label: "BRIDGE · READY", color: "var(--color-state-ok)" };
    case "browser":
      return { label: "BRIDGE · BROWSER", color: "var(--color-state-warn)" };
    case "error":
      return { label: "BRIDGE · ERROR", color: "var(--color-state-err)" };
  }
}

function lastRefreshLabel(probe: BridgeProbe): string {
  if (probe.kind === "ready" && probe.pingTs) {
    return `LAST PING ${new Date(probe.pingTs * 1000).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })}`;
  }
  if (probe.kind === "browser") {
    return "DATA · OFFLINE";
  }
  if (probe.kind === "error") {
    return `ERROR · ${probe.message.slice(0, 60)}`;
  }
  return "—";
}

export function StatusStrip() {
  const probe = useBridgeStatus();
  const bridge = bridgeLabel(probe);

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex h-full items-center gap-4 px-4 font-mono text-2xs"
      style={{
        background: "var(--color-surface-0)",
        borderTop: "1px solid var(--color-border-subtle)",
        color: "var(--color-text-tertiary)",
      }}
    >
      <span style={{ color: bridge.color }}>
        <span aria-hidden="true">●</span> {bridge.label}
      </span>
      <span aria-hidden="true">|</span>
      <span>{lastRefreshLabel(probe)}</span>
      <span aria-hidden="true">|</span>
      <span>ENV · {ENV_LABEL}</span>
      <span className="ml-auto">CVMAnalytics Terminal</span>
    </div>
  );
}
