import { Panel } from "@/components/surface/Panel";
import { TabularData } from "@/lib/bridge/types";

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

export function KpiTrendCharts({ bundle }: { bundle: { annual: TabularData; years: number[] } | null }) {
  if (!bundle || bundle.years.length === 0) return null;

  const years = [...bundle.years].sort((a, b) => a - b);

  // Extract trend data for key KPIs
  const getTrendData = (kpiId: string): DataPoint[] => {
    const row = bundle.annual.rows.find((r) => String(r.KPI_ID ?? "").trim() === kpiId);
    if (!row) return years.map((yr) => ({ year: yr, value: null }));
    return years.map((yr) => {
      const val = row[String(yr)];
      return {
        year: yr,
        value: typeof val === "number" ? val : null,
      };
    });
  };

  const ebitdaMarginData = getTrendData("MG_EBITDA");
  const netMarginData = getTrendData("MG_LIQ");
  const roeData = getTrendData("ROE");
  const leverageData = getTrendData("DIV_EBITDA");

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <TrendChartCard
        title="Margem EBITDA"
        data={ebitdaMarginData}
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
  const nonNullValues = data.map((d) => d.value).filter((v): v is number => v !== null);
  const hasData = nonNullValues.length > 0;

  let minY = 0;
  let maxY = 1;

  if (hasData) {
    minY = Math.min(...nonNullValues);
    maxY = Math.max(...nonNullValues);
    // If minY and maxY are the same, give some padding to prevent division by zero
    if (minY === maxY) {
      minY -= Math.abs(minY) * 0.1 || 1;
      maxY += Math.abs(maxY) * 0.1 || 1;
    }
  }

  // Add 15% padding on Y boundaries for visual breathing room
  const range = maxY - minY;
  const paddingY = range * 0.15 || 0.1;
  const yMinBound = minY - paddingY;
  const yMaxBound = maxY + paddingY;

  // ViewBox layout dimensions
  const viewWidth = 400;
  const viewHeight = 160;

  const padLeft = 55;
  const padRight = 15;
  const padTop = 15;
  const padBottom = 25;

  const chartWidth = viewWidth - padLeft - padRight;
  const chartHeight = viewHeight - padTop - padBottom;

  const years = data.map((d) => d.year);
  const minX = Math.min(...years);
  const maxX = Math.max(...years);

  const scaleX = (year: number) => {
    if (minX === maxX) return padLeft + chartWidth / 2;
    return padLeft + ((year - minX) / (maxX - minX)) * chartWidth;
  };

  const scaleY = (val: number) => {
    return padTop + chartHeight - ((val - yMinBound) / (yMaxBound - yMinBound)) * chartHeight;
  };

  // Format labels helper
  const formatVal = (val: number): string => {
    if (formatType === "pct") {
      return `${(val * 100).toFixed(1)}%`;
    }
    if (formatType === "ratio") {
      return `${val.toFixed(1)}x`;
    }
    return val.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
  };

  // Generate SVG path string with gap-handling logic
  let pathD = "";
  let drawing = false;
  data.forEach((p) => {
    if (p.value !== null) {
      const x = scaleX(p.year);
      const y = scaleY(p.value);
      if (!drawing) {
        pathD += `M ${x} ${y}`;
        drawing = true;
      } else {
        pathD += ` L ${x} ${y}`;
      }
    } else {
      drawing = false;
    }
  });

  // Calculate 3 grid lines (bottom, middle, top)
  const gridValues = [yMinBound + paddingY, (yMinBound + yMaxBound) / 2, yMaxBound - paddingY];

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
            {/* Grid Lines & Y labels */}
            {gridValues.map((gVal, idx) => {
              const yPos = scaleY(gVal);
              return (
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
              );
            })}

            {/* X labels */}
            {years.map((year, idx) => {
              const xPos = scaleX(year);
              const yPos = viewHeight - 8;
              return (
                <text
                  key={idx}
                  x={xPos}
                  y={yPos}
                  textAnchor="middle"
                  fill="var(--color-text-tertiary)"
                  className="font-mono text-[9px] opacity-75"
                >
                  {year}
                </text>
              );
            })}

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
            {data.map((p, idx) => {
              if (p.value === null) return null;
              const x = scaleX(p.year);
              const y = scaleY(p.value);
              return (
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
                  {/* Tooltip on hover */}
                  <title>{`${p.year}: ${formatVal(p.value)}`}</title>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </Panel>
  );
}
