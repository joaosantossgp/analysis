export function buildSparklinePoints(
  anos: number[] | undefined | null,
  width = 54,
  height = 20,
  bottomPadding = 2,
): string {
  if (!anos || anos.length < 2) return "";
  const sorted = [...anos].sort((a, b) => a - b);
  const min = sorted[0]!;
  const max = sorted[sorted.length - 1]!;
  const rangeYears = max - min || 1;
  return sorted
    .map((year, i) => {
      const x = ((year - min) / rangeYears) * width;
      const y =
        height -
        (i / Math.max(sorted.length - 1, 1)) * (height * 0.75) -
        bottomPadding;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
