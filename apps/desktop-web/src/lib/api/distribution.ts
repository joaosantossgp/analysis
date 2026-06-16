/**
 * Electricity distribution analytics API facade.
 *
 * Wraps bridge methods for the distributor-level Energy Utilities layer.
 * All reads hit local SQLite — no network on read path.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  DistributorEntry,
  DistributorDetail,
  DistributionSeriesEntry,
  DistributionRefreshStatus,
  EconomicGroupEntry,
  EconomicGroupDetail,
  DistributionHealthResponse,
  ConglomerateEntry,
  AssetMappingEntry
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable.";

export type DistributionDistributorsResult =
  | { mode: "desktop" | "mock"; items: DistributorEntry[]; count: number }
  | { mode: "browser"; items: []; count: 0; reason: string };

export type DistributionDistributorDetailResult =
  | { mode: "desktop" | "mock"; detail: DistributorDetail }
  | { mode: "browser"; detail: null; reason: string };

export type DistributionSeriesResult =
  | { mode: "desktop" | "mock"; series: DistributionSeriesEntry[]; count: number }
  | { mode: "browser"; series: []; count: 0; reason: string };

export type DistributionRefreshStatusResult =
  | { mode: "desktop" | "mock"; status: DistributionRefreshStatus }
  | { mode: "browser"; status: null; reason: string };

export type DistributionRefreshTriggerResult =
  | { mode: "desktop" | "mock"; status: string; error: string | null }
  | { mode: "browser"; status: "error"; error: string };

export async function fetchDistributionDistributors(params?: {
  search?: string;
  economic_group_id?: string;
  uf?: string;
}): Promise<DistributionDistributorsResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", items: [], count: 0, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_distributors", params ?? {});
  if (payload.error) throw new Error(payload.error);
  return { mode, items: payload.items ?? [], count: payload.count ?? 0 };
}

export async function fetchDistributionDistributorDetail(
  distributorId: string,
): Promise<DistributionDistributorDetailResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", detail: null, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_distributor_detail", {
    distributor_id: distributorId,
  });
  if ("error" in payload && payload.error) throw new Error(payload.error);
  return { mode, detail: payload as DistributorDetail };
}

export async function fetchDistributionSeries(params: {
  entity_type: string;
  entity_id: string;
  frequency?: string;
}): Promise<DistributionSeriesResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", series: [], count: 0, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_series", params);
  if (payload.error) throw new Error(payload.error);
  return { mode, series: payload.series ?? [], count: payload.count ?? 0 };
}

export async function fetchDistributionRefreshStatus(): Promise<DistributionRefreshStatusResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", status: null, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_refresh_status", {});
  return { mode, status: payload };
}

export async function triggerDistributionRefresh(params?: {
  years?: number[];
  force?: boolean;
}): Promise<DistributionRefreshTriggerResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", status: "error", error: BROWSER_REASON };
  }
  const payload = await callBridge("refresh_distribution_data", params ?? {});
  return { mode, status: payload.status, error: payload.error };
}

export type DistributionGroupsResult =
  | { mode: "desktop" | "mock"; items: EconomicGroupEntry[]; count: number }
  | { mode: "browser"; items: []; count: 0; reason: string };

export type DistributionGroupDetailResult =
  | { mode: "desktop" | "mock"; detail: EconomicGroupDetail }
  | { mode: "browser"; detail: null; reason: string };

export type DistributionExcelResult =
  | { mode: "desktop" | "mock"; path: string | null; error: string | null }
  | { mode: "browser"; path: null; error: string };

export async function fetchDistributionGroups(): Promise<DistributionGroupsResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", items: [], count: 0, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_groups", {});
  if (payload.error) throw new Error(payload.error);
  return { mode, items: payload.items ?? [], count: payload.count ?? 0 };
}

export async function fetchDistributionGroupDetail(
  groupId: string,
): Promise<DistributionGroupDetailResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", detail: null, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_group_detail", {
    group_id: groupId,
  });
  if ("error" in payload && payload.error) throw new Error(payload.error);
  return { mode, detail: payload as EconomicGroupDetail };
}

export async function exportDistributionExcel(
  entityType: "distributor" | "group",
  entityId: string,
): Promise<DistributionExcelResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", path: null, error: BROWSER_REASON };
  }
  const payload = await callBridge("export_distribution_excel", {
    entity_type: entityType,
    entity_id: entityId,
  });
  return { mode, path: payload.path, error: payload.error };
}

export type DistributionHealthResult =
  | { mode: "desktop" | "mock"; health: DistributionHealthResponse }
  | { mode: "browser"; health: null; reason: string };

export async function fetchDistributionHealth(): Promise<DistributionHealthResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", health: null, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_distribution_health", {});
  if (payload.error) throw new Error(payload.error);
  return { mode, health: payload as DistributionHealthResponse };
}



export type ConglomeratesResult =
  | { mode: "desktop" | "mock"; items: ConglomerateEntry[]; count: number }
  | { mode: "browser"; items: []; count: 0; reason: string };

export type AssetMappingsResult =
  | { mode: "desktop" | "mock"; items: AssetMappingEntry[]; count: number }
  | { mode: "browser"; items: []; count: 0; reason: string };

export type GenericResult =
  | { mode: "desktop" | "mock"; success: boolean; error: string | null }
  | { mode: "browser"; success: boolean; error: string };

export async function fetchConglomerates(): Promise<ConglomeratesResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", items: [], count: 0, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_conglomerates", {});
  if (payload.error) throw new Error(payload.error);
  return { mode, items: payload.items ?? [], count: payload.count ?? 0 };
}

export async function fetchAssetMappings(): Promise<AssetMappingsResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", items: [], count: 0, reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_asset_mappings", {});
  if (payload.error) throw new Error(payload.error);
  return { mode, items: payload.items ?? [], count: payload.count ?? 0 };
}

export async function updateAssetMapping(
  assetId: string,
  assetType: "distributor" | "plant",
  cdCvm: number | null,
  customOwnerName?: string | null,
  reviewNotes?: string
): Promise<GenericResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", success: false, error: BROWSER_REASON };
  }
  const payload = await callBridge("update_asset_mapping", {
    asset_id: assetId,
    asset_type: assetType,
    cd_cvm: cdCvm,
    custom_owner_name: customOwnerName || null,
    review_notes: reviewNotes || null,
  });
  if (payload.error) return { mode, success: false, error: payload.error };
  return { mode, success: true, error: null };
}

export async function runAutomaticMapping(): Promise<GenericResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", success: false, error: BROWSER_REASON };
  }
  const payload = await callBridge("run_automatic_mapping", {});
  if (payload.error) return { mode, success: false, error: payload.error };
  return { mode, success: true, error: null };
}
