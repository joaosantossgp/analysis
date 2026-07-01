import { describe, expect, it } from "vitest";

import type { EntityWorkspaceSummary, PortfolioRow } from "./entityWorkspace";

import {
  ENERGY_DEEP_DIVE_STEPS,
  buildEnergyPortfolioSnapshot,
  getTopGenerationPortfolioRows,
} from "./energyDeepDive";

const summary: EntityWorkspaceSummary = {
  totalAssets: 8,
  mappedAssets: 6,
  unmappedAssets: 2,
  autoLinks: 4,
  manualLinks: 2,
  customOwnerLinks: 1,
  linkedCompanies: 3,
  listedPortfolios: 2,
  customPortfolios: 1,
  distributorCoverage: "2 / 3",
  plantCoverage: "4 / 5",
};

const rows: PortfolioRow[] = [
  {
    ownerKey: "cvm:1001",
    companyName: "Distribution Heavy",
    isListed: true,
    cdCvm: 1001,
    ticker: "DIST3",
    cnpj: null,
    setorCvm: "Energy",
    gicsSector: "Utilities",
    distributorsCount: 4,
    plantsCount: 0,
    totalAssets: 4,
    totalCapacityMw: 0,
    totalGenerationMwmed: 0,
    manualLinks: 1,
    autoLinks: 3,
    customOwnerLinks: 0,
  },
  {
    ownerKey: "cvm:2002",
    companyName: "Generation Leader",
    isListed: true,
    cdCvm: 2002,
    ticker: "GENE3",
    cnpj: null,
    setorCvm: "Energy",
    gicsSector: "Utilities",
    distributorsCount: 0,
    plantsCount: 3,
    totalAssets: 3,
    totalCapacityMw: 900,
    totalGenerationMwmed: 300,
    manualLinks: 1,
    autoLinks: 2,
    customOwnerLinks: 0,
  },
  {
    ownerKey: "custom:Private Owner",
    companyName: "Private Owner",
    isListed: false,
    cdCvm: null,
    ticker: null,
    cnpj: null,
    setorCvm: null,
    gicsSector: null,
    distributorsCount: 0,
    plantsCount: 1,
    totalAssets: 1,
    totalCapacityMw: 50,
    totalGenerationMwmed: 10,
    manualLinks: 1,
    autoLinks: 0,
    customOwnerLinks: 1,
  },
];

describe("energy deep-dive helpers", () => {
  it("defines the analyst path from sector context to verified outputs", () => {
    expect(ENERGY_DEEP_DIVE_STEPS.map((step) => step.id)).toEqual([
      "sector-context",
      "company-portfolios",
      "asset-review",
      "source-verification",
      "indicator-exports",
    ]);
  });

  it("summarizes mapped Energy portfolios without inventing confidence", () => {
    expect(buildEnergyPortfolioSnapshot(summary, rows)).toEqual({
      mappedAssetLabel: "6 / 8",
      portfolioLabel: "2 listed · 1 custom",
      generationCoverage: "4 / 5",
      distributionCoverage: "2 / 3",
      unresolvedLabel: "2 need review",
      largestGenerationPortfolio: "Generation Leader",
      confidenceLabel: "Confidence not recorded",
    });
  });

  it("prioritizes generation portfolios by plants, capacity and name", () => {
    expect(getTopGenerationPortfolioRows(rows, 2).map((row) => row.companyName)).toEqual([
      "Generation Leader",
      "Private Owner",
    ]);
  });
});
