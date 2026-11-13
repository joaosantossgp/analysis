/**
 * Coverage API facade.
 * Funnels React Query calls through the pywebview bridge.
 */
import { callBridge, getBridgeMode, whenBridgeReady } from "../bridge/adapter";

export interface CoverageUniverse {
  id: string;
  name: string;
  purpose: string | null;
  analysis_type: string;
  benchmark: string | null;
  status: "draft" | "active" | "archived";
  company_count: number;
  created_at: string;
  updated_at: string;
}

export async function fetchCoverageUniverses(): Promise<CoverageUniverse[]> {
  const mode = await whenBridgeReady();
  if (mode === "browser") {
    throw new Error("Coverage requires the desktop bridge. Your saved universe selection is preserved.");
  }
  const res = await callBridge("get_coverage_universes", {});
  if (res.error) throw new Error(res.error);
  return res as CoverageUniverse[];
}

export async function fetchCoverageUniverse(id: string): Promise<any> {
  const mode = getBridgeMode();
  if (mode === "browser") return null;
  const res = await callBridge("get_coverage_universe", { id });
  if (res.error) throw new Error(res.error);
  return res;
}

export async function createCoverageUniverse(params: {
  name: string;
  purpose?: string;
  analysis_type?: string;
  benchmark?: string;
}): Promise<string> {
  const res = await callBridge("create_coverage_universe", params);
  if (res.error) throw new Error(res.error);
  return res.universe_id!;
}

export async function updateCoverageUniverse(params: {
  id: string;
  name: string;
  purpose?: string;
  benchmark?: string;
  status: string;
  assumptions?: any;
}): Promise<boolean> {
  const res = await callBridge("update_coverage_universe", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function deleteCoverageUniverse(id: string): Promise<boolean> {
  const res = await callBridge("delete_coverage_universe", { id });
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function duplicateCoverageUniverse(
  id: string,
  name: string,
  copy_companies: boolean = true,
  copy_checklists: boolean = false,
): Promise<string> {
  const res = await callBridge("duplicate_coverage_universe", {
    id,
    name,
    copy_companies,
    copy_checklists,
  });
  if (res.error) throw new Error(res.error);
  return res.universe_id!;
}

export async function bulkUpdateCompaniesInCoverageUniverse(params: {
  universe_id: string;
  company_ids: number[];
  tier: string;
  rationale: string;
}): Promise<boolean> {
  const res = await callBridge("bulk_update_companies_in_coverage_universe", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}



export async function addCompanyToCoverageUniverse(params: {
  universe_id: string;
  cd_cvm: number;
  tier: string;
  rationale: string;
  owner?: string;
  holding_pct?: number;
}): Promise<boolean> {
  const res = await callBridge("add_company_to_coverage_universe", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function removeCompanyFromCoverageUniverse(params: {
  universe_id: string;
  cd_cvm: number;
  rationale: string;
}): Promise<boolean> {
  const res = await callBridge("remove_company_from_coverage_universe", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function fetchCoveragePriorityScores(universe_id: string): Promise<any[]> {
  const mode = getBridgeMode();
  if (mode === "browser") return [];
  const res = await callBridge("calculate_coverage_priority_scores", { universe_id });
  if (res.error) throw new Error(res.error);
  return res.items || [];
}

export async function saveManualScoreOverride(params: {
  universe_id: string;
  cd_cvm: number;
  override: number | null;
  rationale: string;
}): Promise<boolean> {
  const res = await callBridge("save_manual_score_override", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function fetchCompanyCoverageChecklists(universe_id: string, cd_cvm: number): Promise<any[]> {
  const mode = getBridgeMode();
  if (mode === "browser") return [];
  const res = await callBridge("get_company_coverage_checklists", { universe_id, cd_cvm });
  if (res.error) throw new Error(res.error);
  return res.items || [];
}

export async function updateCompanyCoverageChecklistItem(params: {
  universe_id: string;
  cd_cvm: number;
  item_key: string;
  is_completed: boolean;
  comments?: string;
  rationale: string;
}): Promise<boolean> {
  const res = await callBridge("update_company_coverage_checklist_item", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function fetchCoverageWorkQueue(universe_id: string): Promise<any[]> {
  const mode = getBridgeMode();
  if (mode === "browser") return [];
  const res = await callBridge("get_coverage_work_queue", { universe_id });
  if (res.error) throw new Error(res.error);
  return res.items || [];
}

export async function fetchCoverageCapacityData(universe_id: string): Promise<any> {
  const mode = getBridgeMode();
  if (mode === "browser") return null;
  const res = await callBridge("get_coverage_capacity_data", { universe_id });
  if (res.error) throw new Error(res.error);
  return res;
}

export async function saveCoverageCapacityScenario(params: {
  universe_id: string;
  available_hours: number;
  tier_hours: Record<string, number>;
}): Promise<boolean> {
  const res = await callBridge("save_coverage_capacity_scenario", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function fetchCoverageDecisionHistory(universe_id: string, cd_cvm?: number): Promise<any[]> {
  const mode = getBridgeMode();
  if (mode === "browser") return [];
  const res = await callBridge("get_coverage_decision_history", { universe_id, cd_cvm });
  if (res.error) throw new Error(res.error);
  return res.items || [];
}

export async function downloadCoverageUniverseExcel(universeId: string): Promise<{ filename: string; content_base64: string }> {
  const mode = getBridgeMode();
  if (mode === "browser") throw new Error("Excel export not available in browser mode");
  const res = await callBridge("download_coverage_universe_excel", { universe_id: universeId });
  if (res.error) throw new Error(res.error);
  return {
    filename: res.filename!,
    content_base64: res.content_base64!,
  };
}

export async function updateCompanyOwnerAnalyst(params: {
  universe_id: string;
  cd_cvm: number;
  owner: string | null;
  rationale: string;
}): Promise<boolean> {
  const res = await callBridge("update_company_owner_analyst", params);
  if (res.error) throw new Error(res.error);
  return !!res.success;
}

export async function fetchCoverageRecommendation(universe_id: string): Promise<any> {
  const mode = getBridgeMode();
  if (mode === "browser") return null;
  const res = await callBridge("get_coverage_recommendation", { universe_id });
  if (res.error) throw new Error(res.error);
  return res;
}

export async function saveCoverageManagerDecision(params: {
  universe_id: string;
  status: "draft" | "pending_review" | "approved" | "rejected";
  notes?: string;
}): Promise<{ success: boolean; status: string; decided_at: string }> {
  const res = await callBridge("save_coverage_manager_decision", params);
  if (res.error) throw new Error(res.error);
  return { success: true, status: res.status!, decided_at: res.decided_at! };
}

