type SparklineProps = {
  values: Array<number | null | undefined>;
  width?: number;
  height?: number;
  label?: string;
  className?: string;
};

type Point = {
  x: number;
  y: number;
  value: number | null;
};

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function buildPoints(
  values: Array<number | null | undefined>,
  width: number,
  height: number,
): Point[] {
  const pad = 3;
  const numeric = values.filter(isFiniteNumber);
  if (values.length === 0) return [];

  const min = numeric.length ? Math.min(...numeric) : 0;
  const max = numeric.length ? Math.max(...numeric) : 0;
  const range = max - min || 1;
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;

  return values.map((value, index) => ({
    x: pad + step * index,
    y: isFiniteNumber(value)
      ? pad + (height - pad * 2) - ((value - min) / range) * (height - pad * 2)
      : height / 2,
    value: isFiniteNumber(value) ? value : null,
  }));
}

function buildPath(points: Point[]): string {
  let path = "";
  let drawing = false;
  for (const point of points) {
    if (point.value === null) {
      drawing = false;
      continue;
    }
    path += drawing
      ? ` L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
      : `M ${point.x.toFixed(2)} ${point.y.toFixed(2)}`;
    drawing = true;
  }
  return path;
}

export function Sparkline({
  values,
  width = 80,
  height = 24,
  label,
  className,
}: SparklineProps) {
  const points = buildPoints(values, width, height);
  const path = buildPath(points);
  const hasLine = points.some((point) => point.value !== null);

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      style={{
        color: "var(--color-id-ticker)",
        display: "block",
        overflow: "visible",
      }}
    >
      <line
        x1="0"
        x2={width}
        y1={height - 3}
        y2={height - 3}
        stroke="var(--color-border-subtle)"
        strokeWidth="1"
      />
      {hasLine ? (
        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.6"
          vectorEffect="non-scaling-stroke"
        />
      ) : (
        <line
          x1="4"
          x2={width - 4}
          y1={height / 2}
          y2={height / 2}
          stroke="var(--color-text-tertiary)"
          strokeDasharray="3 3"
          strokeWidth="1"
        />
      )}
    </svg>
  );
}
