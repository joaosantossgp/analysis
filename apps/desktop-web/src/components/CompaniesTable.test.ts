import { describe, expect, it } from "vitest";

import {
  COMPANY_DIRECTORY_COLUMNS,
  getNextCompanyDirectorySort,
  getCompanyDirectoryIndustryGroupLabel,
  getCompanyDirectoryRoute,
  getCompanyDirectorySectorLabel,
} from "./CompaniesTable";

describe("Companies directory table contract", () => {
  it("keeps the directory as a company-selection index without coverage actions or rows column", () => {
    const labels = COMPANY_DIRECTORY_COLUMNS.map((column) => column.label);

    expect(labels).toEqual([
      "Company",
      "Ticker",
      "Sector",
      "Industry Group",
      "Mkt Cap",
      "Data",
      "Years",
      "CVM",
    ]);
    expect(labels).not.toContain("Rows");
    expect(labels).not.toContain("Coverage");
    expect(labels).not.toContain("Sub-industry");
  });

  it("opens companies through the company workspace route", () => {
    expect(getCompanyDirectoryRoute(9512)).toBe("/empresas/9512");
  });

  it("shows only GICS sector and industry group labels in the directory", () => {
    expect(
      getCompanyDirectorySectorLabel({
        gics_sector: "Energy",
        sector_name: "Petróleo, Gás e Biocombustíveis",
      }),
    ).toBe("Energy");
    expect(
      getCompanyDirectoryIndustryGroupLabel({
        gics_industry_group: "Energy",
        gics_sub_industry: "Integrated Oil & Gas",
      }),
    ).toBe("Energy");
  });

  it("makes pending and unclassifiable companies explicit in the sector column", () => {
    expect(getCompanyDirectorySectorLabel({ gics_sector: null, classification_origin: "pending" })).toBe("Pending");
    expect(getCompanyDirectorySectorLabel({ gics_sector: null, classification_origin: "unclassified" })).toBe(
      "Not classifiable",
    );
  });

  it("does not fall back to CVM sector labels when GICS classification is missing", () => {
    expect(
      getCompanyDirectorySectorLabel({
        gics_sector: null,
        sector_name: "Financeiro",
      }),
    ).toBe("—");
    expect(
      getCompanyDirectoryIndustryGroupLabel({
        gics_industry_group: null,
        gics_sub_industry: "Banks",
      }),
    ).toBe("—");
  });

  it("toggles a selected directory column between ascending and descending order", () => {
    expect(getNextCompanyDirectorySort(null, "company")).toEqual({
      sortBy: "company",
      sortDirection: "asc",
    });
    expect(getNextCompanyDirectorySort({ sortBy: "company", sortDirection: "asc" }, "company")).toEqual({
      sortBy: "company",
      sortDirection: "desc",
    });
  });
});
