import { useBridgeStatus, type BridgeProbe } from "@/hooks/useBridgeStatus";

/**
 * Inline bridge indicator. Kept as a thin presentational wrapper around the
 * shared `useBridgeStatus` hook so pages that still import this component
 * (e.g. inline diagnostics) keep working without forcing a second polling
 * cadence. The TerminalShell uses `StatusStrip` instead.
 */
export function BridgeStatus() {
  const probe = useBridgeStatus();
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs"
      style={{ color: "var(--color-text-tertiary)" }}
    >
      <ModeBadge probe={probe} />
      <Detail probe={probe} />
    </div>
  );
}

function ModeBadge({ probe }: { probe: BridgeProbe }) {
  const { label, classes } = badgeFor(probe);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 font-mono ${classes}`}
    >
      <span aria-hidden="true">●</span>
      {label}
    </span>
  );
}

function Detail({ probe }: { probe: BridgeProbe }) {
  switch (probe.kind) {
    case "init":
      return <span>Detecting bridge…</span>;
    case "checking":
      return <span>Pinging Python…</span>;
    case "ready":
      return (
        <span>
          last ping ok
          {probe.pingTs
            ? ` at ${new Date(probe.pingTs * 1000).toLocaleTimeString("en-US")}`
            : null}
        </span>
      );
    case "browser":
      return (
        <span>
          Open via{" "}
          <code className="font-mono">
            python scripts/phase1_pywebview_smoke.py --manual
          </code>{" "}
          for real data.
        </span>
      );
    case "error":
      return (
        <span style={{ color: "var(--color-state-err)" }}>
          bridge error: {probe.message}
        </span>
      );
  }
}

function badgeFor(probe: BridgeProbe): { label: string; classes: string } {
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
