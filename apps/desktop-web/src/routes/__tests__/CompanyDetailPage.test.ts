import { describe, expect, it } from "vitest";

import { selectedYearsForPreset } from "../CompanyDetailPage";

describe("selectedYearsForPreset", () => {
  it("expands Last 5 when additional downloaded years become available", () => {
    expect(selectedYearsForPreset([2025], "last5")).toEqual([2025]);
    expect(selectedYearsForPreset([2022, 2023, 2024, 2025], "last5")).toEqual([
      2022,
      2023,
      2024,
      2025,
    ]);
  });
});
