import { useMemo } from "react";

import { Panel } from "@/components/surface/Panel";
import type { TabularData } from "@/lib/bridge/types";

interface DataPoint {
  year: number;
  value: number | null;
}

interface TrendChartProps {
  title: string;
  data: DataPoint[];
  formatType: "pct" | "ratio" | string;
  colorVar: string;
}

function getTrendData(annual: TabularData, years: number[], kpiId: string): DataPoint[] {
  const row = annual.rows.find((r) => String(r.KPI_ID ?? "").trim() === kpiId);
  if (!row) return years.map((yr) => ({ year: yr, value: null }));
  return years.map((yr) => {
    const val = row[String(yr)];
    return { year: yr, value: typeof val === "number" ? val : null };
  });
}

export function KpiTrendCharts({
  bundle,
}: {
  bundle: { annual: TabularData; years: number[] } | null;
}) {
  const sortedYears = useMemo(
    () => (bundle ? [...bundle.years].sort((a, b) => a - b) : []),
    [bundle],
  );

  const ebitdaData = useMemo(
    () => (bundle ? getTrendData(bundle.annual, sortedYears, "MG_EBITDA") : []),
    [bundle, sortedYears],
  );
  const netMarginData = useMemo(
    () => (bundle ? getTrendData(bundle.annual, sortedYears, "MG_LIQ") : []),
    [bundle, sortedYears],
  );
  const roeData = useMemo(
    () => (bundle ? getTrendData(bundle.annual, sortedYears, "ROE") : []),
    [bundle, sortedYears],
  );
  const leverageData = useMemo(
    () => (bundle ? getTrendData(bundle.annual, sortedYears, "DIV_EBITDA") : []),
    [bundle, sortedYears],
  );

  if (!bundle || sortedYears.length === 0) return null;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <TrendChartCard
        title="Margem EBITDA"
        data={ebitdaData}
        formatType="pct"
        colorVar="--color-id-ticker"
      />
      <TrendChartCard
        title="Margem Líquida"
        data={netMarginData}
        formatType="pct"
        colorVar="--color-chart-2"
      />
      <TrendChartCard
        title="Retorno s/ Patrimônio (ROE)"
        data={roeData}
        formatType="pct"
        colorVar="--color-num-pos"
      />
      <TrendChartCard
        title="Alavancagem (Dívida Líq. / EBITDA)"
        data={leverageData}
        formatType="ratio"
        colorVar="--color-action-primary"
      />
    </div>
  );
}

function TrendChartCard({ title, data, formatType, colorVar }: TrendChartProps) {
  // All layout calculations memoized — only recomputes when data changes.
  const chart = useMemo(() => {
    const viewWidth = 400;
    const viewHeight = 160;
    const padLeft = 55;
    const padRight = 15;
    const padTop = 15;
    const padBottom = 25;
    const chartWidth = viewWidth - padLeft - padRight;
    const chartHeight = viewHeight - padTop - padBottom;

    const nonNullValues = data.map((d) => d.value).filter((v): v is number => v !== null);
    const hasData = nonNullValues.length > 0;

    let minY = 0;
    let maxY = 1;
    if (hasData) {
      minY = Math.min(...nonNullValues);
      maxY = Math.max(...nonNullValues);
      if (minY === maxY) {
        minY -= Math.abs(minY) * 0.1 || 1;
        maxY += Math.abs(maxY) * 0.1 || 1;
      }
    }
    const range = maxY - minY;
    const paddingY = range * 0.15 || 0.1;
    const yMinBound = minY - paddingY;
    const yMaxBound = maxY + paddingY;

    const years = data.map((d) => d.year);
    const minX = years.length ? Math.min(...years) : 0;
    const maxX = years.length ? Math.max(...years) : 0;

    const scaleX = (year: number) =>
      minX === maxX
        ? padLeft + chartWidth / 2
        : padLeft + ((year - minX) / (maxX - minX)) * chartWidth;

    const scaleY = (val: number) =>
      padTop + chartHeight - ((val - yMinBound) / (yMaxBound - yMinBound)) * chartHeight;

    // Pre-build SVG path string
    let pathD = "";
    let drawing = false;
    for (const p of data) {
      if (p.value !== null) {
        const x = scaleX(p.year);
        const y = scaleY(p.value);
        pathD += drawing ? ` L ${x} ${y}` : `M ${x} ${y}`;
        drawing = true;
      } else {
        drawing = false;
      }
    }

    const gridValues = [
      yMinBound + paddingY,
      (yMinBound + yMaxBound) / 2,
      yMaxBound - paddingY,
    ];

    const gridLines = gridValues.map((gVal) => ({ gVal, yPos: scaleY(gVal) }));
    const xLabels = years.map((year) => ({ year, xPos: scaleX(year) }));
    const dataDots = data
      .filter((p): p is DataPoint & { value: number } => p.value !== null)
      .map((p) => ({ x: scaleX(p.year), y: scaleY(p.value), year: p.year, value: p.value }));

    return { hasData, pathD, gridLines, xLabels, dataDots, viewWidth, viewHeight, padLeft, padRight };
  }, [data]);

  const formatVal = (val: number): string => {
    if (formatType === "pct") return `${(val * 100).toFixed(1)}%`;
    if (formatType === "ratio") return `${val.toFixed(1)}x`;
    return val.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  };

  const { hasData, pathD, gridLines, xLabels, dataDots, viewWidth, viewHeight, padLeft, padRight } =
    chart;

  return (
    <Panel dense headingLevel={4} title={title}>
      {!hasData ? (
        <div
          className="flex h-32 items-center justify-center"
          style={{
            background: "var(--color-surface-1)",
            border: "1px dashed var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
          }}
        >
          <span style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}>
            Nenhum dado histórico disponível
          </span>
        </div>
      ) : (
        <div className="relative w-full">
          <svg
            viewBox={`0 0 ${viewWidth} ${viewHeight}`}
            className="w-full h-auto overflow-visible select-none"
            aria-label={`Trend chart for ${title}`}
          >
            {/* Grid lines & Y labels */}
            {gridLines.map(({ gVal, yPos }, idx) => (
              <g key={idx} className="opacity-40">
                <line
                  x1={padLeft}
                  y1={yPos}
                  x2={viewWidth - padRight}
                  y2={yPos}
                  stroke="var(--color-border-subtle)"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                />
                <text
                  x={padLeft - 8}
                  y={yPos + 3}
                  textAnchor="end"
                  fill="var(--color-text-tertiary)"
                  className="font-mono text-[9px]"
                >
                  {formatVal(gVal)}
                </text>
              </g>
            ))}

            {/* X labels */}
            {xLabels.map(({ year, xPos }, idx) => (
              <text
                key={idx}
                x={xPos}
                y={viewHeight - 8}
                textAnchor="middle"
                fill="var(--color-text-tertiary)"
                className="font-mono text-[9px] opacity-75"
              >
                {year}
              </text>
            ))}

            {/* Trend line */}
            <path
              d={pathD}
              fill="none"
              stroke={`var(${colorVar})`}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Data points */}
            {dataDots.map(({ x, y, year, value }, idx) => (
              <g key={idx} className="group/dot">
                <circle
                  cx={x}
                  cy={y}
                  r={3}
                  fill="var(--color-surface-1)"
                  stroke={`var(${colorVar})`}
                  strokeWidth={1.5}
                  className="transition-all duration-150 group-hover/dot:r-4"
                />
                <title>{`${year}: ${formatVal(value)}`}</title>
              </g>
            ))}
          </svg>
        </div>
      )}
    </Panel>
  );
}
