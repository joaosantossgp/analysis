/**
 * Mock bridge — dev-only fixture implementation of BridgeApi.
 *
 * Active only when VITE_MOCK_BRIDGE=1 AND import.meta.env.DEV is true.
 * Never compiled into production builds (tree-shaken by Vite).
 *
 * Domain handlers live in ./mock.<domain>.ts alongside ./mock.fixtures.ts,
 * ./mockEnergyFixtures.ts, and ./mockLocalDatabase.ts.
 */

// Safety guard: throw immediately if somehow loaded outside a dev build.
if (!import.meta.env.DEV) {
  throw new Error("[CVMAnalytics] mock bridge loaded in non-dev build — this is a bug");
}

import type { BridgeApi } from "./types";
import { createMockCompaniesMethods } from "./mock.companies";
import { createMockCoverageMethods } from "./mock.coverage";
import { createMockDistributionMethods } from "./mock.distribution";
import { createMockEnergyMethods } from "./mock.energy";
import { createMockExcelMethods } from "./mock.excel";
import { createMockNewsMethods } from "./mock.news";
import { createMockRefreshMethods } from "./mock.refresh";
import { createMockStatusMethods } from "./mock.status";

export function createMockBridge(): Partial<BridgeApi> {
  return {
    ...createMockStatusMethods(),
    ...createMockNewsMethods(),
    ...createMockEnergyMethods(),
    ...createMockCompaniesMethods(),
    ...createMockRefreshMethods(),
    ...createMockExcelMethods(),
    ...createMockDistributionMethods(),
    ...createMockCoverageMethods(),
  };
}
