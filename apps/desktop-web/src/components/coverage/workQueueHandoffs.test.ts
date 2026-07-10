import { describe, expect, it } from "vitest";

import {
  resolveCoverageWorkQueueHandoff,
  SUPPORTED_COVERAGE_WORK_QUEUE_TYPES,
} from "./workQueueHandoffs";

describe("coverage work queue handoffs", () => {
  it("maps supported queue reasons to deterministic analyst workflow handoffs", () => {
    const handoff = resolveCoverageWorkQueueHandoff(
      {
        task_type: "missing_liquidity",
        cd_cvm: 9512,
        reason: "Liquidity: only 8 trading day(s) in last 30 days.",
        severity: "medium",
        source: "derived",
      },
      { universeId: "univ-1" },
    );

    expect(handoff.supported).toBe(true);
    expect(handoff.analystQuestion).toBe("Is recent trading liquidity available for scoring?");
    expect(handoff.evidenceSurface).toBe("Company Overview market history");
    expect(handoff.actionLabel).toBe("Open market history");
    expect(handoff.destination).toBe(
      "/empresas/9512?from=coverage-work-queue&universe_id=univ-1&task_type=missing_liquidity&cd_cvm=9512&reason=Liquidity%3A+only+8+trading+day%28s%29+in+last+30+days.&severity=medium&source=derived",
    );
    expect(handoff.completionSignal).toBe(
      "The 30-day liquidity observation count reaches the scoring threshold, or the market-history refresh/ticker failure remains visible.",
    );
    expect(handoff.unsupportedReason).toBeNull();
  });

  it("covers current backend task types and the browser fixture alias", () => {
    const taskTypes = [
      "missing_market_cap",
      "missing_liquidity",
      "missing_gics",
      "unassigned_owner",
      "incomplete_checklist",
      "checklist_gap",
      "news_mapping_unavailable",
      "news_gap",
      "news_db_unavailable",
    ];

    expect(SUPPORTED_COVERAGE_WORK_QUEUE_TYPES).toEqual(taskTypes);

    for (const taskType of taskTypes) {
      const handoff = resolveCoverageWorkQueueHandoff(
        {
          task_type: taskType,
          cd_cvm: taskType === "news_db_unavailable" ? null : 9512,
          reason: `${taskType} reason`,
          severity: "low",
        },
        { universeId: "univ-1" },
      );

      expect(handoff.analystQuestion).not.toBe("");
      expect(handoff.evidenceSurface).not.toBe("");
      expect(handoff.completionSignal).not.toBe("");
      expect(handoff.supported || handoff.unsupportedReason).toBeTruthy();
    }
  });

  it("does not fabricate actions for unknown reasons or missing required company context", () => {
    const unknown = resolveCoverageWorkQueueHandoff(
      {
        task_type: "experimental_factor_gap",
        cd_cvm: 9512,
        reason: "Pilot factor moved.",
      },
      { universeId: "univ-1" },
    );

    expect(unknown.supported).toBe(false);
    expect(unknown.actionLabel).toBeNull();
    expect(unknown.destination).toBeNull();
    expect(unknown.unsupportedReason).toBe(
      "No supported workflow handoff exists yet for task type experimental_factor_gap.",
    );

    const missingCompany = resolveCoverageWorkQueueHandoff(
      {
        task_type: "incomplete_checklist",
        cd_cvm: null,
        reason: "Checklist item incomplete.",
      },
      { universeId: "univ-1" },
    );

    expect(missingCompany.supported).toBe(false);
    expect(missingCompany.actionLabel).toBeNull();
    expect(missingCompany.destination).toBeNull();
    expect(missingCompany.unsupportedReason).toBe(
      "This handoff requires a company CVM id, but the queue item did not provide one.",
    );
  });
});
