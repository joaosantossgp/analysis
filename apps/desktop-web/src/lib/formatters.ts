export function formatUnit(formatType: unknown): string {
  const f = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (f === "pct") return "%";
  if (f === "money") return "R$";
  if (f === "ratio") return "x";
  if (f === "bps") return "bps";
  return "—";
}

export function formatKpiCell(value: unknown, formatType: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "number" || !Number.isFinite(value)) {
    const s = String(value);
    return s.length > 0 ? s : "—";
  }
  const format = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (format === "pct") {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (format === "money") {
    if (Math.abs(value) >= 1_000_000) {
      return `${(value / 1_000_000).toLocaleString("en-US", { maximumFractionDigits: 1 })} mn`;
    }
    return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }
  if (format === "ratio") {
    return `${value.toFixed(2)}x`;
  }
  if (format === "integer") {
    return Math.round(value).toLocaleString("en-US");
  }
  if (format === "bps") {
    return `${Math.round(value)} bps`;
  }
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
