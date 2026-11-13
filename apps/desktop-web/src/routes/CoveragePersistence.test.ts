import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { CoveragePage } from "./CoveragePage";

const pending = vi.hoisted(() => [] as Array<() => unknown>);
vi.mock("react", async original => ({
  ...await original<typeof import("react")>(),
  useEffect: (effect: () => unknown) => { pending.push(effect); },
}));
afterEach(() => { pending.length = 0; vi.unstubAllGlobals(); });

it.each(["loading", "failed", "loaded"])("preserves the saved universe when the catalog is %s", state => {
  const saved = new Map([["active_coverage_universe_id", "saved-universe"]]);
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    removeItem: (key: string) => saved.delete(key),
  });
  vi.stubGlobal("window", { dispatchEvent: () => {} });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (state === "loaded") {
    client.setQueryData(["coverage-universes"], [{id: "saved-universe", status: "active", name: "Saved universe", analysis_type: "Equity", company_count: 0, created_at: "2026-11-12", updated_at: "2026-11-12"}]);
  } else if (state === "failed") {
    client.getQueryCache().build(client, {queryKey: ["coverage-universes"]}).setState({status: "error", error: new Error("Bridge unavailable")});
  }
  renderToStaticMarkup(createElement(QueryClientProvider, {client},
    createElement(MemoryRouter, {}, createElement(CoveragePage, {section: "universes"}))));
  pending.forEach(effect => effect());
  expect(saved.get("active_coverage_universe_id")).toBe("saved-universe");
  client.clear();
});

