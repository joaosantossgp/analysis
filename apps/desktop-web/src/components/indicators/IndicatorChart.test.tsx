import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DEFAULT_INDICATOR_CHART_HEIGHT, IndicatorChart } from "./IndicatorChart";

describe("IndicatorChart axis labels", () => {
  it("uses the shared company-chart height by default", () => {
    const markup = renderToStaticMarkup(
      <IndicatorChart
        periods={["2025"]}
        series={[]}
        config={{ type: "line", smooth: false, markers: false, legend: false, grid: true, dataLabels: false, indexMode: false }}
      />,
    );

    expect(DEFAULT_INDICATOR_CHART_HEIGHT).toBe(320);
    expect(markup).toContain(`height:${DEFAULT_INDICATOR_CHART_HEIGHT}px`);
  });

  it("does not render a redundant unit caption beside unit-formatted ticks", () => {
    const markup = renderToStaticMarkup(
      <IndicatorChart
        periods={["2024", "2025"]}
        series={[
          {
            id: "price",
            label: "Price",
            unit: "brl",
            color: "#fff",
            type: "line",
            axis: "left",
            points: [10, 12],
            latest: 12,
          },
          {
            id: "volume",
            label: "Trading Volume",
            unit: "volume",
            color: "#0ff",
            type: "line",
            axis: "right",
            points: [1_000_000, 1_200_000],
            latest: 1_200_000,
          },
        ]}
        config={{ type: "line", smooth: false, markers: false, legend: false, grid: true, dataLabels: false, indexMode: false }}
      />,
    );

    expect(markup).not.toContain(">R$<");
    expect(markup).not.toContain(">Volume<");
    expect(markup).toContain("1.2M");
  });
});
