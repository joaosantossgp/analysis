import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";
import type { LocalDatabaseState } from "@/lib/bridge/types.localDatabase";

import { DataAction } from "./DataAction";

function render(state: LocalDatabaseState, opts: { online?: boolean; context?: "panel" | "inline" } = {}) {
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: new QueryClient() },
      createElement(DataAction, { state, online: opts.online ?? true, context: opts.context ?? "panel" }),
    ),
  );
}

describe("DataAction", () => {
  it("offers the first download when the local database is empty", () => {
    expect(render(S.empty)).toContain("Download CVM data");
  });

  it("offers an update once data exists", () => {
    expect(render(S.current)).toContain("Update data");
    expect(render(S.partial)).toContain("Update data");
  });

  it("makes the update the primary action when the database is stale", () => {
    expect(render(S.stale)).toMatch(/background:var\(--color-action-primary\)[^>]*>Update data/);
  });

  it("lets the analyst retry a failed first download", () => {
    expect(render(S.failed)).toContain("Try again");
  });

  it("cancels a running data update from the panel", () => {
    expect(render(S.updating, { context: "panel" })).toContain("Cancel update");
    expect(render(S.files, { context: "panel" })).toContain("Cancel update");
  });

  it("points to progress instead of starting a second run elsewhere", () => {
    const html = render(S.updating, { context: "inline" });
    expect(html).toContain("View progress");
    expect(html).not.toContain("Cancel update");
  });

  it("explains why the download is unavailable offline", () => {
    const html = render(S.empty, { online: false });
    expect(html).toContain("disabled");
    expect(html).toContain("Offline — connect to download.");
  });
});
