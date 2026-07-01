import { describe, expect, it } from "vitest";

import type {
  AssetMappingEntry,
  ConglomerateEntry,
  CvmRegistryEntry,
} from "@/lib/bridge/types";

import {
  buildPortfolioRows,
  getAssetMappingReviewState,
  summarizeEntityWorkspace,
} from "./entityWorkspace";

const assets: AssetMappingEntry[] = [
  {
    id: "dist-1",
    type: "distributor",
    name: "CPFL Paulista",
    sub_name: "SP",
    mapped_cvm: 1001,
    custom_owner_name: null,
    company_name: "CPFL Energia",
    ticker: "CPFE3",
    mapping_source: "auto",
    review_notes: null,
    stats: "12 periods",
  },
  {
    id: "plant-1",
    type: "plant",
    name: "UHE Example",
    sub_name: "SE/CO",
    mapped_cvm: 1001,
    custom_owner_name: null,
    company_name: "CPFL Energia",
    ticker: "CPFE3",
    mapping_source: "manual",
    review_notes: "Confirmed from company asset list.",
    stats: "100 MW",
  },
  {
    id: "plant-2",
    type: "plant",
    name: "Private Plant",
    sub_name: "NE",
    mapped_cvm: null,
    custom_owner_name: "Private Owner",
    company_name: "Private Owner",
    ticker: "",
    mapping_source: "manual",
    review_notes: null,
    stats: "50 MW",
  },
  {
    id: "plant-3",
    type: "plant",
    name: "Unknown Plant",
    sub_name: "N",
    mapped_cvm: null,
    custom_owner_name: null,
    company_name: "",
    ticker: "",
    mapping_source: "unmapped",
    review_notes: null,
    stats: "No owner",
  },
];

const companies: CvmRegistryEntry[] = [
  {
    cd_cvm: 1001,
    company_name: "CPFL Energia",
    ticker_b3: "CPFE3",
    cnpj: "00000000000100",
    setor_cvm: "Energy",
    gics_sector: "Utilities",
    has_financials: true,
    mapped_distributors: 1,
    mapped_plants: 1,
    total_capacity_mw: 100,
  },
  {
    cd_cvm: 2002,
    company_name: "Unlinked Company",
    ticker_b3: "UNLK3",
    cnpj: null,
    setor_cvm: "Energy",
    gics_sector: "Utilities",
    has_financials: true,
    mapped_distributors: 0,
    mapped_plants: 0,
    total_capacity_mw: 0,
  },
];

const conglomerates: ConglomerateEntry[] = [
  {
    cd_cvm: 1001,
    company_name: "CPFL Energia",
    ticker_b3: "CPFE3",
    cnpj: "00000000000100",
    setor_cvm: "Energy",
    gics_sector: "Utilities",
    distributors_count: 1,
    plants_count: 1,
    total_capacity_mw: 100,
    total_generation_mwmed: 20,
    is_listed: true,
  },
  {
    cd_cvm: null,
    company_name: "Private Owner",
    ticker_b3: null,
    cnpj: null,
    setor_cvm: null,
    gics_sector: null,
    distributors_count: 0,
    plants_count: 1,
    total_capacity_mw: 50,
    total_generation_mwmed: 10,
    is_listed: false,
  },
];

describe("entity workspace helpers", () => {
  it("summarizes portfolio and mapping review counts without inventing confidence", () => {
    expect(summarizeEntityWorkspace(assets, companies, conglomerates)).toEqual({
      totalAssets: 4,
      mappedAssets: 3,
      unmappedAssets: 1,
      autoLinks: 1,
      manualLinks: 2,
      customOwnerLinks: 1,
      linkedCompanies: 1,
      listedPortfolios: 1,
      customPortfolios: 1,
      distributorCoverage: "1 / 1",
      plantCoverage: "2 / 3",
    });
  });

  it("builds company portfolio rows with mapping-source mix", () => {
    expect(buildPortfolioRows(conglomerates, assets)).toEqual([
      expect.objectContaining({
        ownerKey: "cvm:1001",
        companyName: "CPFL Energia",
        totalAssets: 2,
        manualLinks: 1,
        autoLinks: 1,
        customOwnerLinks: 0,
      }),
      expect.objectContaining({
        ownerKey: "custom:Private Owner",
        companyName: "Private Owner",
        totalAssets: 1,
        manualLinks: 1,
        autoLinks: 0,
        customOwnerLinks: 1,
      }),
    ]);
  });

  it("labels manual, custom, auto and unresolved mapping states honestly", () => {
    expect(getAssetMappingReviewState(assets[0])).toEqual({
      label: "Auto linked",
      tone: "success",
      detail: "Inferred relationship; confidence is not recorded.",
      needsReview: false,
    });
    expect(getAssetMappingReviewState(assets[1])).toEqual({
      label: "Manual override",
      tone: "warning",
      detail: "Confirmed from company asset list.",
      needsReview: false,
    });
    expect(getAssetMappingReviewState(assets[2]).label).toBe("Custom owner");
    expect(getAssetMappingReviewState(assets[3])).toEqual({
      label: "Needs review",
      tone: "neutral",
      detail: "No company or custom owner is linked.",
      needsReview: true,
    });
  });
});
