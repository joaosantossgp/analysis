import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EditableSeriesLegend } from "./IndicatorLegend";

describe("EditableSeriesLegend", () => {
  it("renders only the series key without latest values or controls", () => {
    const markup = renderToStaticMarkup(
      <EditableSeriesLegend
        series={[
          { id: "margin", label: "Margin", unit: "pct", color: "#0ff", type: "line", axis: "left", points: [0.2], latest: 0.2 },
          { id: "roe", label: "ROE", unit: "pct", color: "#fc0", type: "line", axis: "left", points: [0.15], latest: 0.15 },
        ]}
        stylesById={new Map()}
        onSetColor={() => undefined}
        onSetType={() => undefined}
      />,
    );

    expect(markup).toContain("Margin");
    expect(markup).toContain("ROE");
    expect(markup).not.toContain("20.0%");
    expect(markup).not.toContain("Edit");
  });
});
