import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";
import type { LocalDatabaseState } from "@/lib/bridge/types.localDatabase";

import { DataIndicator, DataPanelBody } from "./DataIndicator";

function renderIndicator(state: LocalDatabaseState) {
  const client = new QueryClient();
  client.setQueryData(["local-database-state"], state);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(DataIndicator)));
}

function renderPanel(state: LocalDatabaseState, online: boolean) {
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: new QueryClient() }, createElement(DataPanelBody, { state, online })),
  );
}

describe("DataIndicator", () => {
  it.each([
    ["empty", "EMPTY"],
    ["files", "CVM FILES 6/10"],
    ["updating", "UPDATING 37%"],
    ["current", "UP TO DATE"],
    ["stale", "STALE"],
    ["partial", "3 FAILED"],
    ["failed", "UPDATE FAILED"],
  ] as const)("labels the %s state in the top bar", (key, label) => {
    expect(renderIndicator(S[key])).toContain(label);
  });

  it("opens the Data panel as a dialog trigger", () => {
    expect(renderIndicator(S.current)).toContain('aria-haspopup="dialog"');
  });
});

describe("DataPanelBody", () => {
  it("lists failed companies after a partial run", () => {
    const html = renderPanel(S.partial, true);
    expect(html).toContain("Completed with 3 failures");
    expect(html).toContain("OI SA");
    expect(html).toContain("DFP 2024 rows rejected by validation");
  });

  it("states that data updates never start on their own", () => {
    const html = renderPanel(S.current, true);
    expect(html).toContain("Data updates run only when you start them");
    expect(html).toContain("Official CVM");
  });

  it("keeps failures visible while offline", () => {
    const html = renderPanel(S.partial, false);
    expect(html).toContain("No internet connection.");
    expect(html).toContain("OI SA");
  });
});
