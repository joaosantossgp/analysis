import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";

import { QueuedCompanyNotice } from "./QueuedCompanyNotice";

function render(state: unknown, cdCvm: number) {
  const client = new QueryClient();
  client.setQueryData(["local-database-state"], state);
  return renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(QueuedCompanyNotice, { cdCvm })));
}

describe("QueuedCompanyNotice", () => {
  it("offers Download now for a company waiting in the running data update", () => {
    const html = render(S.updating, 4170);
    expect(html).toContain("Download now");
    expect(html).toContain("running data update");
  });

  it("stays silent for the company being processed", () => {
    expect(render(S.updating, 14673)).toBe("");
  });

  it("stays silent outside a run", () => {
    expect(render(S.current, 4170)).toBe("");
    expect(render(S.updating, 777)).toBe("");
  });
});
