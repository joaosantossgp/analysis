import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ModuleNav } from "../components/shell/ModuleNav";
import { buildNavigationCommands } from "../components/command/commands/navigation";
import { HomePage, RECOMMENDED_LAYOUT, parseLayoutItems, parseCardConfigs } from "./HomePage";

const render = (node: React.ReactNode, path = "/") => renderToStaticMarkup(
  createElement(QueryClientProvider, { client: new QueryClient() },
    createElement(MemoryRouter, { initialEntries: [path] }, node)));

describe("company-focused shell", () => {
  it("keeps Home and analytical modules but retires standalone News/Coverage", () => {
    const html = render(createElement(ModuleNav));
    for (const route of ["/", "/empresas", "/setores", "/indicators", "/settings"]) expect(html).toContain(`href="${route}"`);
    expect(html).not.toContain('href="/news"');
    expect(html).not.toContain('href="/coverage"');
    expect(html).not.toContain("<details");
  });
  it("opens Coverage inside Companies and removes News palette commands", async () => {
    const navigate = vi.fn();
    const commands = buildNavigationCommands(navigate);
    await commands.find(command => command.id === "nav:coverage")?.run();
    expect(navigate).toHaveBeenCalledWith("/empresas/coverage");
    expect(commands.some(command => command.id.startsWith("nav:news"))).toBe(false);
  });
  it("recommends only the two analysis widgets", () => {
    expect(RECOMMENDED_LAYOUT.map(item => item.id)).toEqual(["watchlist", "market-price"]);
  });
  it("preserves saved optional widgets and their configuration, including an empty workspace", () => {
    const saved = ["top-news", "priority-queue", "database-status"].map((id, index) => ({ id, x: 0, y: index * 2, w: 2, h: 2, isMinimized: false, isCompact: true }));
    expect(parseLayoutItems(JSON.stringify(saved))).toEqual(saved);
    expect(parseLayoutItems("[]")).toEqual([]);
    expect(parseLayoutItems(null)).toEqual([]);
    expect(parseCardConfigs('{"priority-queue":{"universeId":"saved"},"top-news":{"source":"cvm"}}')).toMatchObject({ "priority-queue": { universeId: "saved" }, "top-news": { source: "cvm" } });
  });
  it("lets an empty Home open Companies without configuring widgets", () => {
    expect(render(createElement(HomePage))).toMatch(/href="\/empresas"[^>]*>Open Companies/);
  });
});

describe("Home with an empty local database", () => {
  const renderWith = (state: unknown) => {
    const client = new QueryClient();
    client.setQueryData(["local-database-state"], state);
    return renderToStaticMarkup(
      createElement(QueryClientProvider, { client }, createElement(MemoryRouter, { initialEntries: ["/"] }, createElement(HomePage))),
    );
  };

  it("leads with the download instead of the layout chooser", async () => {
    const { MOCK_LOCAL_DATABASE_STATES } = await import("../lib/bridge/mockLocalDatabase");
    const html = renderWith(MOCK_LOCAL_DATABASE_STATES.empty);
    expect(html).toContain("No CVM data on this computer yet");
    expect(html).not.toContain("Start with a company");
    expect(html.indexOf("Analyst Workspace")).toBeLessThan(html.indexOf("No CVM data on this computer yet"));
  });

  it("drops the MODE, SYNC TIME and JOB ACTIVE chips and renames COVERAGE", async () => {
    const { MOCK_LOCAL_DATABASE_STATES } = await import("../lib/bridge/mockLocalDatabase");
    const html = renderWith(MOCK_LOCAL_DATABASE_STATES.current);
    expect(html).not.toContain("MODE:");
    expect(html).not.toContain("SYNC TIME:");
    expect(html).not.toContain("COVERAGE:");
    expect(html).toContain("COMPLETENESS:");
  });

  it("shows completeness and gaps as unknown on an empty database", async () => {
    const { MOCK_LOCAL_DATABASE_STATES } = await import("../lib/bridge/mockLocalDatabase");
    const html = renderWith(MOCK_LOCAL_DATABASE_STATES.empty);
    expect(html).toMatch(/COMPLETENESS:<\/span><span[^>]*>—/);
    expect(html).toMatch(/GAPS:<\/span><span[^>]*>—/);
  });
});
