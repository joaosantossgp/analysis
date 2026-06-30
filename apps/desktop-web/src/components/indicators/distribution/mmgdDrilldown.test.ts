import { describe, expect, it } from "vitest";

import { resolveMmgdDetailMonth, resolveMmgdPageOffset } from "./mmgdDrilldown";

describe("MMGD drill-down helpers", () => {
  it("keeps the selected month when it still has MMGD data", () => {
    const month = resolveMmgdDetailMonth(
      [
        { period: "2026-05", mmgd_projects_count: 10 },
        { period: "2026-06", mmgd_projects_count: 20 },
      ],
      "2026-05",
    );

    expect(month).toBe("2026-05");
  });

  it("chooses the latest month with MMGD projects when selection is missing", () => {
    const month = resolveMmgdDetailMonth(
      [
        { period: "2026-04", mmgd_projects_count: null },
        { period: "2026-05", mmgd_projects_count: 10 },
        { period: "2026-06", mmgd_projects_count: 20 },
      ],
      null,
    );

    expect(month).toBe("2026-06");
  });

  it("clamps the page offset to available rows", () => {
    expect(resolveMmgdPageOffset({ requestedOffset: 150, limit: 50, totalRows: 120 })).toBe(100);
    expect(resolveMmgdPageOffset({ requestedOffset: -10, limit: 50, totalRows: 120 })).toBe(0);
  });
});
