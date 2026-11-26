import { afterEach, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { useRefreshJobInvalidation } from "./useRefreshJobInvalidation";

let client: QueryClient;
vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...await importOriginal<typeof import("@tanstack/react-query")>(),
  useQueryClient: () => client,
}));

afterEach(() => client.clear());

it("invalidates cached empty statement evidence after a Database Updates job", () => {
  client = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
  const evidenceKey = ["company-statement-years", 4170, "DFC"];
  client.setQueryData(evidenceKey, { mode: "desktop", years: [] });
  client.setQueryData(["company-years", 4170], { mode: "desktop", years: [] });

  useRefreshJobInvalidation()();

  expect(client.getQueryState(evidenceKey)?.isInvalidated).toBe(true);
  expect(client.getQueryState(["company-years", 4170])?.isInvalidated).toBe(true);
});

it("refreshes the command palette company index after a data update", () => {
  client = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });
  const indexKey = ["command-palette", "companies-index"];
  client.setQueryData(indexKey, []);

  useRefreshJobInvalidation()();

  expect(client.getQueryState(indexKey)?.isInvalidated).toBe(true);
});
