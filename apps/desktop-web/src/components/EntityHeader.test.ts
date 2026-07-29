import { describe, expect, it } from "vitest";

import { getCompanyHeaderClassificationBadges } from "./EntityHeader";

describe("EntityHeader classification badges", () => {
  it("uses the first two visible GICS levels in the company header", () => {
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

    expect(badges.map((badge) => badge.value)).toEqual(["—", "—"]);
    expect(badges.map((badge) => badge.value)).not.toContain("Financeiro");
    expect(badges.map((badge) => badge.value)).not.toContain("Banks");
  });
});
