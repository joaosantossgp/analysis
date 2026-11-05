import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoveragePage } from "../CoveragePage";

const universe = {
  id: "fixture-universe", name: "Fixture coverage", purpose: "Offline test",
  analysis_type: "Equity", benchmark: null, status: "active", company_count: 0,
  created_at: "2026-01-01", updated_at: "2026-01-01",
};

afterEach(() => vi.unstubAllGlobals());

function render(section: "universes" | "prioritization" | "work-queue" | "capacity", state: "ready" | "empty" | "loading" | "error" = "ready") {
  vi.stubGlobal("localStorage", { getItem: () => state === "ready" ? universe.id : null });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryOnMount: false, staleTime: Infinity } } });
  if (state === "ready") {
    client.setQueryData(["coverage-universes"], [universe]);
    client.setQueryData(["coverage-universe-detail", universe.id], { ...universe, companies: [] });
    client.setQueryData(["coverage-scores", universe.id], []);
    client.setQueryData(["coverage-work-queue", universe.id], [{
      task_type: "news_db_unavailable", reason: "News source unavailable",
      suggested_action: "Review news source", severity: "high",
    }]);
    client.setQueryData(["coverage-capacity", universe.id], {
      available_hours: 1600, required_hours: 0, capacity_utilization_pct: 0,
      warnings: ["Partial source coverage"], tier_counts: {}, tier_hours: {},
    });
  } else if (state === "empty") {
    client.setQueryData(["coverage-universes"], []);
  } else if (state === "error") {
    client.getQueryCache().build(client, { queryKey: ["coverage-universes"] }).setState({
      status: "error", error: new Error("Offline catalog unavailable"), fetchStatus: "idle",
    });
  }
  try {
    return renderToStaticMarkup(
      <QueryClientProvider client={client}><MemoryRouter><CoveragePage section={section} /></MemoryRouter></QueryClientProvider>,
    );
  } finally { client.clear(); }
}

describe("Coverage workspace composition", () => {
  it.each([
    ["loading", "Loading coverage universes"],
    ["empty", "Create your first workspace"],
    ["error", "Offline catalog unavailable"],
  ] as const)("keeps the %s state visible", (state, message) => {
    expect(render("universes", state)).toContain(message);
  });

  it.each([
    ["universes", "Recommendation Package"],
    ["prioritization", "Fixture coverage"],
    ["work-queue", "News source unavailable"],
    ["capacity", "Partial source coverage"],
  ] as const)("renders the selected %s workspace from local query data", (section, message) => {
    const markup = render(section);
    expect(markup).toContain("Fixture coverage");
    expect(markup).toContain(message);
  });
});
