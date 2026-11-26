import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it } from "vitest";

import { WatchlistRow } from "./WatchlistCard";

function renderRow(priceStatus: string) {
  const client = new QueryClient();
  client.setQueryData(["company-historical-indicators", 9512], {
    mode: "desktop",
    data: { ok: true, cd_cvm: 9512, ticker_b3: "PETR4", price_history_status: priceStatus, yearly_data: [{ year: 2024, roe: 0.1, mg_ebit: 0.2, mg_liq: 0.05, stock_price: null }] },
  });
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(MemoryRouter, null,
    createElement("table", null, createElement("tbody", null,
      createElement(WatchlistRow, { company: { cdCvm: 9512, name: "PETROBRAS", ticker: "PETR4" }, metric: "stock_price", isCompact: false }))))));
}

it("asks before fetching external prices when there is no local price history", () => {
  const html = renderRow("missing");
  expect(html).toContain("No local price history");
  expect(html).toContain("Fetch prices (external)");
});

it("shows the local value when price history exists", () => {
  expect(renderRow("local")).not.toContain("No local price history");
});
