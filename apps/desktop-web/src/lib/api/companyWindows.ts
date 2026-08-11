import { callBridge, getBridgeMode } from "../bridge/adapter";
import type { OpenCompanyExcelMappingWindowResult } from "../bridge/types";

const BROWSER_REASON =
  "Excel Mapping opens in a separate window only in the desktop app.";

export type CompanyExcelMappingWindowResult =
  | { mode: "desktop"; result: OpenCompanyExcelMappingWindowResult }
  | { mode: "browser"; result: null; reason: string };

export async function openCompanyExcelMappingWindow(
  cdCvm: number,
): Promise<CompanyExcelMappingWindowResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const result = await callBridge("open_company_excel_mapping_window", { cd_cvm: cdCvm });
  return { mode: "desktop", result };
}
