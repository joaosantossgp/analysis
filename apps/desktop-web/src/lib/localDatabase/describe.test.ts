import { describe, expect, it } from "vitest";

import { MOCK_LOCAL_DATABASE_STATES as S } from "../bridge/mockLocalDatabase";
import { describeLocalDatabaseState } from "./describe";

const online = { online: true };

describe("describeLocalDatabaseState", () => {
  it("shows checking while the state is unknown", () => {
    expect(describeLocalDatabaseState(null, online)).toMatchObject({ short: "CHECKING", tone: "muted" });
  });

  it("invites the first download when the local database is empty", () => {
    expect(describeLocalDatabaseState(S.empty, online)).toMatchObject({
      glyph: "○",
      short: "EMPTY",
      tone: "warn",
      headline: "Local database is empty",
    });
  });

  it("counts CVM files during the file phase", () => {
    expect(describeLocalDatabaseState(S.files, online)).toMatchObject({
      short: "CVM FILES 6/10",
      headline: "Downloading CVM files · 6 of 10",
    });
  });

  it("shows company progress with a pace-based ETA", () => {
    const d = describeLocalDatabaseState(S.updating, online);
    expect(d.short).toBe("UPDATING 37%");
    expect(d.headline).toBe("Updating · 162 of 438 companies");
    expect(d.detail).toBe("About 24 min left, from this run's pace");
    expect(d.percent).toBe(37);
  });

  it("names the last data update when up to date", () => {
    expect(describeLocalDatabaseState(S.current, online)).toMatchObject({
      short: "UP TO DATE",
      tone: "ok",
      detail: "Last data update Nov 20, 2026",
    });
  });

  it("names the passed CVM deadline when stale", () => {
    expect(describeLocalDatabaseState(S.stale, online)).toMatchObject({
      short: "STALE",
      headline: "New CVM filings may be due",
      detail: "ITR 3Q26 deadline passed on Nov 14, 2026 · last data update Aug 2, 2026",
    });
  });

  it("explains stale data without any full data update", () => {
    const state = { ...S.stale, last_full_update_at: null, stale_reason: { label: null, due: null } };
    expect(describeLocalDatabaseState(state, online).detail).toBe("No full data update has been recorded yet.");
  });

  it("counts failures after a partial run", () => {
    expect(describeLocalDatabaseState(S.partial, online)).toMatchObject({
      short: "3 FAILED",
      headline: "Completed with 3 failures",
      detail: "435 of 438 companies updated · Nov 20, 2026",
    });
  });

  it("uses the singular for one failure", () => {
    const one = { ...S.partial, last_run: { ...S.partial.last_run!, failures: 1 } };
    expect(describeLocalDatabaseState(one, online).headline).toBe("Completed with 1 failure");
  });

  it("shows the failure reason when the data update failed", () => {
    expect(describeLocalDatabaseState(S.failed, online)).toMatchObject({
      short: "UPDATE FAILED",
      tone: "err",
      detail: "The CVM server did not respond.",
    });
  });

  it("adds offline as a suffix without hiding the state", () => {
    const d = describeLocalDatabaseState(S.partial, { online: false });
    expect(d.short).toBe("3 FAILED · OFFLINE");
    expect(d.headline).toBe("Completed with 3 failures");
    expect(d.offline).toBe(true);
  });
});

describe("describeLocalDatabaseState when the state cannot be read", () => {
  it("shows an unavailable state instead of a blank pill", () => {
    const broken = { state: "unknown", error: "database is locked" } as unknown as Parameters<typeof describeLocalDatabaseState>[0];
    expect(describeLocalDatabaseState(broken, online)).toMatchObject({
      short: "STATE UNAVAILABLE",
      tone: "err",
      detail: "database is locked",
    });
  });
});
