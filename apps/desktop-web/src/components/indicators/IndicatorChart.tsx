import { useMemo, useState } from "react";

import { axisUnitSymbol, formatAxisTick, formatValue } from "@/lib/indicators/format";
import type { AxisSide, ChartAesthetics, ResolvedSeries } from "@/lib/indicators/types";

import { useElementWidth } from "./useElementSize";

interface IndicatorChartProps {
  series: ResolvedSeries[];
  periods: string[];
  config: ChartAesthetics;
  height?: number;
  xTickFormatter?: (val: string) => string;
}

interface Domain {
  min: number;
  max: number;
}

interface RunPoint {
  x: number;
  y: number;
  value: number;
  index: number;
}

interface AxisTick {
  y: number;
  label: string;
}

const PAD_TOP = 16;
const PAD_BOTTOM = 30;
const PAD_LEFT = 52;
const TICK_TARGET = 4; // aim for ~4 intervals (5 ticks)

/** Round a span to a human-friendly magnitude (1 / 2 / 5 × 10ⁿ). */
function niceNum(range: number, round: boolean): number {
  if (!Number.isFinite(range) || range <= 0) return 1;
  const exp = Math.floor(Math.log10(range));
  const frac = range / Math.pow(10, exp);
  let nf: number;
  if (round) {
    nf = frac < 1.5 ? 1 : frac < 3 ? 2 : frac < 7 ? 5 : 10;
  } else {
    nf = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  }
  return nf * Math.pow(10, exp);
}

/** Build round tick values across [min, max] at a nice step. */
function buildTicks(min: number, max: number, step: number): number[] {
  if (step <= 0 || !Number.isFinite(step)) return [min, max];
  const count = Math.round((max - min) / step);
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  const factor = Math.pow(10, decimals);
  const ticks: number[] = [];
  for (let i = 0; i <= count; i += 1) {
    ticks.push(Math.round((min + i * step) * factor) / factor);
  }
  return ticks;
}

/**
 * Data-driven axis bounds rounded to human-friendly tick boundaries, so axis
 * labels read 0/20/40/60/80% rather than 9/19/38/57/76%. Optionally pins the
 * zero baseline (bar/area). Returns the rounded domain plus its tick values.
 */
function niceDomain(values: number[], includeZero: boolean): Domain & { ticks: number[] } {
  if (values.length === 0) return { min: 0, max: 1, ticks: [0, 0.25, 0.5, 0.75, 1] };
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (includeZero) {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
  }
  if (min === max) {
    // Flatline: center the value in a small nice range so it lands on a tick.
    const step = niceNum((Math.abs(min) || 1) * 0.4, true);
    const niceMin = min - 2 * step;
    const niceMax = min + 2 * step;
    return { min: niceMin, max: niceMax, ticks: buildTicks(niceMin, niceMax, step) };
  }
  const step = niceNum((max - min) / TICK_TARGET, true);
  const niceMin = includeZero && min >= 0 ? 0 : Math.floor(min / step) * step;
  const niceMax = includeZero && max <= 0 ? 0 : Math.ceil(max / step) * step;
  return { min: niceMin, max: niceMax, ticks: buildTicks(niceMin, niceMax, step) };
}

/** Split a point array into contiguous runs of finite values. */
function buildRuns(
  points: Array<number | null>,
  xs: number[],
  scaleY: (v: number) => number,
): RunPoint[][] {
  const runs: RunPoint[][] = [];
  let current: RunPoint[] = [];
  points.forEach((value, index) => {
    if (value === null) {
      if (current.length) runs.push(current);
      current = [];
      return;
    }
    current.push({ x: xs[index], y: scaleY(value), value, index });
  });
  if (current.length) runs.push(current);
  return runs;
}

/** Catmull-Rom → cubic bezier for smooth lines; straight segments otherwise. */
function linePath(run: RunPoint[], smooth: boolean): string {
  if (run.length === 0) return "";
  if (run.length === 1) return `M ${run[0].x} ${run[0].y}`;
  if (!smooth) {
    return run.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  }
  let d = `M ${run[0].x} ${run[0].y}`;
  for (let i = 0; i < run.length - 1; i += 1) {
    const p0 = run[i - 1] ?? run[i];
    const p1 = run[i];
    const p2 = run[i + 1];
    const p3 = run[i + 2] ?? run[i + 1];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${p2.x} ${p2.y}`;
  }
  return d;
}

function areaPath(run: RunPoint[], smooth: boolean, baselineY: number): string {
  if (run.length < 2) return "";
  const top = linePath(run, smooth);
  return `${top} L ${run[run.length - 1].x} ${baselineY} L ${run[0].x} ${baselineY} Z`;
}

export function IndicatorChart({ series, periods, config, height = 320, xTickFormatter }: IndicatorChartProps) {
  const [wrapRef, width] = useElementWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const hasRightAxis = useMemo(() => series.some((s) => s.axis === "right"), [series]);
  const padRight = hasRightAxis ? 52 : 16;
  const unitLeft = useMemo(() => series.find((s) => s.axis === "left")?.unit ?? "number", [series]);
  const unitRight = useMemo(
    () => series.find((s) => s.axis === "right")?.unit ?? "number",
    [series],
  );

  const layout = useMemo(() => {
    const w = Math.max(width, 320);
    const plotW = Math.max(0, w - PAD_LEFT - padRight);
    const plotH = Math.max(0, height - PAD_TOP - PAD_BOTTOM);
    const n = periods.length;
    const band = n > 0 ? plotW / n : plotW;
    const centerX = (i: number) => PAD_LEFT + (i + 0.5) * band;

    const barSeries = series.filter((s) => s.type === "bar");
    const axisHasBarOrArea = (axis: AxisSide) =>
      series.some((s) => s.axis === axis && (s.type === "bar" || s.type === "area"));

    const valuesFor = (axis: AxisSide) =>
      series
        .filter((s) => s.axis === axis)
        .flatMap((s) => s.points.filter((v): v is number => v !== null));

    const leftDomain = niceDomain(valuesFor("left"), axisHasBarOrArea("left"));
    const rightDomain = niceDomain(valuesFor("right"), axisHasBarOrArea("right"));

    const makeScale = (domain: Domain) => (v: number) =>
      PAD_TOP + plotH - ((v - domain.min) / (domain.max - domain.min || 1)) * plotH;
    const scaleLeft = makeScale(leftDomain);
    const scaleRight = makeScale(rightDomain);
    const scaleFor = (axis: AxisSide) => (axis === "right" ? scaleRight : scaleLeft);

    const xs = periods.map((_, i) => centerX(i));
    const baselineLeftY = Math.min(Math.max(scaleLeft(0), PAD_TOP), PAD_TOP + plotH);

    // Pre-bake axis ticks so the render body never touches the raw domains.
    // The left axis lands on round values; the right axis reuses the left
    // gridline positions so the two axes stay aligned.
    const leftSpan = leftDomain.max - leftDomain.min || 1;
    const leftTicks: AxisTick[] = leftDomain.ticks.map((v) => ({
      y: scaleLeft(v),
      label: formatAxisTick(v, unitLeft, config.indexMode),
    }));
    const rightTicks: AxisTick[] = leftDomain.ticks.map((v) => {
      const f = (v - leftDomain.min) / leftSpan;
      return {
        y: scaleLeft(v),
        label: formatAxisTick(
          rightDomain.min + f * (rightDomain.max - rightDomain.min),
          unitRight,
          config.indexMode,
        ),
      };
    });

    return {
      w,
      plotW,
      plotH,
      band,
      centerX,
      xs,
      scaleFor,
      barSeries,
      baselineLeftY,
      leftTicks,
      rightTicks,
    };
  }, [width, padRight, height, periods, series, unitLeft, unitRight, config.indexMode]);

  if (periods.length === 0 || series.length === 0) {
    return (
      <div
        className="flex items-center justify-center"
        style={{
          height,
          background: "var(--color-surface-1)",
          border: "1px dashed var(--color-border-subtle)",
          borderRadius: "var(--radius-sm)",
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-xs)",
        }}
      >
        Nothing to plot.
      </div>
    );
  }

  const { w, plotW, plotH, band, centerX, xs, scaleFor, barSeries, baselineLeftY, leftTicks, rightTicks } =
    layout;

  // X-axis label thinning to avoid overlap.
  const maxLabelLength = periods.length > 0 ? Math.max(...periods.map((p) => p.length)) : 4;
  const charWidth = 6.5;
  const labelWidth = Math.max(64, maxLabelLength * charWidth + 16);
  const maxLabels = Math.max(2, Math.floor(plotW / labelWidth));
  const labelStep = Math.max(1, Math.ceil(periods.length / maxLabels));

  const totalPoints = periods.length * series.length;
  const showDataLabels = config.dataLabels && totalPoints <= 24;

  const ariaLabel = `Indicator chart — ${series
    .map((s) => s.label)
    .join(", ")} across ${periods.length} periods`;

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%" }}>
      <svg
        width={w}
        height={height}
        viewBox={`0 0 ${w} ${height}`}
        role="img"
        aria-label={ariaLabel}
        style={{ display: "block", maxWidth: "100%" }}
      >
        {/* Horizontal grid + left/right axis ticks */}
        {leftTicks.map((tick, i) => (
          <g key={`lt-${i}`}>
            {config.grid ? (
              <line
                x1={PAD_LEFT}
                x2={w - padRight}
                y1={tick.y}
                y2={tick.y}
                stroke="var(--color-border-subtle)"
                strokeWidth={1}
                strokeDasharray={i === 0 ? undefined : "3 3"}
                opacity={i === 0 ? 0.8 : 0.5}
              />
            ) : null}
            <text
              x={PAD_LEFT - 8}
              y={tick.y + 3}
              textAnchor="end"
              className="font-mono"
              fill="var(--color-text-tertiary)"
              style={{ fontSize: "var(--text-2xs)" }}
            >
              {tick.label}
            </text>
            {hasRightAxis && rightTicks[i] ? (
              <text
                x={w - padRight + 8}
                y={tick.y + 3}
                textAnchor="start"
                className="font-mono"
                fill="var(--color-text-tertiary)"
                style={{ fontSize: "var(--text-2xs)" }}
              >
                {rightTicks[i].label}
              </text>
            ) : null}
          </g>
        ))}

        {/* Axis unit captions */}
        <text
          x={PAD_LEFT - 8}
          y={PAD_TOP - 5}
          textAnchor="end"
          fill="var(--color-text-tertiary)"
          style={{ fontSize: "var(--text-2xs)" }}
        >
          {axisUnitSymbol(unitLeft, config.indexMode)}
        </text>
        {hasRightAxis ? (
          <text
            x={w - padRight + 8}
            y={PAD_TOP - 5}
            textAnchor="start"
            fill="var(--color-text-tertiary)"
            style={{ fontSize: "var(--text-2xs)" }}
          >
            {axisUnitSymbol(unitRight, config.indexMode)}
          </text>
        ) : null}

        {/* X labels */}
        {periods.map((label, i) =>
          i % labelStep === 0 || i === periods.length - 1 ? (
            <text
              key={label}
              x={centerX(i)}
              y={height - 10}
              textAnchor="middle"
              className="font-mono"
              fill="var(--color-text-tertiary)"
              style={{ fontSize: "var(--text-2xs)" }}
            >
              {xTickFormatter ? xTickFormatter(label) : label}
            </text>
          ) : null,
        )}

        {/* Area fills (drawn first so lines/bars sit on top) */}
        {series
          .filter((s) => s.type === "area")
          .map((s) => {
            const scaleY = scaleFor(s.axis);
            const runs = buildRuns(s.points, xs, scaleY);
            return (
              <g key={`area-${s.id}`}>
                {runs.map((run, ri) => (
                  <path
                    key={ri}
                    d={areaPath(run, config.smooth, baselineLeftY)}
                    fill={s.color}
                    opacity={0.16}
                    stroke="none"
                  />
                ))}
              </g>
            );
          })}

        {/* Bars */}
        {barSeries.length > 0
          ? periods.map((_, i) => {
              const groupWidth = band * 0.7;
              const barWidth = groupWidth / barSeries.length;
              const startX = centerX(i) - groupWidth / 2;
              return (
                <g key={`bars-${i}`}>
                  {barSeries.map((s, bi) => {
                    const v = s.points[i];
                    if (v === null) return null;
                    const scaleY = scaleFor(s.axis);
                    const y0 = Math.min(Math.max(scaleY(0), PAD_TOP), PAD_TOP + plotH);
                    const y1 = scaleY(v);
                    const top = Math.min(y0, y1);
                    const h = Math.max(1, Math.abs(y1 - y0));
                    return (
                      <rect
                        key={s.id}
                        x={startX + bi * barWidth + barWidth * 0.1}
                        y={top}
                        width={barWidth * 0.8}
                        height={h}
                        fill={s.color}
                        opacity={hover === null || hover === i ? 0.9 : 0.5}
                      />
                    );
                  })}
                </g>
              );
            })
          : null}

        {/* Lines + markers */}
        {series
          .filter((s) => s.type === "line" || s.type === "area")
          .map((s) => {
            const scaleY = scaleFor(s.axis);
            const runs = buildRuns(s.points, xs, scaleY);
            return (
              <g key={`line-${s.id}`}>
                {runs.map((run, ri) => (
                  <path
                    key={ri}
                    d={linePath(run, config.smooth)}
                    fill="none"
                    stroke={s.color}
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
                {runs.flatMap((run) =>
                  run.map((p) => {
                    const isSinglePoint = run.length === 1;
                    if (!config.markers && !isSinglePoint) return null;
                    return (
                      <circle
                        key={`${s.id}-${p.index}`}
                        cx={p.x}
                        cy={p.y}
                        r={hover === p.index ? 4.5 : isSinglePoint ? 3.5 : 2.5}
                        fill="var(--color-surface-1)"
                        stroke={s.color}
                        strokeWidth={isSinglePoint ? 2 : 1.5}
                      />
                    );
                  })
                )}
              </g>
            );
          })}

        {/* Data labels */}
        {showDataLabels
          ? series.flatMap((s) => {
              const scaleY = scaleFor(s.axis);
              return s.points.map((v, i) =>
                v === null || s.type === "bar" ? null : (
                  <text
                    key={`dl-${s.id}-${i}`}
                    x={centerX(i)}
                    y={scaleY(v) - 6}
                    textAnchor="middle"
                    className="font-mono"
                    fill={s.color}
                    style={{ fontSize: "var(--text-2xs)" }}
                  >
                    {formatValue(v, s.unit, config.indexMode)}
                  </text>
                ),
              );
            })
          : null}

        {/* Hover guide */}
        {hover !== null ? (
          <line
            x1={centerX(hover)}
            x2={centerX(hover)}
            y1={PAD_TOP}
            y2={PAD_TOP + plotH}
            stroke="var(--color-text-tertiary)"
            strokeWidth={1}
            strokeDasharray="2 2"
            opacity={0.6}
          />
        ) : null}

        {/* Hover capture */}
        <rect
          x={PAD_LEFT}
          y={PAD_TOP}
          width={Math.max(0, plotW)}
          height={Math.max(0, plotH)}
          fill="transparent"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const i = Math.round(mx / (band || 1) - 0.5);
            setHover(Math.min(Math.max(i, 0), periods.length - 1));
          }}
          onMouseLeave={() => setHover(null)}
        />
      </svg>

      {hover !== null ? (
        <ChartTooltip
          periods={periods}
          series={series}
          index={hover}
          x={centerX(hover)}
          width={w}
          indexMode={config.indexMode}
        />
      ) : null}
    </div>
  );
}

function ChartTooltip({
  periods,
  series,
  index,
  x,
  width,
  indexMode,
}: {
  periods: string[];
  series: ResolvedSeries[];
  index: number;
  x: number;
  width: number;
  indexMode: boolean;
}) {
  const boxWidth = 196;
  const left = x > width / 2 ? x - boxWidth - 12 : x + 12;
  return (
    <div
      role="tooltip"
      style={{
        position: "absolute",
        top: PAD_TOP,
        left: Math.max(0, Math.min(left, width - boxWidth)),
        width: boxWidth,
        background: "var(--color-surface-3)",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-sm)",
        boxShadow: "var(--shadow-overlay)",
        padding: "8px 10px",
        pointerEvents: "none",
        zIndex: 5,
      }}
    >
      <div
        className="font-mono"
        style={{
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          marginBottom: 6,
          textTransform: "uppercase",
        }}
      >
        {periods[index]}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {series.map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2" style={{ minWidth: 0 }}>
              <span
                aria-hidden="true"
                style={{
                  background: s.color,
                  borderRadius: 1,
                  display: "inline-block",
                  flexShrink: 0,
                  height: 8,
                  width: 8,
                }}
              />
              <span
                className="truncate"
                style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}
                title={s.label}
              >
                {s.label}
              </span>
            </span>
            <span
              className="font-mono"
              style={{
                color: "var(--color-text-primary)",
                fontSize: "var(--text-xs)",
                fontVariantNumeric: "tabular-nums",
                whiteSpace: "nowrap",
              }}
            >
              {formatValue(s.points[index], s.unit, indexMode)}
              {s.axis === "right" ? (
                <span style={{ color: "var(--color-text-tertiary)" }}> ·R</span>
              ) : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
