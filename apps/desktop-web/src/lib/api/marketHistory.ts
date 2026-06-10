import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  CompanyMarketHistoryStatus,
  CompanyMarketHistoryResult,
  CompanyMarketHistoryRefreshResult,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable. Launch via scripts/diagnostics/phase1_pywebview_smoke.py or the packaged exe to fetch live market data.";

export type MarketHistoryStatusResult =
  | { mode: "desktop"; status: CompanyMarketHistoryStatus }
  | { mode: "browser"; status: null; reason: string };

export async function fetchMarketHistoryStatus(
  cdCvm: number,
  ticker?: string | null,
): Promise<MarketHistoryStatusResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", status: null, reason: BROWSER_REASON };
  }
  const status = await callBridge("get_company_market_history_status", {
    cd_cvm: cdCvm,
    ticker: ticker ?? null,
  });
  if (status.error) {
    throw new Error(status.error);
  }
  return { mode: "desktop", status };
}

export type MarketHistoryResultUI =
  | { mode: "desktop"; data: CompanyMarketHistoryResult }
  | { mode: "browser"; data: null; reason: string };

export async function fetchMarketHistory(
  cdCvm: number,
  ticker?: string | null,
  start_date?: string | null,
  end_date?: string | null,
  period?: string | null,
  interval?: string,
): Promise<MarketHistoryResultUI> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", data: null, reason: BROWSER_REASON };
  }
  const data = await callBridge("get_company_market_history", {
    cd_cvm: cdCvm,
    ticker: ticker ?? null,
    start_date: start_date ?? null,
    end_date: end_date ?? null,
    period: period ?? null,
    interval: interval ?? "1d",
  });
  if (data.error) {
    throw new Error(data.error);
  }
  return { mode: "desktop", data };
}

export type MarketHistoryRefreshResultUI =
  | { mode: "desktop"; result: CompanyMarketHistoryRefreshResult }
  | { mode: "browser"; result: null; reason: string };

export async function triggerMarketHistoryRefresh(
  cdCvm: number,
  ticker?: string | null,
): Promise<MarketHistoryRefreshResultUI> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const result = await callBridge("refresh_company_market_history", {
    cd_cvm: cdCvm,
    ticker: ticker ?? null,
  });
  if (result.error) {
    throw new Error(result.error);
  }
  return { mode: "desktop", result };
}
