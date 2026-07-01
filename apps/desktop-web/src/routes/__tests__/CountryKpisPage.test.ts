import { describe, expect, it } from "vitest";

import {
  ENERGY_SUB_NAV,
  EXPORT_VERIFICATION_WORKFLOWS,
  TOP_NAV,
  WORKSPACE_OVERVIEW_AREAS,
  parseEnergySub,
  parseSection,
} from "../CountryKpisPage";

describe("CountryKpisPage indicators workspace navigation", () => {
  it("exposes analyst-oriented top-level workspace sections", () => {
    expect(TOP_NAV.map((item) => item.label)).toEqual([
      "Workspace",
      "Sectors",
      "Companies & Assets",
      "Indicator Library",
      "Data Health & Sources",
      "Exports & Verification",
    ]);
  });

  it("keeps existing Energy workflows reachable", () => {
    expect(ENERGY_SUB_NAV.map((item) => item.label)).toEqual([
      "Overview",
      "Distribution",
      "Generation",
      "Fuel",
      "Power System",
      "Matrix & Trends",
    ]);
  });

  it("keeps legacy query values compatible with the reorganized IA", () => {
    expect(parseSection(null)).toBe("overview");
    expect(parseSection("discover")).toBe("entities");
    expect(parseSection("energy")).toBe("energy");
    expect(parseSection("favorites")).toBe("library");
    expect(parseSection("health")).toBe("health");
    expect(parseSection("exports")).toBe("exports");
    expect(parseSection("unknown")).toBe("overview");

    expect(parseEnergySub(null)).toBe("overview");
    expect(parseEnergySub("generation")).toBe("generation");
    expect(parseEnergySub("unknown")).toBe("overview");
  });

  it("keeps the landing page focused on available workflows and honest planned areas", () => {
    expect(WORKSPACE_OVERVIEW_AREAS.map((area) => area.id)).toEqual([
      "energy",
      "entities",
      "library",
      "health",
      "exports",
    ]);
    expect(WORKSPACE_OVERVIEW_AREAS.find((area) => area.id === "exports")?.status).toBe(
      "partial",
    );
    expect(WORKSPACE_OVERVIEW_AREAS.find((area) => area.id === "exports")?.section).toBe(
      "exports",
    );
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
});
