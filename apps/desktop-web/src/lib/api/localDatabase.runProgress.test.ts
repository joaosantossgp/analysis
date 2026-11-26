import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "@/lib/bridge/mockLocalDatabase";

import { LOCAL_DATABASE_STATE_KEY, refreshCompaniesOnRunProgress } from "./localDatabase";

const COMPANIES_KEY = ["companies", { page: 1 }];

function setup() {
  const client = new QueryClient();
  refreshCompaniesOnRunProgress(client);
  client.setQueryData(COMPANIES_KEY, { mode: "desktop" });
  const isStale = () => client.getQueryState(COMPANIES_KEY)?.isInvalidated ?? false;
  const reset = () => client.setQueryData(COMPANIES_KEY, { mode: "desktop" });
  return { client, isStale, reset };
}

// #577: an open Companies directory must follow the running data update.
describe("refreshCompaniesOnRunProgress", () => {
  const run = S.updating.run!;

  it("refreshes company lists when the run starts, progresses and ends", () => {
    const { client, isStale, reset } = setup();

    client.setQueryData(LOCAL_DATABASE_STATE_KEY, { ...S.updating, run: { ...run, phase: "starting", processed: 0 } });
    expect(isStale()).toBe(true);
    reset();

    client.setQueryData(LOCAL_DATABASE_STATE_KEY, { ...S.updating, run: { ...run, processed: 5 } });
    expect(isStale()).toBe(true);
    reset();

    client.setQueryData(LOCAL_DATABASE_STATE_KEY, { ...S.current, run: null });
    expect(isStale()).toBe(true);
  });

  it("leaves company lists alone while nothing changes", () => {
    const { client, isStale, reset } = setup();
    client.setQueryData(LOCAL_DATABASE_STATE_KEY, { ...S.updating, run: { ...run, processed: 5 } });
    reset();

    client.setQueryData(LOCAL_DATABASE_STATE_KEY, { ...S.updating, run: { ...run, processed: 5, eta_seconds: 1 } });
    expect(isStale()).toBe(false);
  });

  it("does nothing when no run was ever seen", () => {
    const { client, isStale } = setup();
    client.setQueryData(LOCAL_DATABASE_STATE_KEY, { ...S.current, run: null });
    expect(isStale()).toBe(false);
  });
});
