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

describe("EntityHeader period coverage", () => {
  it("summarizes a partial current year in quarters beside the available-year count", () => {
    expect(formatCompanyPeriodCoverage("2Q26", 9)).toBe("2Q26 · 9Y · 38Q");
  });
});
