import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { CompaniesTable } from "./CompaniesTable";

afterEach(() => vi.unstubAllGlobals());

it("renders the server page order, keeping absent market caps last for ascending order", () => {
  vi.stubGlobal("localStorage", { getItem: () => null });
  const client = new QueryClient();
  client.setQueryData(["companies", { search: "", sector: "", page: 1, pageSize: 25, sortBy: "marketCap", sortDirection: "asc" }], {
    mode: "desktop",
    page: {
      items: [
        { cd_cvm: 10, company_name: "Priced issuer", ticker_b3: "AAA3", market_cap_brl: 100, anos_disponiveis: [], has_financial_data: false },
        { cd_cvm: 20, company_name: "Unknown issuer", ticker_b3: null, market_cap_brl: null, anos_disponiveis: [], has_financial_data: false },
      ],
      pagination: { total_items: 2, total_pages: 1, has_next: false, has_previous: false },
    },
  });
  const html = renderToStaticMarkup(createElement(QueryClientProvider, { client },
    createElement(MemoryRouter, { initialEntries: ["/empresas?sort=marketCap&direction=asc"] }, createElement(CompaniesTable))));
  expect(html.indexOf("Priced issuer")).toBeGreaterThan(-1);
  expect(html.indexOf("Priced issuer")).toBeLessThan(html.indexOf("Unknown issuer"));
  client.clear();
});
