export type SectorPageTab = "visao-geral" | "empresas";

export function coerceSectorTab(value: string | undefined): SectorPageTab {
  return value === "empresas" ? "empresas" : "visao-geral";
}

export function resolveSectorYear(
  availableYears: number[],
  rawYear: string | undefined,
  fallbackYear: number,
): number {
  if (!rawYear) {
    return fallbackYear;
  }

  const parsed = Number.parseInt(rawYear, 10);
  if (!Number.isFinite(parsed) || !availableYears.includes(parsed)) {
    return fallbackYear;
  }

  return parsed;
}
