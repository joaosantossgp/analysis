/**
 * Sectors API facade.
 *
 * Wraps CVMBridge.get_sectors / get_sector_detail. Mirrors the parity with
 * the Next /setores routes: the Python read-service is the authoritative
 * source of GICS sector aggregation. Vite never aggregates locally.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  SectorDetailResponse,
  SectorDirectoryItem,
  SectorDirectoryResponse,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable. Launch with python -m desktop.app --vite or the packaged exe.";

export type SectorGroupBy = "sector" | "sub_sector";

export type SectorDirectoryResult =
  | { mode: "desktop"; items: SectorDirectoryItem[] }
  | { mode: "browser"; items: []; reason: string };

export type SectorDetailResult =
  | { mode: "desktop"; detail: SectorDetailResponse; notFound: false }
  | { mode: "desktop"; detail: null; notFound: true }
  | { mode: "browser"; detail: null; notFound: false; reason: string };

export async function fetchSectors(
  groupBy: SectorGroupBy = "sector",
): Promise<SectorDirectoryResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", items: [], reason: BROWSER_REASON };
  }
  const payload: SectorDirectoryResponse = await callBridge("get_sectors", {
    group_by: groupBy,
  });
  if (payload.error) {
    throw new Error(payload.error);
  }
  return { mode: "desktop", items: payload.items ?? [] };
}

export async function fetchSectorDetail(
  sectorSlug: string,
  year: number | null = null,
): Promise<SectorDetailResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", detail: null, notFound: false, reason: BROWSER_REASON };
  }
  const params: Record<string, unknown> = { sector_slug: sectorSlug };
  if (year !== null && Number.isFinite(year)) {
    params.year = year;
  }
  const payload: SectorDetailResponse = await callBridge(
    "get_sector_detail",
    params,
  );
  if (payload.error) {
    throw new Error(payload.error);
  }
  if (payload.not_found) {
    return { mode: "desktop", detail: null, notFound: true };
  }
  return { mode: "desktop", detail: payload, notFound: false };
}

export async function fetchSubSectorDetail(
  sectorSlug: string,
  subIndustrySlug: string,
  year: number | null = null,
): Promise<SectorDetailResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", detail: null, notFound: false, reason: BROWSER_REASON };
  }
  const params: Record<string, unknown> = {
    sector_slug: sectorSlug,
    sub_industry_slug: subIndustrySlug,
  };
  if (year !== null && Number.isFinite(year)) {
    params.year = year;
  }
  const payload: SectorDetailResponse = await callBridge(
    "get_sub_sector_detail",
    params,
  );
  if (payload.error) {
    throw new Error(payload.error);
  }
  if (payload.not_found) {
    return { mode: "desktop", detail: null, notFound: true };
  }
  return { mode: "desktop", detail: payload, notFound: false };
}

