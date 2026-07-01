import { describe, expect, it } from "vitest";

import { getSettingsNavSection, SETTINGS_NAV_ITEMS } from "../SettingsModule";

describe("SettingsModule navigation", () => {
  it("exposes the six user-facing Settings sections", () => {
    expect(SETTINGS_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Overview",
      "Data",
      "Sources",
      "Storage",
      "App",
      "Advanced",
    ]);
  });

  it("keeps legacy Settings routes attached to their new sections", () => {
    expect(getSettingsNavSection("overview")).toBe("overview");
    expect(getSettingsNavSection("health")).toBe("data");
    expect(getSettingsNavSection("coverage")).toBe("data");
    expect(getSettingsNavSection("updates")).toBe("data");
    expect(getSettingsNavSection("sources")).toBe("sources");
    expect(getSettingsNavSection("imports")).toBe("sources");
    expect(getSettingsNavSection("storage")).toBe("storage");
    expect(getSettingsNavSection("diagnostics")).toBe("advanced");
  });
});
