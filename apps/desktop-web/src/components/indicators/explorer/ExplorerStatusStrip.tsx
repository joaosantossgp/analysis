import { useMemo } from "react";

import type { IndicatorRecord } from "@/lib/indicators/registry";

/**
 * Local-first status strip. Six dense tiles summarising catalog size, source
 * connectivity, and cache health — derived entirely from the already-built
 * record set so it never drifts from the table below it.
 */
export function ExplorerStatusStrip({ records }: { records: IndicatorRecord[] }) {
  const stats = useMemo(() => {
    const total = records.length;
    const sources = new Set(records.map((r) => r.sourceLabel));
    let cached = 0;
    let stale = 0;
    let failedOrBlocked = 0;
    let lastRefresh: string | null = null;
    for (const r of records) {
      if (r.status === "cached" || r.status === "stale") cached += 1;
      if (r.status === "stale") stale += 1;
      if (r.status === "failed" || r.status === "blocked") failedOrBlocked += 1;
      if (r.lastRefreshAt && (!lastRefresh || r.lastRefreshAt > lastRefresh)) {
        lastRefresh = r.lastRefreshAt;
      }
    }
    return { total, sources: sources.size, cached, stale, failedOrBlocked, lastRefresh };
  }, [records]);

  return (
    <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 xl:grid-cols-6">
      <Tile label="Indicators" value={String(stats.total)} />
      <Tile label="Sources" value={String(stats.sources)} />
      <Tile label="Cached locally" value={`${stats.cached}/${stats.total}`} />
      <Tile
        label="Stale"
        value={String(stats.stale)}
        tone={stats.stale > 0 ? "warn" : "default"}
      />
      <Tile
        label="Failed / blocked"
        value={String(stats.failedOrBlocked)}
        tone={stats.failedOrBlocked > 0 ? "err" : "default"}
      />
      <Tile label="Last refresh" value={formatDate(stats.lastRefresh)} />
    </div>
  );
}

function Tile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "warn" | "err";
}) {
  const valueColor =
    tone === "warn"
      ? "var(--color-state-warn)"
      : tone === "err"
        ? "var(--color-state-err)"
        : "var(--color-text-primary)";
  return (
    <div
      style={{
        background: "var(--color-surface-1)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "8px 10px",
      }}
    >
      <p
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {label}
      </p>
      <p
        className="font-mono"
        style={{
          color: valueColor,
          fontSize: "var(--text-lg)",
          fontVariantNumeric: "tabular-nums",
          margin: "2px 0 0",
        }}
      >
        {value}
      </p>
    </div>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" });
}
