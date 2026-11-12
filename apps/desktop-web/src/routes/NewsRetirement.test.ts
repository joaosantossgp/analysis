import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it } from "vitest";
import { WORKSPACE_REGISTRY } from "../components/home/WorkspaceRegistry";
import { WorkspaceConfigPanel } from "../components/home/WorkspaceConfigPanel";
import { resolveCoverageWorkQueueHandoff } from "../components/coverage/workQueueHandoffs";

it("keeps a saved News widget as a retirement notice and offers no new News widget", () => {
 const client = new QueryClient();
 const html = renderToStaticMarkup(createElement(QueryClientProvider, {client}, createElement(MemoryRouter, {},
   createElement(WORKSPACE_REGISTRY['top-news'].component, {config:{saved:'value'},onConfigure:()=>{},onRemove:()=>{}}))));
 expect(html).toContain('News has been retired');
 expect(client.getQueryCache().getAll()).toHaveLength(0);
 const panel = renderToStaticMarkup(createElement(WorkspaceConfigPanel, {isOpen:true,onClose:()=>{},activeCardIds:[],onToggleCard:()=>{}}));
 expect(panel).not.toContain('Top News Feed');
 client.clear();
});
it.each(['news_gap','news_mapping_unavailable','news_db_unavailable'])("keeps %s evidence visible without a misleading retired action", task_type => {
 const handoff = resolveCoverageWorkQueueHandoff({task_type});
 expect(handoff.supported).toBe(false);
 expect(handoff.destination).toBeNull();
 expect(handoff.unsupportedReason).toContain('retired');
});
