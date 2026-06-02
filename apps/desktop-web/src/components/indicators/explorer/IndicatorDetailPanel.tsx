import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import {
  COUNTRY_ISO_CODES,
  MatrixView,
  buildTrendSeries,
} from "@/components/indicators/CountryKpiCharts";
import { GenerationMix } from "@/components/indicators/SINKpiPanel";
import { fetchSINKPISeries } from "@/lib/api/energyKpis";
import type { CountryKPIValue, SINKPIObservation } from "@/lib/bridge/types";
import type { ChartAesthetics, ResolvedSeries } from "@/lib/indicators/types";
import type { IndicatorRecord, IndicatorSourceGroup } from "@/lib/indicators/registry";

import { StatusBadge, Tag } from "./StatusBadge";

const PREVIEW_CHART: ChartAesthetics = {
  type: "line",
  smooth: true,
  markers: false,
  legend: true,
  grid: true,
  dataLabels: false,
  indexMode: false,
};

const SIN_SUBSYSTEMS = [
  { code: "S", label: "South / Sul", color: "#60A5FA" },
  { code: "SE_CO", label: "Southeast-Center West", color: "#22D3EE" },
  { code: "NE", label: "Northeast / Nordeste", color: "#FBBF24" },
  { code: "N", label: "North / Norte", color: "#4ADE80" },
] as const;

interface DetailProps {
  record: IndicatorRecord | null;
  recordsById: Map<string, IndicatorRecord>;
  countrySeries: CountryKPIValue[];
  sinObservations: SINKPIObservation[];
  bridgeReady: boolean;
  isFavorite: (id: string) => boolean;
  onToggleFavorite: (id: string) => void;
  onSelectRelated: (id: string) => void;
  onRefresh: (group: IndicatorSourceGroup) => void;
  refreshingGroup: IndicatorSourceGroup | null;
  onExport: () => void;
}

export function IndicatorDetailPanel(props: DetailProps) {
  const { record } = props;
  if (!record) {
    return (
      <div
        className="flex items-center justify-center text-center"
        style={{
          border: "1px dashed var(--color-border-subtle)",
          borderRadius: "var(--radius-md)",
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-sm)",
          minHeight: 240,
          padding: 24,
        }}
      >
        Select an indicator to inspect its source, methodology, coverage, and a
        preview chart.
      </div>
    );
  }
  // Keyed remount so per-indicator lazy queries reset cleanly on selection.
  return <DetailBody key={record.id} {...props} record={record} />;
}

function DetailBody({
  record,
  recordsById,
  countrySeries,
  sinObservations,
  bridgeReady,
  isFavorite,
  onToggleFavorite,
  onSelectRelated,
  onRefresh,
  refreshingGroup,
  onExport,
}: DetailProps & { record: IndicatorRecord }) {
  const [showComposite, setShowComposite] = useState(false);
  const isSin = record.sourceGroup === "sin";
  const fav = isFavorite(record.id);
  const refreshing = refreshingGroup === record.sourceGroup;

  // Country preview reuses the cached all-country series; SIN fetches lazily.
  const sinSeriesQuery = useQuery({
    queryKey: ["explorer-sin-series", record.id],
    queryFn: () =>
      fetchSINKPISeries({
        kpi_ids: [record.id],
        subsystem_codes: SIN_SUBSYSTEMS.map((s) => s.code),
        start_datetime: new Date(Date.now() - 365 * 86_400_000).toISOString().slice(0, 19),
        limit: 50_000,
      }),
    enabled: bridgeReady && isSin,
    staleTime: 60_000,
  });

  const country = useMemo(() => {
    if (isSin) return { series: [] as ResolvedSeries[], periods: [] as string[] };
    const plottable = COUNTRY_ISO_CODES.map((iso) => ({ id: iso, axis: "auto" as const, type: "auto" as const }));
    return buildTrendSeries(countrySeries, record.id, plottable, PREVIEW_CHART);
  }, [isSin, countrySeries, record.id]);

  const sin = useMemo(() => {
    if (!isSin) return { series: [] as ResolvedSeries[], periods: [] as string[] };
    const rows = sinSeriesQuery.data?.mode === "desktop" ? sinSeriesQuery.data.values : [];
    return buildSinSeries(rows, record.id);
  }, [isSin, sinSeriesQuery.data, record.id]);

  const chart = isSin ? sin : country;
  const change = useMemo(() => computeChange(chart.series, record.latestValueLabel), [chart, record.latestValueLabel]);

  const related = record.relatedIds
    .map((id) => recordsById.get(id))
    .filter((r): r is IndicatorRecord => Boolean(r));

  return (
    <div
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        display: "flex",
        flexDirection: "column",
        gap: 14,
        padding: 16,
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 style={{ color: "var(--color-text-primary)", fontSize: "var(--text-md)", fontWeight: 600, margin: 0 }}>
            {record.name}
          </h3>
          <div className="flex flex-wrap items-center gap-1.5" style={{ marginTop: 6 }}>
            <StatusBadge status={record.status} />
            <Tag title={record.primarySource}>{record.sourceLabel}</Tag>
            <Tag>{record.theme}</Tag>
            <Tag tone="info">{record.valueType === "derived" ? "derived" : "raw"}</Tag>
          </div>
        </div>
        <button
          type="button"
          aria-label={fav ? "Remove from favorites" : "Add to favorites"}
          aria-pressed={fav}
          onClick={() => onToggleFavorite(record.id)}
          style={{
            background: "transparent",
            border: "none",
            color: fav ? "var(--color-action-primary)" : "var(--color-text-disabled)",
            cursor: "pointer",
            fontSize: "var(--text-lg)",
            lineHeight: 1,
            padding: 0,
          }}
        >
          {fav ? "★" : "☆"}
        </button>
      </div>

      {record.description ? (
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)", margin: 0 }}>
          {record.description}
        </p>
      ) : null}

      {/* Latest value */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span
          className="font-mono"
          style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xl)", fontVariantNumeric: "tabular-nums" }}
        >
          {formatLatest(record.latestValue, record.unit)}
        </span>
        {change ? (
          <span
            className="font-mono"
            style={{
              color: change.dir > 0 ? "var(--color-state-ok)" : change.dir < 0 ? "var(--color-state-err)" : "var(--color-text-tertiary)",
              fontSize: "var(--text-xs)",
            }}
          >
            {change.dir > 0 ? "▲" : change.dir < 0 ? "▼" : "■"} {change.label} YoY
          </span>
        ) : null}
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>
          {record.latestReferenceDate ? `as of ${record.latestReferenceDate}` : "no cached value"}
          {record.latestValueLabel ? ` · ${record.latestValueLabel}` : ""}
        </span>
      </div>

      {/* Preview chart (exactly one) */}
      <PreviewChart
        isSin={isSin}
        loading={isSin && sinSeriesQuery.isLoading}
        error={isSin && sinSeriesQuery.isError}
        series={chart.series}
        periods={chart.periods}
      />

      {/* Reproducibility metadata */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2" style={{ margin: 0 }}>
        <Meta label="Source" value={record.sourceLabel} />
        <Meta label="Primary source" value={record.primarySource} />
        <Meta label="Unit" value={record.unit || "—"} />
        <Meta label="Frequency" value={record.frequency} />
        <Meta label="Geography" value={record.geography} />
        <Meta label="Value type" value={record.valueType === "derived" ? "Derived / calculated" : "Raw"} />
        <Meta label="Methodology" value={record.calculationMethod} />
        <Meta label="Verification" value={record.verificationStatus || "—"} />
        <Meta
          label="Coverage"
          value={
            record.coverageStart || record.coverageEnd
              ? `${shortRef(record.coverageStart)} – ${shortRef(record.coverageEnd)}`
              : "—"
          }
        />
        <Meta label="Last refresh" value={shortDateTime(record.lastRefreshAt)} />
        <Meta label="Data quality" value={record.dataQuality ?? "—"} />
        <Meta
          label="Direction"
          value={record.higherIsBetter === null ? "neutral" : record.higherIsBetter ? "higher is better" : "lower is better"}
        />
      </dl>

      {record.caveats ? <Note label="Caveats" text={record.caveats} tone="warn" /> : null}
      {record.auditNotes ? <Note label="Audit notes" text={record.auditNotes} /> : null}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2">
        <ActionButton onClick={() => onRefresh(record.sourceGroup)} disabled={refreshing} busy={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh source"}
        </ActionButton>
        {!isSin ? <ActionButton onClick={onExport}>Export Excel</ActionButton> : null}
        {canShowComposite(record) ? (
          <ActionButton onClick={() => setShowComposite((s) => !s)} active={showComposite}>
            {showComposite ? "Hide" : isSin ? "Open generation mix" : "Open electricity matrix"}
          </ActionButton>
        ) : null}
      </div>

      {showComposite && canShowComposite(record) ? (
        <div
          style={{
            background: "var(--color-surface-1)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            padding: 12,
          }}
        >
          {isSin ? (
            <GenerationMix latestIndex={buildLatestIndex(sinObservations)} />
          ) : (
            <MatrixView values={countrySeries} year={latestCountryYear(countrySeries)} isoCodes={[...COUNTRY_ISO_CODES]} />
          )}
        </div>
      ) : null}

      {/* Related */}
      {related.length > 0 ? (
        <div>
          <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)", letterSpacing: "0.04em", margin: "0 0 6px", textTransform: "uppercase" }}>
            Related indicators
          </p>
          <div className="flex flex-wrap gap-1.5">
            {related.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => onSelectRelated(r.id)}
                className="focus-visible:outline focus-visible:outline-1"
                style={{
                  background: "var(--color-surface-1)",
                  border: "1px solid var(--color-border-default)",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--color-text-secondary)",
                  cursor: "pointer",
                  fontSize: "var(--text-2xs)",
                  outlineColor: "var(--color-border-focus)",
                  padding: "3px 7px",
                }}
              >
                {r.name}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PreviewChart({
  isSin,
  loading,
  error,
  series,
  periods,
}: {
  isSin: boolean;
  loading: boolean;
  error: boolean;
  series: ResolvedSeries[];
  periods: string[];
}) {
  if (loading) return <StateBanner variant="loading" size="dense" title="Loading series…" />;
  if (error) return <StateBanner variant="error" size="dense" message="Could not load this indicator's series." />;
  if (series.length === 0 || periods.length === 0) {
    return (
      <StateBanner
        variant="empty"
        size="dense"
        title="No cached series"
        message={
          isSin
            ? "No local SIN observations for this KPI yet. Refresh the source to populate the cache."
            : "No cached country values for this KPI yet. Refresh the source to populate the cache."
        }
      />
    );
  }
  return (
    <div>
      <IndicatorChart series={series} periods={periods} config={PREVIEW_CHART} height={220} />
      <div className="flex flex-wrap gap-x-3 gap-y-1" style={{ marginTop: 6 }}>
        {series.map((s) => (
          <span key={s.id} className="flex items-center gap-1.5" style={{ fontSize: "var(--text-2xs)", color: "var(--color-text-tertiary)" }}>
            <span aria-hidden="true" style={{ background: s.color, borderRadius: 1, height: 8, width: 8 }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <dt style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
        {label}
      </dt>
      <dd className="font-mono" style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", margin: 0, wordBreak: "break-word" }}>
        {value}
      </dd>
    </div>
  );
}

function Note({ label, text, tone = "default" }: { label: string; text: string; tone?: "default" | "warn" }) {
  const color = tone === "warn" ? "var(--color-state-warn)" : "var(--color-text-tertiary)";
  return (
    <div
      style={{
        background: "var(--color-surface-1)",
        border: `1px solid ${tone === "warn" ? "var(--color-state-warn)" : "var(--color-border-subtle)"}`,
        borderRadius: "var(--radius-sm)",
        padding: "8px 10px",
      }}
    >
      <p style={{ color, fontSize: "var(--text-2xs)", letterSpacing: "0.04em", margin: "0 0 2px", textTransform: "uppercase" }}>
        {label}
      </p>
      <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", margin: 0 }}>{text}</p>
    </div>
  );
}

function ActionButton({
  children,
  onClick,
  disabled = false,
  busy = false,
  active = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="font-mono focus-visible:outline focus-visible:outline-1"
      style={{
        alignItems: "center",
        background: active ? "var(--color-surface-3)" : "var(--color-surface-1)",
        border: `1px solid ${active ? "var(--color-action-primary)" : "var(--color-border-default)"}`,
        borderRadius: "var(--radius-md)",
        color: active ? "var(--color-action-primary)" : "var(--color-text-secondary)",
        cursor: disabled ? "not-allowed" : "pointer",
        display: "inline-flex",
        fontSize: "var(--text-xs)",
        gap: 6,
        height: 28,
        opacity: disabled ? 0.6 : 1,
        outlineColor: "var(--color-border-focus)",
        padding: "0 10px",
      }}
    >
      {busy ? (
        <span
          aria-hidden="true"
          className="animate-spin"
          style={{
            width: 10,
            height: 10,
            border: "2px solid var(--color-text-tertiary)",
            borderTopColor: "transparent",
            borderRadius: "50%",
            display: "inline-block",
          }}
        />
      ) : null}
      {children}
    </button>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────────────

function canShowComposite(record: IndicatorRecord): boolean {
  return record.themeKey === "generation_mix" ||
    ["renewables", "fossil_dependence", "hydro", "thermal", "nuclear"].includes(record.themeKey);
}

function formatLatest(value: number | null, unit: string): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
  const num = value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const u = (unit || "").trim();
  if (!u || u === "—") return num;
  if (u === "%") return `${num}%`;
  return `${num} ${u}`;
}

function computeChange(
  series: ResolvedSeries[],
  refLabel: string | null,
): { dir: number; label: string } | null {
  const ref = series.find((s) => s.label === refLabel) ?? series[0];
  if (!ref) return null;
  const finite = ref.points.filter((v): v is number => v !== null);
  if (finite.length < 2) return null;
  const last = finite[finite.length - 1];
  const prev = finite[finite.length - 2];
  const abs = last - prev;
  const dir = abs > 0 ? 1 : abs < 0 ? -1 : 0;
  const pct = prev !== 0 ? (abs / Math.abs(prev)) * 100 : null;
  const label = pct !== null ? `${abs >= 0 ? "+" : ""}${pct.toFixed(1)}%` : `${abs >= 0 ? "+" : ""}${abs.toFixed(2)}`;
  return { dir, label };
}

function latestCountryYear(values: CountryKPIValue[]): number {
  const years = values.filter((v) => v.value !== null).map((v) => v.period);
  return years.length > 0 ? Math.max(...years) : new Date().getFullYear() - 1;
}

function buildLatestIndex(values: SINKPIObservation[]): Map<string, SINKPIObservation> {
  const map = new Map<string, SINKPIObservation>();
  for (const row of values) map.set(`${row.kpi_id}|${row.subsystem_code}`, row);
  return map;
}

function shortRef(value: string | null): string {
  if (!value) return "—";
  if (/^\d{4}$/.test(value)) return value;
  return value.slice(0, 10);
}

function shortDateTime(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" });
}

/** Compact daily-mean multi-subsystem series for the SIN preview chart. */
function buildSinSeries(
  rows: SINKPIObservation[],
  kpiId: string,
): { series: ResolvedSeries[]; periods: string[] } {
  const isPct = kpiId.endsWith("pct") || kpiId.includes("share");
  // subsystem -> date -> {sum,count}
  const acc = new Map<string, Map<string, { sum: number; count: number }>>();
  const dateSet = new Set<string>();
  for (const r of rows) {
    if (r.value === null) continue;
    const date = r.reference_datetime.slice(0, 10);
    dateSet.add(date);
    let bySub = acc.get(r.subsystem_code);
    if (!bySub) {
      bySub = new Map();
      acc.set(r.subsystem_code, bySub);
    }
    const cell = bySub.get(date);
    if (cell) {
      cell.sum += r.value;
      cell.count += 1;
    } else {
      bySub.set(date, { sum: r.value, count: 1 });
    }
  }
  const dates = [...dateSet].sort();
  if (dates.length === 0) return { series: [], periods: [] };

  const series: ResolvedSeries[] = SIN_SUBSYSTEMS.filter((sub) => acc.has(sub.code)).map((sub) => {
    const bySub = acc.get(sub.code)!;
    const points = dates.map((d) => {
      const cell = bySub.get(d);
      if (!cell) return null;
      const mean = cell.sum / cell.count;
      return isPct ? mean / 100 : mean;
    });
    const finite = points.filter((v): v is number => v !== null);
    return {
      id: sub.code,
      label: sub.label,
      unit: isPct ? "pct" : "number",
      color: sub.color,
      type: "line",
      axis: "left",
      points,
      latest: finite.length > 0 ? finite[finite.length - 1] : null,
    };
  });

  const periods = dates.map((d) => {
    const [, m, day] = d.split("-");
    return `${m}/${day}`;
  });
  return { series, periods };
}
