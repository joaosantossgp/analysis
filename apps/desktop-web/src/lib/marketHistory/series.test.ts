import { describe, expect, it } from "vitest";

import {
  buildMarketChartSeries,
  canEnableMarketMetric,
  type MarketView,
} from "./series";

const observations = [
  {
    date: "2026-01-02",
    open: 10,
    high: 11,
    low: 9,
    close: 10,
    adjusted_close: 10,
    volume: 100,
    dividend: 0,
    split_ratio: 1,
    price_return_index: 1,
    total_return_index: 1,
    ttm_dividend_yield: 0.03,
  },
  {
    date: "2026-01-03",
    open: 11,
    high: 12,
    low: 10,
    close: 11,
    adjusted_close: 11,
    volume: 120,
    dividend: 0,
    split_ratio: 1,
    price_return_index: 1.1,
    total_return_index: 1.12,
    ttm_dividend_yield: 0.031,
  },
];

describe("market metric selection", () => {
  it("plots price and dividend yield on their respective axes", () => {
    const series = buildMarketChartSeries({
      observations,
      views: ["price", "yield"],
      selectedIds: ["adjusted_close", "ttm_dividend_yield"],
      chartType: "line",
      indexMode: false,
    });

    expect(series.map(({ id, axis, unit }) => ({ id, axis, unit }))).toEqual([
      { id: "adjusted_close", axis: "left", unit: "brl" },
      { id: "ttm_dividend_yield", axis: "right", unit: "pct" },
    ]);
  });

  it("rejects a metric that would introduce a third unit", () => {
    const selected: MarketView[] = ["price", "return"];

    expect(canEnableMarketMetric(selected, "volume")).toBe(false);
    expect(canEnableMarketMetric(selected, "yield")).toBe(true);
  });
});
