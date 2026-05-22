import { TabularData } from "@/lib/bridge/types";

interface DataPoint {
  year: number;
  value: number | null;
}

interface TrendChartProps {
  title: string;
  data: DataPoint[];
  formatType: "pct" | "ratio" | string;
  color: string;
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
        color="#38bdf8" // accent-info (Teal/Sky)
      />
      <TrendChartCard
        title="Margem Líquida"
        data={netMarginData}
        formatType="pct"
        color="#06b6d4" // Cyan
      />
      <TrendChartCard
        title="Retorno s/ Patrimônio (ROE)"
        data={roeData}
        formatType="pct"
        color="#22c55e" // accent-success (Green)
      />
      <TrendChartCard
        title="Alavancagem (Dívida Líq. / EBITDA)"
        data={leverageData}
        formatType="ratio"
        color="#f5a524" // accent-primary (Amber)
      />
    </div>
  );
}

function TrendChartCard({ title, data, formatType, color }: TrendChartProps) {
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
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 shadow-lg flex flex-col justify-between">
      <header className="mb-2">
        <h4 className="text-xs uppercase tracking-wider text-zinc-400 font-semibold">{title}</h4>
      </header>

      {!hasData ? (
        <div className="h-32 flex items-center justify-center border border-dashed border-zinc-800 rounded bg-zinc-950/20">
          <span className="text-xs text-zinc-600">Nenhum dado histórico disponível</span>
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
                    stroke="rgba(255, 255, 255, 0.08)"
                    strokeWidth={1}
                    strokeDasharray="4 4"
                  />
                  <text
                    x={padLeft - 8}
                    y={yPos + 3}
                    textAnchor="end"
                    fill="#747b88"
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
                  fill="#747b88"
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
              stroke={color}
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
                    fill="#08090b"
                    stroke={color}
                    strokeWidth={1.5}
                    className="transition-all duration-150 group-hover/dot:r-4 group-hover/dot:stroke-zinc-100"
                  />
                  {/* Tooltip on hover */}
                  <title>{`${p.year}: ${formatVal(p.value)}`}</title>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </article>
  );
}
