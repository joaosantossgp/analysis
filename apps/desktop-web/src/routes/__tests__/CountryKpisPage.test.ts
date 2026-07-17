import { describe, expect, it } from "vitest";

import {
  EMPTY_INDICATOR_LIBRARY_FILTERS,
  INDICATOR_LIBRARY_STATIC_ROWS,
  buildIndicatorLibraryRows,
  collectIndicatorLibraryFacets,
  filterIndicatorLibraryRows,
  resolveIndicatorLibrarySelection,
} from "@/lib/indicators/indicatorLibrary";
import type { IndicatorRecord } from "@/lib/indicators/registry";

import {
  ENERGY_SUB_NAV,
  EXPORT_VERIFICATION_WORKFLOWS,
  TOP_NAV,
  parseEnergySub,
  parseSection,
} from "../CountryKpisPage";
import {
  DEFAULT_LIBRARY_PANEL_WIDTH,
  MAX_LIBRARY_PANEL_WIDTH,
  MIN_LIBRARY_PANEL_WIDTH,
  calculateLibraryPanelDragWidth,
  calculateLibraryPanelViewportBounds,
  clampLibraryPanelWidth,
} from "@/lib/indicators/libraryPanelLayout";

describe("CountryKpisPage indicators navigation", () => {
  it("exposes analyst-oriented top-level sections without a generic Workspace tab", () => {
    expect(TOP_NAV.map((item) => item.label)).toEqual([
      "Indicator Library",
      "Sectors",
      "Companies & Assets",
      "Data Health & Sources",
      "Exports & Verification",
    ]);
  });

  it("keeps existing Energy workflows reachable", () => {
    expect(ENERGY_SUB_NAV.map((item) => item.label)).toEqual([
      "Distribution",
      "Generation",
      "Fuel",
      "Power System",
      "Matrix & Trends",
    ]);
  });

  it("uses the Indicator Library as a direct non-entity indicator list", () => {
    const rows = buildIndicatorLibraryRows([]);
    const ids = rows.map((row) => row.id);

    expect(ids).toContain("catalog.energy_utilities.sin.load_mwmed");
    expect(ids).toContain("catalog.energy_utilities.country.elec_renewables_share");
    expect(ids).not.toContain("financial.MG_EBITDA");
    expect(ids).not.toContain("distribution.billed_energy_mwh");
    expect(ids).not.toContain("distribution.dec_actual");
    expect(ids).not.toContain("fuel.sales_volume");
    expect(ids).not.toContain("generation.capacity_mw");
    expect(ids).not.toContain("energy-generation");

    expect(rows.every((row) => row.requiresEntityContext === false)).toBe(true);
    expect(INDICATOR_LIBRARY_STATIC_ROWS.every((row) => row.requiresEntityContext === false)).toBe(true);
  });

  it("keeps export kinds honest by available workflow", () => {
    const records: IndicatorRecord[] = [
      makeIndicatorRecord("energy_utilities.country.elec_renewables_share", "energy_country"),
      makeIndicatorRecord("energy_utilities.sin.load_mwmed", "sin"),
    ];
    const rows = buildIndicatorLibraryRows(records);

    expect(rows.find((row) => row.id === "catalog.energy_utilities.country.elec_renewables_share")?.exportKind).toBe(
      "country-kpi-excel",
    );
    expect(rows.find((row) => row.id === "catalog.energy_utilities.sin.load_mwmed")?.exportKind).toBe("none");
    expect(rows.find((row) => row.id === "distribution.billed_energy_mwh")).toBeUndefined();
    expect(rows.find((row) => row.id === "financial.MG_EBITDA")).toBeUndefined();
  });

  it("excludes entity-dependent indicators from library preview", () => {
    const rows = buildIndicatorLibraryRows([]);
    const billedEnergy = rows.find((row) => row.id === "distribution.billed_energy_mwh");
    const decActual = rows.find((row) => row.id === "distribution.dec_actual");
    const financial = rows.find((row) => row.id === "financial.MG_EBITDA");
    const generation = rows.find((row) => row.id === "generation.capacity_mw");
    const fuel = rows.find((row) => row.id === "fuel.sales_volume");

    expect(billedEnergy).toBeUndefined();
    expect(decActual).toBeUndefined();
    expect(financial).toBeUndefined();
    expect(generation).toBeUndefined();
    expect(fuel).toBeUndefined();
  });

  it("closes the library detail when the selected row is clicked again", () => {
    const rows = buildIndicatorLibraryRows([]);
    const first = rows[0]!.id;
    const second = rows[1]!.id;

    expect(resolveIndicatorLibrarySelection(null, first)).toBe(first);
    expect(resolveIndicatorLibrarySelection(first, first)).toBeNull();
    expect(resolveIndicatorLibrarySelection(first, second)).toBe(second);
  });

  it("builds library facets and filters without hiding the full library model", () => {
    const rows = buildIndicatorLibraryRows([
      makeIndicatorRecord("energy_utilities.country.elec_renewables_share", "energy_country"),
    ]);
    const facets = collectIndicatorLibraryFacets(rows);

    expect(facets.domains.map((facet) => facet.label)).not.toContain("Financials");
    expect(facets.sources.map((facet) => facet.label)).not.toContain("CVM statements");
    expect(facets.units.map((facet) => facet.label)).toContain("%");
    expect(facets.valueTypes.map((facet) => facet.label)).toContain("Reported / imported");
    expect(facets.statuses.map((facet) => facet.label)).toContain("Definition");

    const filtered = filterIndicatorLibraryRows(rows, {
      search: "MG_EBITDA",
      filters: EMPTY_INDICATOR_LIBRARY_FILTERS,
      favoritesOnly: false,
      isFavorite: () => false,
    });
    expect(filtered).toEqual([]);
  });

  it("keeps legacy query values compatible with the reorganized IA", () => {
    expect(parseSection(null)).toBe("library");
    expect(parseSection("overview")).toBe("library");
    expect(parseSection("discover")).toBe("entities");
    expect(parseSection("energy")).toBe("energy");
    expect(parseSection("favorites")).toBe("library");
    expect(parseSection("health")).toBe("health");
    expect(parseSection("exports")).toBe("exports");
    expect(parseSection("unknown")).toBe("library");

    expect(parseEnergySub(null)).toBe("distribution");
    expect(parseEnergySub("overview")).toBe("distribution");
    expect(parseEnergySub("generation")).toBe("generation");
    expect(parseEnergySub("unknown")).toBe("distribution");
  });

  it("documents real export and verification workflows without fake centralized exports", () => {
    expect(EXPORT_VERIFICATION_WORKFLOWS.map((workflow) => workflow.id)).toEqual([
      "distribution-excel",
      "country-kpi-excel",
      "generation-source-review",
      "sin-source-review",
      "fuel-detail-review",
      "mapping-review-notes",
    ]);

    expect(
      EXPORT_VERIFICATION_WORKFLOWS.filter((workflow) => workflow.status === "available").map(
        (workflow) => workflow.id,
      ),
    ).toEqual(["distribution-excel", "country-kpi-excel"]);

    expect(
      EXPORT_VERIFICATION_WORKFLOWS.filter((workflow) => workflow.status === "source-review").map(
        (workflow) => workflow.id,
      ),
    ).toEqual(["generation-source-review", "sin-source-review", "fuel-detail-review"]);
  });

  it("keeps the library detail panel resizable within usable bounds", () => {
    expect(DEFAULT_LIBRARY_PANEL_WIDTH).toBe(420);
    expect(clampLibraryPanelWidth(100)).toBe(MIN_LIBRARY_PANEL_WIDTH);
    expect(clampLibraryPanelWidth(9999)).toBe(MAX_LIBRARY_PANEL_WIDTH);
    expect(calculateLibraryPanelDragWidth({ startWidth: 420, startX: 900, currentX: 820 })).toBe(500);
    expect(calculateLibraryPanelDragWidth({ startWidth: 420, startX: 900, currentX: 960 })).toBe(360);
  });

  it("bounds the library detail panel to the indicator table and content margin", () => {
    expect(
      calculateLibraryPanelViewportBounds({
        viewportWidth: 2048,
        viewportHeight: 900,
        contentRect: { right: 2032 },
        mainRect: { top: 68, bottom: 876 },
        tableRect: { top: 121, bottom: 862 },
      }),
    ).toEqual({ top: 121, right: 16, bottom: 40 });

    expect(
      calculateLibraryPanelViewportBounds({
        viewportWidth: 2048,
        viewportHeight: 900,
        contentRect: { right: 2032 },
        mainRect: { top: 68, bottom: 876 },
        tableRect: { top: -515, bottom: 862 },
      }),
    ).toEqual({ top: 84, right: 16, bottom: 40 });
  });
});

function makeIndicatorRecord(id: string, sourceGroup: "energy_country" | "sin"): IndicatorRecord {
  return {
    id,
    name: id.includes("country") ? "Renewable Share of Electricity" : "Load",
    description: "Catalog indicator description.",
    theme: "Demand",
    themeKey: "demand",
    sourceGroup,
    sourceLabel: sourceGroup === "sin" ? "ONS" : "OWID / Ember",
    primarySource: sourceGroup === "sin" ? "ONS" : "OWID",
    geography: sourceGroup === "sin" ? "Brazil — SIN subsystems" : "Country (cross-country)",
    geographyKey: sourceGroup === "sin" ? "sin" : "country",
    frequency: sourceGroup === "sin" ? "Daily / intraday" : "Annual",
    frequencyKey: sourceGroup === "sin" ? "daily" : "annual",
    unit: "%",
    chartUnit: "pct",
    valueType: "raw",
    calculationMethod: "direct",
    status: "cached",
    lastRefreshAt: "2026-01-02T03:04:05",
    latestValue: 82.4,
    latestValueLabel: "Brazil",
    latestReferenceDate: "2025",
    coverageStart: "2000",
    coverageEnd: "2025",
    methodology: "direct",
    caveats: "",
    auditNotes: "",
    verificationStatus: "verified",
    higherIsBetter: true,
    dashboardPriority: "high",
    dataQuality: "ok",
    relatedIds: [],
  };
}
