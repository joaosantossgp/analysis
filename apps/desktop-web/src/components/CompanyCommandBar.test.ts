import { describe, expect, it } from "vitest";

import {
  COMPANY_COMMAND_LABELS,
  companyDataInvalidationKeys,
  getCompanyCommandWorkspaceLinks,
} from "./CompanyCommandBar";

type InvalidationKeys = (cdCvm: number) => Array<readonly unknown[]>;

function getInvalidationKeys(): InvalidationKeys {
  return companyDataInvalidationKeys as InvalidationKeys;
}

describe("Company Command Bar query invalidation", () => {
  it("invalidates financial readiness after the existing company refresh completes", () => {
    expect(getInvalidationKeys()(9512)).toContainEqual([
      "company-financial-readiness",
      9512,
    ]);
  });
});

describe("Company Command Bar action contract", () => {
  it("uses explicit labels for history download and export scope controls", () => {
    expect(COMPANY_COMMAND_LABELS.historyDisclosure).toBe("History range");
    expect(COMPANY_COMMAND_LABELS.exportScope).toBe("Export scope");
    expect(Object.values(COMPANY_COMMAND_LABELS)).not.toContain("More");
  });

  it("links from Overview to implemented company workflow surfaces", () => {
    expect(getCompanyCommandWorkspaceLinks(9512)).toEqual([
      { label: "Statements", to: "/empresas/9512/demonstrativos" },
      { label: "Excel mapping", to: "/empresas/9512/model-mapping" },
    ]);
  });
});
