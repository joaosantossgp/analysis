// Mirror of the Python bridge surface in desktop/bridge.py.
//
// This file is the single typed contract for the pywebview JS API. Components
// MUST NOT reference window.pywebview directly — they go through the adapter
// in ./adapter.ts which validates availability and forwards calls.

export type HealthPayload = {
  status: "ok" | "degraded" | string;
  version: string;
  database_dialect: string | null;
  required_tables: string[];
  warnings: Array<{ severity: string; code: string; message: string; path: string | null }>;
  errors: Array<{ severity: string; code: string; message: string; path: string | null }>;
};

export type CompanyDirectoryItem = {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
  setor_analitico: string | null;
  setor_cvm: string | null;
  sector_name: string;
  sector_slug: string;
  anos_disponiveis: number[];
  total_rows: number;
  has_financial_data: boolean;
  coverage_rank: number | null;
  gics_sector?: string | null;
  gics_sector_slug?: string | null;
  gics_industry_group?: string | null;
  gics_industry?: string | null;
  gics_sub_industry?: string | null;
};

export type CompanyDirectoryPagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
};

export type CompanyDirectoryFilters = {
  search: string;
  sector: string | null;
};

export type CompanyDirectoryPage = {
  items: CompanyDirectoryItem[];
  pagination: CompanyDirectoryPagination;
  applied_filters: CompanyDirectoryFilters;
  /** Bridge instrumentation. Optional, present when CVMBridge times the call. */
  _bridge_ms?: number;
  /** Present only on error (bridge swallows exceptions). */
  error?: string;
};

/** Loose parameter shape — CVMBridge.get_companies uses .get() on every key. */
export type CompaniesQuery = {
  search?: string;
  sector_slug?: string | null;
  page?: number;
  page_size?: number;
};

export type PingResult = {
  pong: boolean;
  ts: number;
};

/**
 * Complete bridge method surface. Add new methods here as Phase 1 grows.
 * Keep parameter shapes loose (Record<string, unknown>) — Python normalises
 * with .get(...) so the JS side does not need to construct exact dicts.
 */
export interface BridgeApi {
  ping(params?: Record<string, unknown>): Promise<PingResult>;
  get_health(params?: Record<string, unknown>): Promise<HealthPayload>;
  get_companies(params: Record<string, unknown>): Promise<CompanyDirectoryPage>;
}

declare global {
  interface Window {
    pywebview?: {
      api: BridgeApi;
    };
  }
}

export {};
