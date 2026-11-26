import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";

import { CompaniesTable } from "./CompaniesTable";

afterEach(() => vi.unstubAllGlobals());

const ITEMS = [
  { cd_cvm: 9512, company_name: "PETROBRAS", ticker_b3: "PETR4", market_cap_brl: 300, anos_disponiveis: [2024], has_financial_data: true, data_status: "complete" },
  { cd_cvm: 14673, company_name: "AMBEV", ticker_b3: "ABEV3", market_cap_brl: 200, anos_disponiveis: [], has_financial_data: false },
  { cd_cvm: 4170, company_name: "OI SA", ticker_b3: null, market_cap_brl: 100, anos_disponiveis: [], has_financial_data: false },
  { cd_cvm: 777, company_name: "OUTSIDE RUN", ticker_b3: null, market_cap_brl: 50, anos_disponiveis: [], has_financial_data: false },
];

function render(localState: unknown) {
  vi.stubGlobal("localStorage", { getItem: () => null });
  const client = new QueryClient();
  client.setQueryData(["companies", { search: "", sector: "", page: 1, pageSize: 25, sortBy: "marketCap", sortDirection: "desc" }], {
    mode: "desktop",
    page: { items: ITEMS, pagination: { total_items: 4, total_pages: 1, has_next: false, has_previous: false } },
  });
  client.setQueryData(["local-database-state"], localState);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client },
    createElement(MemoryRouter, { initialEntries: ["/empresas?sort=marketCap&direction=desc"] }, createElement(CompaniesTable))));
}

function rowOf(html: string, name: string) {
  const start = html.indexOf(name);
  return html.slice(start, html.indexOf("</tr>", start));
}

describe("Companies during a data update", () => {
  const running = {
    ...S.updating,
    run: { ...S.updating.run!, company_ids: [9512, 14673, 4170], current_cvm: 14673 },
  };

  it("marks the company being processed and the queued ones", () => {
    const html = render(running);
    expect(rowOf(html, "AMBEV")).toContain("Downloading");
    expect(rowOf(html, "OI SA")).toContain("Queued");
    expect(rowOf(html, "PETROBRAS")).toContain("Complete");
  });

  it("never marks companies outside the run", () => {
    expect(rowOf(render(running), "OUTSIDE RUN")).not.toContain("Queued");
  });

  it("shows the run phase above the list", () => {
    expect(render(running)).toContain("162 of 438 companies processed");
    expect(render({ ...S.files, run: { ...S.files.run!, company_ids: [4170], current_cvm: null } })).toContain(
      "Step 1 of 2 · downloading CVM files (6 of 10)",
    );
  });

  it("marks failed companies after a partial run", () => {
    expect(rowOf(render(S.partial), "OI SA")).toContain("Failed");
  });
});
