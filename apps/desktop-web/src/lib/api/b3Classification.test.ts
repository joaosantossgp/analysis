import { describe, expect, it } from "vitest";

import { getCompanySourceSectorBadges } from "@/components/EntityHeader";
import { describeB3Refresh } from "./b3Classification";

describe("B3 sector source", () => {
  it("labels CVM and B3 sectors by source and flags stale B3 data", () => {
    const badges = getCompanySourceSectorBadges({
      setor_cvm: "Petróleo e Gás",
      b3_classification: {
        b3_sector: "Petróleo. Gás e Biocombustíveis",
        b3_subsector: "Petróleo. Gás e Biocombustíveis",
        b3_segment: "Exploração. Refino e Distribuição",
        raw_classification: null,
        source_url: "https://example.invalid",
        fetched_at: "2026-01-01T00:00:00+00:00",
        stale: true,
      },
    });
    expect(badges.map((b) => [b.label, b.value])).toEqual([
      ["CVM sector", "Petróleo e Gás"],
      ["B3 sector", "Exploração. Refino e Distribuição"],
    ]);
    expect(badges[1].title).toContain("fetched 2026-01-01");
    expect(badges[1].title).toContain("stale");
  });

  it("omits the B3 badge when B3 sectors were never fetched", () => {
    expect(getCompanySourceSectorBadges({ setor_cvm: null, b3_classification: null })).toEqual([]);
  });

  it("keeps refresh failures and staleness visible in the status line", () => {
    expect(describeB3Refresh(null)).toContain("Never refreshed");
    const line = describeB3Refresh({
      ok: true,
      last_run: {
        started_at: "2026-11-24T10:00:00+00:00",
        finished_at: "2026-11-24T10:05:00+00:00",
        requested: 3,
        succeeded: 1,
        not_listed: 1,
        failed: 1,
        errors: "30: offline",
      },
      stored_companies: 1,
      stale: false,
      stale_after_days: 90,
    });
    expect(line).toBe("Last refresh 2026-11-24 10:05 UTC · 1 updated · 1 not listed on B3 · 1 failed");
  });
});
