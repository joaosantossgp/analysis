/**
 * Excel export / output facade.
 *
 * Wraps CVMBridge.export_company_excel + get_output_dir. Files land under
 * the persistent runtime data root (Documents/CVMAnalytics/output in the
 * packaged exe). The bridge handles unique-name suffixing so previous
 * exports are never overwritten.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type { ExportCompanyResult, ExportMarketHistoryResult, OutputDirInfo } from "../bridge/types";

const BROWSER_REASON =
  "Excel export needs the pywebview bridge. Launch with python -m desktop.app --vite or the packaged exe.";

export type ExportCompanyOutcome =
  | { mode: "desktop"; result: ExportCompanyResult }
  | { mode: "browser"; result: null; reason: string };

export type OutputDirOutcome =
  | { mode: "desktop"; info: OutputDirInfo }
  | { mode: "browser"; info: null; reason: string };

export type ExportMarketHistoryParams = {
  cdCvm: number;
  ticker: string;
  period: string;
  customStart?: string | null;
  customEnd?: string | null;
  interval: string;
  view: string;
  selectedSeries: string[];
  valueMode?: string | null;
  chartType?: string | null;
};

export type ExportMarketHistoryOutcome =
  | { mode: "desktop"; result: ExportMarketHistoryResult }
  | { mode: "browser"; result: null; reason: string };

export async function exportCompanyWorkbook(
  cdCvm: number,
  options: {
    reveal?: boolean;
    statementType?: string;
    periodScope?: string;
    mappingPresetId?: string;
  } = {},
): Promise<ExportCompanyOutcome> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const result = await callBridge("export_company_excel", {
    cd_cvm: cdCvm,
    reveal: options.reveal ?? false,
    statement_type: options.statementType,
    period_scope: options.periodScope ?? "last_5_years",
    mapping_preset_id: options.mappingPresetId,
  });
  return { mode: "desktop", result };
}

export async function fetchOutputDir(): Promise<OutputDirOutcome> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", info: null, reason: BROWSER_REASON };
  }
  const info = await callBridge("get_output_dir", {});
  return { mode: "desktop", info };
}

export async function exportMarketHistoryWorkbook(
  params: ExportMarketHistoryParams,
): Promise<ExportMarketHistoryOutcome> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const result = await callBridge("export_company_market_history_excel", {
    cd_cvm: params.cdCvm,
    ticker: params.ticker,
    period: params.period,
    custom_start: params.customStart ?? null,
    custom_end: params.customEnd ?? null,
    interval: params.interval,
    view: params.view,
    selected_series: params.selectedSeries,
    value_mode: params.valueMode ?? null,
    chart_type: params.chartType ?? null,
  });
  return { mode: "desktop", result };
}
