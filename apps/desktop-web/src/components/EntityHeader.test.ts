import { describe, expect, it } from "vitest";

import {
  formatCompanyPeriodCoverage,
  getCompanyHeaderClassificationBadges,
} from "./EntityHeader";

describe("EntityHeader classification badges", () => {
  it("uses all four official GICS levels in the company header", () => {
    const badges = getCompanyHeaderClassificationBadges({
      gics_sector: "Energy",
      gics_industry_group: "Energy",
      gics_industry: "Oil, Gas & Consumable Fuels",
      gics_sub_industry: "Integrated Oil & Gas",
      sector_name: "Petroleo e Gas",
      setor_cvm: "Petroleo e Gas",
    });

    expect(badges.map((badge) => [badge.label, badge.value])).toEqual([
      ["Sector", "Energy"],
      ["Industry Group", "Energy"],
      ["Industry", "Oil, Gas & Consumable Fuels"],
      ["Sub-industry", "Integrated Oil & Gas"],
    ]);
  });

  it("does not fall back to CVM sector or lower GICS levels when the visible GICS levels are missing", () => {
    const badges = getCompanyHeaderClassificationBadges({
      gics_sector: null,
      gics_industry_group: null,
      gics_industry: "Banks",
      gics_sub_industry: "Diversified Banks",
      sector_name: "Financeiro",
      setor_cvm: "Financeiro",
    });

    expect(badges.map((badge) => badge.value)).toEqual(["—", "—", "Banks", "Diversified Banks"]);
    expect(badges.map((badge) => badge.value)).not.toContain("Financeiro");
  });
});

describe("EntityHeader canonical classification", () => {
  const base = {
    gics_sector: null,
    gics_industry_group: null,
    gics_industry: null,
    gics_sub_industry: null,
    sector_name: "Energia Eletrica",
    setor_cvm: "Energia Eletrica",
  };

  it("shows pending explicitly instead of a guess from the CVM sector", () => {
    const [sector] = getCompanyHeaderClassificationBadges({
      ...base,
      classification: { origin: "pending", official: false },
    });
    expect(sector.value).toBe("Pending");
    expect(sector.title).toContain("curation pending");
  });

  it("shows why a company is not classifiable", () => {
    const [sector] = getCompanyHeaderClassificationBadges({
      ...base,
      classification: { origin: "unclassified", official: false, unclassified_reason: "pre-operational SPAC" },
    });
    expect(sector.value).toBe("Not classifiable");
    expect(sector.title).toContain("pre-operational SPAC");
  });

  it("labels a curated sub-industry as not official and keeps its evidence", () => {
    const badges = getCompanyHeaderClassificationBadges({
      ...base,
      gics_sector: "Utilities",
      gics_industry_group: "Utilities",
      gics_industry: "Electric Utilities",
      gics_sub_industry: "Electric Utilities",
      classification: {
        origin: "curated",
        official: false,
        sub_industry_code: "55101010",
        confidence: "medium",
        rationale: "Transmission concession.",
        evidence_url: "https://ri.example",
      },
    });
    const sub = badges[3];
    expect(sub.value).toBe("Electric Utilities");
    expect(sub.title).toContain("not an official MSCI/S&P classification");
    expect(sub.title).toContain("Confidence: medium");
    expect(sub.title).toContain("https://ri.example");
  });
});

describe("EntityHeader period coverage", () => {
  it("summarizes a partial current year in quarters beside the available-year count", () => {
    expect(formatCompanyPeriodCoverage("2Q26", 9)).toBe("2Q26 · 9Y · 38Q");
  });
});
