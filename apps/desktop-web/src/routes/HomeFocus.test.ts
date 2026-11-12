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
  it("keeps primary modules and Settings visible, with Coverage/News under More", () => {
    const html = render(createElement(ModuleNav));
    const secondary = html.match(/<details[\s\S]*?<\/details>/)?.[0];
    expect(secondary).toContain("More");
    expect(secondary).toContain('href="/coverage"');
    expect(secondary).toContain('href="/news"');
    const primary = html.replace(secondary!, "");
    for (const route of ["/", "/empresas", "/setores", "/indicators", "/settings"]) {
      expect(primary).toContain(`href="${route}"`);
    }
  });
  it("keeps the secondary workspace identifiable on deep links", () => {
    expect(render(createElement(ModuleNav), "/coverage/work-queue")).toMatch(/<summary[^>]*>[\s\S]*?Coverage[\s\S]*?<\/summary>/);
  });
  it("adds Coverage to the palette without removing existing routes", async () => {
    const navigate = vi.fn();
    const commands = buildNavigationCommands(navigate);
    await commands.find(command => command.id === "nav:coverage")?.run();
    expect(navigate).toHaveBeenCalledWith("/coverage");
    expect(commands.some(command => command.id === "nav:news")).toBe(true);
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
