import { callBridge, getBridgeMode } from "../bridge/adapter";
import type { CompanyClassification, GicsSubIndustry } from "../bridge/types";

const BROWSER_REASON = "Editing a classification needs the desktop bridge.";

type ClassificationWriteResult = { ok: boolean; error?: string; classification?: CompanyClassification };

export async function fetchGicsStructure(): Promise<GicsSubIndustry[]> {
  if (getBridgeMode() === "browser") return [];
  const result = await callBridge("get_gics_structure", {});
  if (!result.ok) throw new Error(result.error ?? "Could not load the GICS structure.");
  return result.items;
}

async function write(method: "set_company_classification" | "clear_company_classification", params: Record<string, unknown>) {
  if (getBridgeMode() === "browser") throw new Error(BROWSER_REASON);
  const result = (await callBridge(method, params)) as ClassificationWriteResult;
  if (!result.ok || !result.classification) {
    throw new Error(result.error ?? "Could not save the classification.");
  }
  return result.classification;
}

export function setCompanyClassification(cdCvm: number, subIndustryCode: string) {
  return write("set_company_classification", { cd_cvm: cdCvm, sub_industry_code: subIndustryCode });
}

export function clearCompanyClassification(cdCvm: number) {
  return write("clear_company_classification", { cd_cvm: cdCvm });
}

/** Case-insensitive match on any GICS level name or the sub-industry code. */
export function filterGicsOptions(items: GicsSubIndustry[], query: string, limit = 40): GicsSubIndustry[] {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matches = terms.length
    ? items.filter((item) => {
        const haystack = [item.sub_industry_code, item.sub_industry, item.industry, item.industry_group, item.sector]
          .join(" ")
          .toLowerCase();
        return terms.every((term) => haystack.includes(term));
      })
    : items;
  return matches.slice(0, limit);
}
