import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { SectorsPage } from "../SectorsPage";

vi.mock("@tanstack/react-query", () => ({ useQuery: () => ({ data: { mode: "desktop", items: [{ sector_name: "Utilities", sector_slug: "utilities", company_count: 2, latest_year: null, sub_industries: [], parent_sector_name: null, parent_sector_slug: null }] } }) }));

function markup(path: string) {
  return renderToStaticMarkup(<MemoryRouter initialEntries={[path]}><SectorsPage /></MemoryRouter>);
}
describe("sector directory navigation", () => {
  it("keeps the sector detail link without a redundant actions column", () => {
    const html = markup("/setores");
    expect(html).toContain('href="/setores/utilities"');
    expect(html).not.toContain(">Actions<");
    expect(html).not.toContain("View companies");
  });
  it("offers CVM classification as an alternative and links its names to companies", () => {
    const html = markup("/setores?visao=cvm_sector");
    expect(html).toContain('aria-label="Alternative classification"');
    expect(html).toContain('href="/empresas?sector=utilities"');
    expect(html).not.toContain('href="/setores/utilities"');
  });
});
