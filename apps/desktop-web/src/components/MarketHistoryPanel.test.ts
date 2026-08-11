import { describe, expect, it } from "vitest";

import { getMarketDataStatus } from "./MarketHistoryPanel";

describe("getMarketDataStatus", () => {
  it("surfaces stale local market data with its latest local date", () => {
    expect(
      getMarketDataStatus({
        hasLocalData: true,
        isStale: true,
        isError: false,
        isUpdating: false,
        lastDownloaded: "2026-08-04T14:12:00Z",
      }),
    ).toMatchObject({ label: "Stale · 04/08/2026", tone: "warn" });
  });
});
