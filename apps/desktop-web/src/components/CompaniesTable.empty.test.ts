import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";

import { CompaniesTable } from "./CompaniesTable";

afterEach(() => vi.unstubAllGlobals());

function renderEmptyDirectory(localState: unknown) {
  vi.stubGlobal("localStorage", { getItem: () => null });
  const client = new QueryClient();
  client.setQueryData(["companies", { search: "", sector: "", page: 1, pageSize: 25, sortBy: "marketCap", sortDirection: "asc" }], {
    mode: "desktop",
    page: { items: [], pagination: { total_items: 0, total_pages: 0, has_next: false, has_previous: false } },
  });
  client.setQueryData(["local-database-state"], localState);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client },
    createElement(MemoryRouter, { initialEntries: ["/empresas?sort=marketCap&direction=asc"] }, createElement(CompaniesTable))));
}

it("offers the download from an empty directory instead of a dead end", () => {
  const html = renderEmptyDirectory(S.empty);
  expect(html).toContain("Download CVM data");
  expect(html).not.toContain("Run Database Updates");
});
