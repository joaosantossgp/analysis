import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";

import { LocalDatabaseNotice } from "./LocalDatabaseNotice";

function render(state: unknown) {
  const client = new QueryClient();
  client.setQueryData(["local-database-state"], state);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(LocalDatabaseNotice)));
}

describe("LocalDatabaseNotice", () => {
  it("names the passed deadline and offers an update when stale", () => {
    const html = render(S.stale);
    expect(html).toContain("New CVM filings may be due");
    expect(html).toContain("ITR 3Q26 deadline passed on Nov 14, 2026");
    expect(html).toContain("Update data");
  });

  it("points to the failures after a partial run", () => {
    const html = render(S.partial);
    expect(html).toContain("Completed with 3 failures");
    expect(html).toContain("View failures");
  });

  it("stays out of the way otherwise", () => {
    expect(render(S.current)).toBe("");
    expect(render(S.empty)).toBe("");
  });
});
