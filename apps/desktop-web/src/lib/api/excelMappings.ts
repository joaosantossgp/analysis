import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  ExcelMappingDefinition,
  ExcelMappingWorkspace,
  SaveExcelMappingPresetResult,
  SetCompanyExcelMappingDefaultResult,
} from "../bridge/types";

const BROWSER_REASON =
  "Model Mapping needs the pywebview bridge. Launch with the desktop shell or the packaged app.";

export type ExcelMappingWorkspaceResult =
  | { mode: "desktop"; workspace: ExcelMappingWorkspace }
  | { mode: "browser"; workspace: null; reason: string };

export async function fetchExcelMappingWorkspace(
  cdCvm: number,
  presetId?: string | null,
  periodScope = "last_5_years",
): Promise<ExcelMappingWorkspaceResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", workspace: null, reason: BROWSER_REASON };
  }
  const workspace = await callBridge("get_excel_mapping_workspace", {
    cd_cvm: cdCvm,
    preset_id: presetId ?? undefined,
    period_scope: periodScope,
  });
  if (workspace.error) {
    throw new Error(workspace.error);
  }
  return { mode: "desktop", workspace };
}

export async function saveExcelMappingPreset(
  mapping: ExcelMappingDefinition,
): Promise<ExcelMappingDefinition> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const result = (await callBridge("save_excel_mapping_preset", {
    mapping,
  })) as SaveExcelMappingPresetResult;
  if (!result.ok || !result.preset) {
    throw new Error(result.error ?? "Could not save mapping preset.");
  }
  return result.preset;
}

export async function setCompanyExcelMappingDefault(
  cdCvm: number,
  presetId: string,
): Promise<SetCompanyExcelMappingDefaultResult> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const result = (await callBridge("set_company_excel_mapping_default", {
    cd_cvm: cdCvm,
    preset_id: presetId,
  })) as SetCompanyExcelMappingDefaultResult;
  if (!result.ok) {
    throw new Error(result.error ?? "Could not set company mapping default.");
  }
  return result;
}
