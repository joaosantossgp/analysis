import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  DataCoverageResponse,
  SetCompanyIgnoredResponse,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode - pywebview bridge is unavailable. Launch with python -m desktop.app --vite or the packaged exe.";

export type DataCoverageResult =
  | { mode: "desktop"; data: DataCoverageResponse }
  | { mode: "browser"; data: null; reason: string };

export async function fetchDataCoverage(): Promise<DataCoverageResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", data: null, reason: BROWSER_REASON };
  }
  const data = (await callBridge(
    "get_data_coverage",
    {},
  )) as DataCoverageResponse;
  if (data.error) {
    throw new Error(data.error);
  }
  return { mode: "desktop", data };
}

export async function setCompanyIgnored(params: {
  cdCvm: number;
  ignored: boolean;
  reason?: string | null;
  companyName?: string | null;
}): Promise<SetCompanyIgnoredResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = await callBridge("set_company_ignored", {
    cd_cvm: params.cdCvm,
    ignored: params.ignored,
    reason: params.reason ?? null,
    company_name: params.companyName ?? null,
  });
  if (!response.ok) {
    throw new Error(response.error ?? "Falha ao atualizar status de ignorado.");
  }
  return response;
}
