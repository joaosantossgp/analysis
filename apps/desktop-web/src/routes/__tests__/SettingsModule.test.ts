import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { subNavFor } from "@/components/shell/SubNav";
import type { SettingsHealthSegment, SettingsHealthSummary } from "@/lib/bridge/types";
import { SETTINGS_NAV_ITEMS, SETTINGS_REDIRECTS } from "@/lib/settingsNav";
import { getSettingsNavSection, historyRangeOf, historyRangeYears, SettingsOverview } from "../SettingsModule";

describe("Settings navigation", () => {
  it("exposes the six user-facing Settings sections", () => {
    expect(SETTINGS_NAV_ITEMS.map((item) => [item.label, item.to])).toEqual([
      ["Overview", "/settings"],
      ["Data", "/settings/data"],
      ["Sources", "/settings/sources"],
      ["Storage", "/settings/storage"],
      ["App", "/settings/app"],
      ["Advanced", "/settings/diagnostics"],
    ]);
  });

  it.each(["/settings", "/settings/data", "/settings/indicator-sources", "/settings/diagnostics"])(
    "shows the same six tabs in the sub-navigation on %s",
    (pathname) => {
      const tabs = subNavFor(pathname, {}, null);
      expect(tabs.map((tab) => [tab.label, tab.to])).toEqual(SETTINGS_NAV_ITEMS.map((item) => [item.label, item.to]));
    },
  );

  it("keeps imports and indicator sources inside Sources", () => {
    expect(getSettingsNavSection("data")).toBe("data");
    expect(getSettingsNavSection("sources")).toBe("sources");
    expect(getSettingsNavSection("imports")).toBe("sources");
    expect(getSettingsNavSection("indicator-sources")).toBe("sources");
    expect(getSettingsNavSection("diagnostics")).toBe("advanced");
  });

  it("redirects the retired update and coverage routes to the Data section", () => {
    for (const route of ["/settings/updates", "/atualizar-base", "/company-universe", "/settings/health", "/settings/coverage", "/data-coverage"]) {
      expect(SETTINGS_REDIRECTS[route]).toBe("/settings/data");
    }
    expect(SETTINGS_REDIRECTS["/status"]).toBe("/settings/diagnostics");
  });
});

describe("History range", () => {
  it("maps each preference to the years the data update fetches", () => {
    expect(historyRangeYears("3", 2026)).toEqual({ start_year: 2024, end_year: 2026 });
    expect(historyRangeYears("5", 2026)).toEqual({ start_year: 2022, end_year: 2026 });
    expect(historyRangeYears("10", 2026)).toEqual({ start_year: 2017, end_year: 2026 });
    expect(historyRangeYears("2010", 2026)).toEqual({ start_year: 2010, end_year: 2026 });
  });

  it("recognizes stored ranges and keeps unknown ones visible as custom", () => {
    expect(historyRangeOf({ start_year: 2022, end_year: 2026 }, 2026)).toBe("5");
    expect(historyRangeOf({ start_year: 2010, end_year: 2026 }, 2026)).toBe("2010");
    expect(historyRangeOf({ start_year: 2015, end_year: 2020 }, 2026)).toBe("custom");
  });
});

function segment(overrides: Partial<SettingsHealthSegment>): SettingsHealthSegment {
  return {
    id: "cvm_registry",
    name: "Companies and CVM Registry",
    required: true,
    status: "empty",
    reason: "No company registry rows were found.",
    owner: "cvm_financials.db",
    provider: "CVM/B3 metadata",
    record_count: 0,
    latest_reference: null,
    last_successful_update: null,
    last_attempted_update: null,
    dimensions: {},
    warnings: [],
    errors: [],
    action_route: "/",
    ...overrides,
  } as SettingsHealthSegment;
}

function renderOverview(segments: SettingsHealthSegment[]) {
  const summary = {
    generated_at: "2026-11-25T00:00:00Z",
    overall_status: "empty",
    summary: { title: "Local data", message: "" , critical_segments: 0, degraded_segments: 0, empty_segments: 2, updating_segments: 0 },
    segments, active_jobs: [], warnings: [], errors: [], provenance: [], storage: {},
    runtime: { version: "0.30.0", runtime_mode: "vite", bridge_status: "ready", frozen: true, desktop_shell: "pywebview", local_first: true },
  } as unknown as SettingsHealthSummary;
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: new QueryClient() },
      createElement(MemoryRouter, null, createElement(SettingsOverview, { loading: false, summary })),
    ),
  );
}

describe("Settings overview", () => {
  it("links each attention item to where it is fixed, without update buttons", () => {
    const html = renderOverview([
      segment({}),
      segment({ id: "cvm_financials", name: "CVM Financial Statements", action_route: "/" }),
      segment({ id: "market_data", name: "Market Data", required: false, status: "degraded", action_route: "/settings/sources" }),
    ]);
    expect(html).not.toContain("Update Data");
    expect(html).not.toContain("Open Data<");
    expect(html).toContain('href="/"');
    expect(html).toContain("Download CVM data on Home");
    expect(html).toContain('href="/settings/sources"');
    expect(html).not.toContain("/settings/storage\">Download");
  });
});
