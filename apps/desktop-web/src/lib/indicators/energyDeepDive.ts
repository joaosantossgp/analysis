import type { EntityWorkspaceSummary, PortfolioRow } from "./entityWorkspace";

export type EnergyDeepDiveStep = {
  id: string;
  title: string;
  description: string;
  target: "overview" | "distribution" | "generation" | "fuel" | "sin" | "matrix" | "entities" | "exports";
};

export type EnergyPortfolioSnapshot = {
  mappedAssetLabel: string;
  portfolioLabel: string;
  generationCoverage: string;
  distributionCoverage: string;
  unresolvedLabel: string;
  largestGenerationPortfolio: string;
  confidenceLabel: string;
};

export const ENERGY_DEEP_DIVE_STEPS: EnergyDeepDiveStep[] = [
  {
    id: "sector-context",
    title: "Sector context",
    description: "Start from distribution, generation, fuel, SIN and matrix views.",
    target: "overview",
  },
  {
    id: "company-portfolios",
    title: "Company portfolios",
    description: "Review linked distributors and generation assets by CVM company or custom owner.",
    target: "entities",
  },
  {
    id: "asset-review",
    title: "Asset review",
    description: "Inspect mapped plants, distributors and unresolved ownership links.",
    target: "generation",
  },
  {
    id: "source-verification",
    title: "Source verification",
    description: "Check snapshots, source status, refresh logs and partial source warnings.",
    target: "exports",
  },
  {
    id: "indicator-exports",
    title: "Indicator outputs",
    description: "Move from verified source data into Indicator Library and export-ready views.",
    target: "matrix",
  },
];

export function buildEnergyPortfolioSnapshot(
  summary: EntityWorkspaceSummary,
  rows: PortfolioRow[],
): EnergyPortfolioSnapshot {
  const generationLeader = getTopGenerationPortfolioRows(rows, 1)[0];

  return {
    mappedAssetLabel: `${summary.mappedAssets} / ${summary.totalAssets}`,
    portfolioLabel: `${summary.listedPortfolios} listed · ${summary.customPortfolios} custom`,
    generationCoverage: summary.plantCoverage,
    distributionCoverage: summary.distributorCoverage,
    unresolvedLabel:
      summary.unmappedAssets === 1
        ? "1 needs review"
        : `${summary.unmappedAssets} need review`,
    largestGenerationPortfolio: generationLeader?.companyName ?? "—",
    confidenceLabel: "Confidence not recorded",
  };
}

export function getTopGenerationPortfolioRows(
  rows: PortfolioRow[],
  limit = 5,
): PortfolioRow[] {
  return [...rows]
    .filter((row) => row.plantsCount > 0)
    .sort((a, b) => {
      if (b.plantsCount !== a.plantsCount) return b.plantsCount - a.plantsCount;
      if (b.totalCapacityMw !== a.totalCapacityMw) return b.totalCapacityMw - a.totalCapacityMw;
      if (b.totalGenerationMwmed !== a.totalGenerationMwmed) {
        return b.totalGenerationMwmed - a.totalGenerationMwmed;
      }
      return a.companyName.localeCompare(b.companyName);
    })
    .slice(0, limit);
}
