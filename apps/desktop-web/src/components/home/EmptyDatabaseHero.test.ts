import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";

import { EmptyDatabaseHero } from "./EmptyDatabaseHero";

function render(state: unknown) {
  const client = new QueryClient();
  client.setQueryData(["local-database-state"], state);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client },
      createElement(MemoryRouter, null, createElement(EmptyDatabaseHero, { onLoadRecommended: () => {}, onChooseWidgets: () => {} }))),
  );
}

describe("EmptyDatabaseHero", () => {
  it("offers the first download on an empty database", () => {
    expect(render(S.empty)).toContain("No CVM data on this computer yet");
  });

  // #579: the first companies land long before the first full run ends.
  it("stays during the first data update after statements start landing", () => {
    const firstRun = { ...S.updating, has_statements: true, last_full_update_at: null, last_run: null };
    const html = render(firstRun);
    expect(html).toContain("Getting CVM data");
    expect(html).toContain("162 of 438");
  });

  it("is absent during later data updates and on a populated database", () => {
    expect(render(S.updating)).toBe("");
    expect(render(S.current)).toBe("");
  });
});
