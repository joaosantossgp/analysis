// GICS é a verdade global para classificação setorial.
// Os 11 setores GICS oficiais (ordem S&P/MSCI) em inglês.
// Slugs derivados normalizando o nome (lower + hyphen). Bater com
// `sector_slugify` em src/ — se divergir, o filtro/rotas quebram.
export const GICS_SECTORS = [
  "Energy",
  "Materials",
  "Industrials",
  "Consumer Discretionary",
  "Consumer Staples",
  "Health Care",
  "Financials",
  "Information Technology",
  "Communication Services",
  "Utilities",
  "Real Estate",
] as const;

export type GicsSector = (typeof GICS_SECTORS)[number];

export const GICS_SECTOR_SLUGS = {
  Energy: "energy",
  Materials: "materials",
  Industrials: "industrials",
  "Consumer Discretionary": "consumer-discretionary",
  "Consumer Staples": "consumer-staples",
  "Health Care": "health-care",
  Financials: "financials",
  "Information Technology": "information-technology",
  "Communication Services": "communication-services",
  Utilities: "utilities",
  "Real Estate": "real-estate",
} as const satisfies Record<GicsSector, string>;

export const GICS_SECTOR_BY_SLUG: Record<string, GicsSector> = Object.fromEntries(
  (Object.entries(GICS_SECTOR_SLUGS) as Array<[GicsSector, string]>).map(
    ([name, slug]) => [slug, name],
  ),
);

export const GICS_SLUG_SET: ReadonlySet<string> = new Set(
  Object.values(GICS_SECTOR_SLUGS),
);

export const SECTOR_COLOR: Record<GicsSector, string> = {
  Energy: "#FF6F00",
  Materials: "#8D6E63",
  Industrials: "#FFB300",
  "Consumer Discretionary": "#E91E63",
  "Consumer Staples": "#558B2F",
  "Health Care": "#43A047",
  Financials: "#1E88E5",
  "Information Technology": "#D32F2F",
  "Communication Services": "#7B1FA2",
  Utilities: "#00897B",
  "Real Estate": "#5E35B1",
};

export const UNCLASSIFIED_SECTOR_LABEL = "Não classificado";
const UNCLASSIFIED_SECTOR_COLOR = "#64748B";

export function getSectorColor(sector: string | null | undefined): string {
  if (!sector) return UNCLASSIFIED_SECTOR_COLOR;
  return (
    (SECTOR_COLOR as Record<string, string>)[sector] ?? UNCLASSIFIED_SECTOR_COLOR
  );
}

export function getSectorNameFromSlug(
  sectorSlug: string | null | undefined,
): string | null {
  if (!sectorSlug) {
    return null;
  }

  return GICS_SECTOR_BY_SLUG[sectorSlug] ?? null;
}

export function getSectorSlugFromName(
  sectorName: string | null | undefined,
): string | null {
  if (!sectorName) {
    return null;
  }
  return (GICS_SECTOR_SLUGS as Record<string, string>)[sectorName] ?? null;
}

export const FEATURED_KPIS = [
  { id: "MG_BRUTA", label: "Margem Bruta", formatType: "pct" },
  { id: "MG_EBITDA", label: "Margem EBITDA", formatType: "pct" },
  { id: "MG_EBIT", label: "Margem EBIT", formatType: "pct" },
  { id: "MG_LIQ", label: "Margem Liquida", formatType: "pct" },
  { id: "ROE", label: "ROE", formatType: "pct" },
  { id: "ROA", label: "ROA", formatType: "pct" },
  { id: "FCO_REC", label: "FCO / Receita", formatType: "pct" },
  { id: "LIQ_CORR", label: "Liquidez Corrente", formatType: "ratio" },
] as const;

export const DETAIL_TABS = [
  { value: "visao-geral", label: "Visão Geral" },
  { value: "demonstracoes", label: "Demonstrações" },
] as const;

export const STATEMENT_OPTIONS = [
  { value: "DRE", label: "DRE" },
  { value: "BPA", label: "BPA" },
  { value: "BPP", label: "BPP" },
  { value: "DFC", label: "DFC" },
] as const;

export const STATEMENT_LABELS: Record<string, string> = {
  DRE: "Demonstração de Resultado",
  BPA: "Balanço Patrimonial Ativo",
  BPP: "Balanço Patrimonial Passivo",
  DFC: "Fluxo de Caixa",
};

const SUBTOTAL_MAP = {
  DRE: new Set(["3.01", "3.03", "3.05", "3.07", "3.11"]),
  BPA: new Set(["1", "1.01", "1.02"]),
  BPP: new Set(["2", "2.01", "2.02", "2.03"]),
  DFC: new Set(["6.01", "6.02", "6.03"]),
} as const;

export function isStatementSubtotal(
  statementType: string,
  accountCode: string | null | undefined,
): boolean {
  if (!accountCode) {
    return false;
  }

  return SUBTOTAL_MAP[statementType as keyof typeof SUBTOTAL_MAP]?.has(accountCode) ?? false;
}
