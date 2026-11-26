import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";
import type { LocalDatabaseState } from "@/lib/bridge/types.localDatabase";

import { EmptyDatabaseHero } from "../home/EmptyDatabaseHero";
import { LocalDataEmptyState } from "./LocalDataEmptyState";

function withState(state: LocalDatabaseState, node: React.ReactElement) {
  const client = new QueryClient();
  client.setQueryData(["local-database-state"], state);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client }, createElement(MemoryRouter, null, node)),
  );
}

const emptyState = createElement(LocalDataEmptyState, {
  title: "No companies",
  emptyMessage: "The local database is empty. Download CVM data to list every active company.",
  fallbackMessage: "No companies match this view.",
});

describe("LocalDataEmptyState", () => {
  it("offers the shared download when the local database is empty", () => {
    const html = withState(S.empty, emptyState);
    expect(html).toContain("The local database is empty.");
    expect(html).toContain("Download CVM data");
    expect(html).toContain("Official CVM");
  });

  it("points to progress while the first download runs", () => {
    expect(withState(S.files, emptyState)).toContain("View progress");
  });

  it("keeps the screen's own explanation when data exists", () => {
    const html = withState(S.current, emptyState);
    expect(html).toContain("No companies match this view.");
    expect(html).not.toContain("Download CVM data");
  });
});

describe("EmptyDatabaseHero", () => {
  const hero = createElement(EmptyDatabaseHero, { onLoadRecommended: () => {}, onChooseWidgets: () => {} });

  it("leads an empty Home with one primary download", () => {
    const html = withState(S.empty, hero);
    expect(html).toContain("No CVM data on this computer yet");
    expect(html.match(/background:var\(--color-action-primary\)/g)?.length).toBe(1);
    expect(html).toContain("Load recommended layout");
    expect(html).toContain("Choose widgets");
  });

  it("shows progress and a path to Companies during the first download", () => {
    const html = withState(S.files, hero);
    expect(html).toContain("Getting CVM data");
    expect(html).toContain("Downloading CVM files · 6 of 10");
    expect(html).toContain('href="/empresas"');
  });

  it("explains a failed first download", () => {
    expect(withState(S.failed, hero)).toContain("The download didn&#x27;t finish");
  });

  it("renders nothing once the local database has statements", () => {
    expect(withState(S.current, hero)).toBe("");
  });
});
