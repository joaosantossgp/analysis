import { describe, expect, it } from "vitest";
import { QueryClient } from "@tanstack/react-query";

import {
  COMPANY_COMMAND_LABELS,
  companyDataInvalidationKeys,
  getCompanyCommandWorkspaceLinks,
  historyPresetRange,
  historyPopoverStyle,
  loadOnDemandUpdateSources,
  selectedOnDemandRefreshSources,
  shouldShowRefreshOutcome,
  updateSourcesEnabled,
} from "./CompanyCommandBar";

type InvalidationKeys = (cdCvm: number) => Array<readonly unknown[]>;

function getInvalidationKeys(): InvalidationKeys {
  return companyDataInvalidationKeys as InvalidationKeys;
}

describe("Company Command Bar query invalidation", () => {
  it("refreshes statement evidence discovery after a company import", async () => {
    const client = new QueryClient();
    const key = ["company-statement-years", 9512, "DFC"];
    client.setQueryData(key, { mode: "desktop", years: [] });
    for (const queryKey of getInvalidationKeys()(9512)) {
      await client.invalidateQueries({ queryKey });
    }
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    client.clear();
  });

  it("invalidates financial readiness after the existing company refresh completes", () => {
    expect(getInvalidationKeys()(9512)).toContainEqual([
      "company-financial-readiness",
      9512,
    ]);
  });

  it("invalidates market history and its availability state after a market refresh", () => {
    expect(getInvalidationKeys()(9512)).toContainEqual(["market-history", 9512]);
    expect(getInvalidationKeys()(9512)).toContainEqual(["market-history-status", 9512]);
  });
});

describe("Company Command Bar transient feedback", () => {
  it("only shows a completed refresh message for a refresh initiated in the current view", () => {
    expect(shouldShowRefreshOutcome("job-1", "job-1", "success")).toBe(true);
    expect(shouldShowRefreshOutcome(null, "job-1", "success")).toBe(false);
    expect(shouldShowRefreshOutcome("job-1", "job-2", "success")).toBe(false);
  });
});

describe("Company Command Bar on-demand settings popover", () => {
  it("opens below the download card instead of into the page header", () => {
    expect(historyPopoverStyle.top).toBe("calc(100% + 8px)");
    expect(historyPopoverStyle.bottom).toBeUndefined();
  });
});

describe("Company Command Bar action contract", () => {
  it("defaults on-demand updates to both financial and market sources", () => {
    expect(loadOnDemandUpdateSources(null)).toEqual({ cvm: true, market: true });
    expect(updateSourcesEnabled({ cvm: true, market: false })).toBe(true);
    expect(updateSourcesEnabled({ cvm: false, market: false })).toBe(false);
  });

  it("uses only the sources selected for an on-demand update", () => {
    expect(selectedOnDemandRefreshSources({ cvm: true, market: true })).toEqual(["cvm", "market"]);
    expect(selectedOnDemandRefreshSources({ cvm: false, market: true })).toEqual(["market"]);
    expect(selectedOnDemandRefreshSources({ cvm: false, market: false })).toEqual([]);
  });

  it("turns the five-year history preset into an inclusive download range", () => {
    expect(historyPresetRange("last_5_years", 2026)).toEqual({
      startYear: 2022,
      endYear: 2026,
    });
  });

  it("uses an explicit label for the history download disclosure", () => {
    expect(COMPANY_COMMAND_LABELS.historyDisclosure).toBe("History range");
    expect(Object.values(COMPANY_COMMAND_LABELS)).not.toContain("Export scope");
    expect(Object.values(COMPANY_COMMAND_LABELS)).not.toContain("More");
  });

  it("keeps Excel Mapping out of the Overview workspace links", () => {
    expect(getCompanyCommandWorkspaceLinks(9512)).toEqual([
      { label: "Statements", to: "/empresas/9512/demonstrativos" },
    ]);
  });

  it("exposes a native Excel Mapping window launcher label", () => {
    expect(COMPANY_COMMAND_LABELS.excelMappingWindow).toBe(
      "Open Excel Mapping in a separate window",
    );
  });
});
