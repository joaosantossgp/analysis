import { describe, expect, it } from "vitest";

import { filterGicsOptions } from "@/lib/api/classification";
import type { GicsSubIndustry } from "@/lib/bridge/types";
import { getCompanyHeaderClassificationBadges } from "./EntityHeader";
import { curatedChangeNotice } from "./ClassificationEditor";

const option = (code: string, sub: string, industry: string, sector: string): GicsSubIndustry => ({
  sector_code: code.slice(0, 2),
  sector,
  industry_group_code: code.slice(0, 4),
  industry_group: sector,
  industry_code: code.slice(0, 6),
  industry,
  sub_industry_code: code,
  sub_industry: sub,
  gics_version: "v",
});

const OPTIONS = [
  option("10102010", "Integrated Oil & Gas", "Oil, Gas & Consumable Fuels", "Energy"),
  option("55101010", "Electric Utilities", "Electric Utilities", "Utilities"),
  option("55105020", "Renewable Electricity", "Independent Power and Renewable Electricity Producers", "Utilities"),
];

describe("GICS option search", () => {
  it("matches every term across levels and codes", () => {
    expect(filterGicsOptions(OPTIONS, "utilities renew").map((o) => o.sub_industry_code)).toEqual(["55105020"]);
    expect(filterGicsOptions(OPTIONS, "10102010").map((o) => o.sub_industry)).toEqual(["Integrated Oil & Gas"]);
    expect(filterGicsOptions(OPTIONS, "", 2)).toHaveLength(2);
  });
});

describe("local classification edits", () => {
  const edited = {
    origin: "user" as const,
    official: false as const,
    gics_sub_industry_code: "55105020",
    user_edit: {
      edited_at: "2026-11-24T00:00:00+00:00",
      curated_sub_industry_code: "55101010",
      curated_sub_industry: "Electric Utilities",
      curated_changed_since_edit: true,
    },
  };

  it("tells the analyst when curation moved after their edit", () => {
    expect(curatedChangeNotice(edited)).toBe(
      "The curated classification changed to Electric Utilities (55101010) since your edit.",
    );
    expect(curatedChangeNotice({ ...edited, user_edit: { ...edited.user_edit, curated_changed_since_edit: false } })).toBeNull();
  });

  it("labels an edited sub-industry as the analyst's own, with the curated value", () => {
    const sub = getCompanyHeaderClassificationBadges({
      gics_sector: "Utilities",
      gics_industry_group: "Utilities",
      gics_industry: "Independent Power and Renewable Electricity Producers",
      gics_sub_industry: "Renewable Electricity",
      sector_name: null,
      setor_cvm: null,
      classification: edited,
    })[3];
    expect(sub.title).toContain("edited by you");
    expect(sub.title).toContain("Electric Utilities (55101010)");
  });
});
