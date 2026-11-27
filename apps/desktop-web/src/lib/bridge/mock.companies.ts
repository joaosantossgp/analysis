import type {
  BridgeApi,
  CompanyDirectoryItem,
  CompanyDirectoryPage,
  CompanyFiltersResponse,
  CompanyInfo,
  CompanyYearsResult,
  KPIBundle,
  SectorDirectoryResponse,
  SectorDetailResponse,
  StatementMatrix,
  TabularData,
  TabularRow,
} from "./types";
import { NOW, YEAR, FIXTURE_COMPANIES, SECTOR_SLUGS, toDirectoryItem } from "./mock.fixtures";

function makeTabularData(cols: string[], rows: (string | number | null)[][]): TabularData {
  return {
    columns: cols,
    rows: rows.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]]))),
  };
}

/**
 * KPI fixtures mirror the real engine output shape (src/financials/kpi_engine.py):
 * rows carry KPI_ID / KPI_NOME / CATEGORIA / FORMAT_TYPE / IS_PLACEHOLDER and
 * one column per period (annual "2023" or quarterly "1Q24"), plus DELTA_YOY_PCT.
 * Percentages are stored as fractions (0.31 → 31%), ratios as multiples (1.8x),
 * matching the engine and the app formatters. Valuation rows are placeholders
 * (null everywhere) exactly as the engine emits them without market data.
 */
interface MockKpiSpec {
  id: string;
  nome: string;
  categoria: string;
  fmt: "pct" | "ratio";
  base: number;
  drift: number;
  placeholder?: boolean;
}

const MOCK_KPI_SPECS: MockKpiSpec[] = [
  { id: "MG_BRUTA", nome: "Margem Bruta", categoria: "Rentabilidade", fmt: "pct", base: 0.42, drift: 0.03 },
  { id: "MG_EBITDA", nome: "Margem EBITDA", categoria: "Rentabilidade", fmt: "pct", base: 0.31, drift: 0.04 },
  { id: "MG_EBIT", nome: "Margem EBIT", categoria: "Rentabilidade", fmt: "pct", base: 0.24, drift: 0.03 },
  { id: "MG_LIQ", nome: "Margem Líquida", categoria: "Rentabilidade", fmt: "pct", base: 0.16, drift: 0.03 },
  { id: "ROE", nome: "ROE", categoria: "Rentabilidade", fmt: "pct", base: 0.18, drift: 0.05 },
  { id: "ROA", nome: "ROA", categoria: "Rentabilidade", fmt: "pct", base: 0.09, drift: 0.02 },
  { id: "ROIC", nome: "ROIC *", categoria: "Rentabilidade", fmt: "pct", base: NaN, drift: 0, placeholder: true },
  { id: "LIQ_CORR", nome: "Liquidez Corrente", categoria: "Liquidez", fmt: "ratio", base: 1.4, drift: 0.2 },
  { id: "LIQ_SECA", nome: "Liquidez Seca", categoria: "Liquidez", fmt: "ratio", base: 1.1, drift: 0.15 },
  { id: "LIQ_IMED", nome: "Liquidez Imediata", categoria: "Liquidez", fmt: "ratio", base: 0.6, drift: 0.1 },
  { id: "DIV_EBITDA", nome: "Dívida Líq./EBITDA", categoria: "Endividamento", fmt: "ratio", base: 1.8, drift: 0.4 },
  { id: "PL_PASS", nome: "PL / Passivo Total", categoria: "Endividamento", fmt: "pct", base: 0.45, drift: 0.04 },
  { id: "PC_PASS", nome: "Passivo Circ./Total", categoria: "Endividamento", fmt: "pct", base: 0.38, drift: 0.03 },
  { id: "FCO_REC", nome: "FCO / Receita", categoria: "Fluxo de Caixa", fmt: "pct", base: 0.22, drift: 0.04 },
  { id: "FCL_REC", nome: "FCL / Receita", categoria: "Fluxo de Caixa", fmt: "pct", base: 0.12, drift: 0.05 },
  { id: "CAPEX_REC", nome: "CAPEX / Receita *", categoria: "Fluxo de Caixa", fmt: "pct", base: 0.1, drift: 0.02 },
  { id: "CRESC_REC", nome: "Crescimento Receita", categoria: "Crescimento", fmt: "pct", base: 0.08, drift: 0.06 },
  { id: "CRESC_LUC", nome: "Crescimento Lucro", categoria: "Crescimento", fmt: "pct", base: 0.11, drift: 0.09 },
  { id: "CAGR_REC", nome: "CAGR Receita (5a) *", categoria: "Crescimento", fmt: "pct", base: NaN, drift: 0, placeholder: true },
  { id: "EV_EBITDA", nome: "EV/EBITDA *", categoria: "Valuation", fmt: "ratio", base: NaN, drift: 0, placeholder: true },
  { id: "PL_PRECO", nome: "P/L *", categoria: "Valuation", fmt: "ratio", base: NaN, drift: 0, placeholder: true },
  { id: "DY", nome: "Dividend Yield *", categoria: "Valuation", fmt: "pct", base: NaN, drift: 0, placeholder: true },
];

function buildMockKpiTable(periods: string[], seed: number): TabularData {
  const meta = ["KPI_ID", "KPI_NOME", "CATEGORIA", "FORMAT_TYPE", "IS_PLACEHOLDER", "HIGHER_IS_BETTER", "UNIDADE"];
  const columns = [...meta, ...periods, "DELTA_YOY_PCT"];
  const rows: TabularRow[] = MOCK_KPI_SPECS.map((spec, specIdx) => {
    const row: TabularRow = {
      KPI_ID: spec.id,
      KPI_NOME: spec.nome,
      CATEGORIA: spec.categoria,
      FORMAT_TYPE: spec.fmt,
      IS_PLACEHOLDER: spec.placeholder ?? false,
      HIGHER_IS_BETTER: false,
      UNIDADE: spec.fmt === "pct" ? "%" : "x",
    };
    periods.forEach((p, i) => {
      if (spec.placeholder) {
        row[p] = null;
        return;
      }
      // Deterministic, smooth wobble so charts show realistic trends.
      const wobble = Math.sin((i + seed + specIdx) * 0.6) * spec.drift;
      const v = spec.base + wobble + i * spec.drift * 0.15;
      row[p] = Number(v.toFixed(spec.fmt === "pct" ? 4 : 2));
    });
    const last = row[periods[periods.length - 1]];
    const prev = row[periods[periods.length - 2]];
    row.DELTA_YOY_PCT =
      typeof last === "number" && typeof prev === "number" && prev !== 0
        ? Number(((last - prev) / Math.abs(prev)).toFixed(4))
        : null;
    return row;
  });
  return { columns, rows };
}

/** Interleaved quarterly periods matching the engine: 1Q,2Q,3Q,annual per year (Q4 omitted). */
function mockQuarterlyPeriods(years: number[]): string[] {
  const out: string[] = [];
  for (const y of years) {
    const yy = String(y).slice(2);
    out.push(`1Q${yy}`, `2Q${yy}`, `3Q${yy}`, String(y));
  }
  return out;
}

function mockKpis(cdCvm: number, years: number[]): KPIBundle {
  const seed = cdCvm % 7;
  const annualYears = years.length > 0 ? years : [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1];
  return {
    cd_cvm: cdCvm,
    years: annualYears,
    annual: buildMockKpiTable(annualYears.map(String), seed),
    quarterly: buildMockKpiTable(mockQuarterlyPeriods(annualYears), seed + 1),
  };
}

function mockStatement(cdCvm: number, statementType: string): StatementMatrix {
  const years = [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1];
  const yearCols = years.map(String);
  const cols = ["Conta", "Descrição", ...yearCols];
  const rows: (string | number | null)[][] =
    statementType === "DRE"
      ? [
          ["3.01", "Receita de Venda de Bens e/ou Serviços", 40_000, 44_000, 38_000, 52_000],
          ["3.04", "Resultado Bruto", 18_000, 20_000, 16_500, 24_000],
          ["3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", 12_000, 14_000, 10_800, 16_500],
          ["3.09", "Lucro/Prejuízo Consolidado do Período", 7_200, 9_100, 6_800, 11_200],
        ]
      : [
          ["1", "Ativo Total", 280_000, 295_000, 310_000, 330_000],
          ["1.01", "Ativo Circulante", 55_000, 58_000, 62_000, 70_000],
          ["2", "Passivo Total", 190_000, 195_000, 205_000, 215_000],
          ["2.03", "Patrimônio Líquido Consolidado", 90_000, 100_000, 105_000, 115_000],
        ];
  return {
    cd_cvm: cdCvm,
    statement_type: statementType,
    years,
    table: makeTabularData(cols, rows),
    exclude_conflicts: true,
  };
}

// ---------------------------------------------------------------------------
// Base health fixture
// ---------------------------------------------------------------------------

const DOWNLOADED_MARKET_HISTORIES = new Set<number>([9512, 14311]);

function resolveMockTicker(cdCvm: number, requestedTicker?: string | null): string | null {
  if (requestedTicker) {
    let t = requestedTicker.trim().toUpperCase();
    if (t) {
      if (!t.includes(".")) {
        t = `${t}.SA`;
      }
      return t;
    }
  }

  const company = FIXTURE_COMPANIES.find((c) => c.cd_cvm === cdCvm);
  if (company && company.ticker_b3) {
    let t = company.ticker_b3.trim().toUpperCase();
    if (!t.includes(".")) {
      t = `${t}.SA`;
    }
    return t;
  }

  return null;
}

function resolveMockCompanyTickers(cdCvm: number, requestedTicker?: string | null): string[] {
  const primary = resolveMockTicker(cdCvm, requestedTicker);
  if (!primary) {
    return [];
  }
  
  const m = primary.match(/^([A-Z]{4})\d+/);
  if (!m) {
    return [primary];
  }
  const base = m[1];
  const suffixes = ["3", "4", "5", "6", "11"];
  const candidates = suffixes.map((s) => `${base}${s}.SA`);
  
  const result = [primary];
  for (const c of candidates) {
    if (!result.includes(c)) {
      result.push(c);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// createMockBridge — exported factory
// ---------------------------------------------------------------------------

export function createMockCompaniesMethods(): Partial<BridgeApi> {
  return {
    get_companies: async (params) => {
      const p = params as Record<string, unknown>;
      const search = String(p?.search ?? "").toLowerCase();
      const sectorSlug = String(p?.sector_slug ?? "");
      const page = Number(p?.page ?? 1);
      const pageSize = Number(p?.page_size ?? 50);

      let items = FIXTURE_COMPANIES.map(toDirectoryItem);
      if (search) items = items.filter((c) => c.company_name.toLowerCase().includes(search) || (c.ticker_b3 ?? "").toLowerCase().includes(search));
      if (sectorSlug) items = items.filter((c) => c.sector_slug === sectorSlug);

      if (p?.sort_by) {
        const valueFor = (item: CompanyDirectoryItem): string | number | null => {
          switch (p.sort_by) {
            case "company": return item.company_name.toLowerCase();
            case "ticker": return item.ticker_b3?.trim().toLowerCase() || null;
            case "sector": return item.gics_sector?.trim().toLowerCase() || null;
            case "industryGroup": return item.gics_industry_group?.trim().toLowerCase() || null;
            case "marketCap": return item.market_cap_brl ?? null;
            case "data": return Number(item.has_financial_data);
            case "years": return item.anos_disponiveis.length;
            case "cvm": return item.cd_cvm;
            default: throw new Error("Invalid company sort column");
          }
        };
        const direction = p.sort_direction ?? "desc";
        if (direction !== "asc" && direction !== "desc") throw new Error("Invalid company sort direction");
        const factor = direction === "asc" ? 1 : -1;
        items.sort((a, b) => {
          const left = valueFor(a), right = valueFor(b);
          if (left === null) return right === null ? a.cd_cvm - b.cd_cvm : 1;
          if (right === null) return -1;
          return (left < right ? -factor : left > right ? factor : a.cd_cvm - b.cd_cvm);
        });
      }
      const totalItems = items.length;
      const totalPages = Math.ceil(totalItems / pageSize) || 1;
      const start = (page - 1) * pageSize;
      const pageItems = items.slice(start, start + pageSize);

      const result: CompanyDirectoryPage = {
        items: pageItems,
        pagination: {
          page,
          page_size: pageSize,
          total_items: totalItems,
          total_pages: totalPages,
          has_next: page < totalPages,
          has_previous: page > 1,
        },
        applied_filters: { search: String(p?.search ?? ""), sector: sectorSlug || null },
      };
      return result;
    },

    get_company_info: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      if (!c) {
        return {
          cd_cvm: cdCvm,
          company_name: "Unknown",
          is_active: true,
          nome_comercial: null,
          cnpj: null,
          ticker_b3: null,
          company_type: null,
          setor_cvm: null,
          has_local_financial_reports: false,
          has_readable_current_data: false,
          readable_years_count: 0,
          latest_readable_year: null,
          readable_financial_periods_count: 0,
          latest_financial_period_label: null,
          latest_financial_period_display: null,
          latest_financial_period_type: null,
          latest_financial_period_year: null,
          latest_financial_period_quarter: null,
          read_model_updated_at: null,
          read_availability_code: null,
          read_availability_message: null,
          not_found: true,
        } satisfies CompanyInfo;
      }
      return {
        cd_cvm: c.cd_cvm,
        company_name: c.company_name,
        is_active: true,
        nome_comercial: c.company_name,
        cnpj: c.cnpj,
        ticker_b3: c.ticker_b3,
        company_type: "SA",
        setor_cvm: c.sector_name,
        sector_name: c.sector_name,
        sector_slug: c.sector_slug,
        has_local_financial_reports: c.has_financial_data,
        has_readable_current_data: c.has_financial_data,
        readable_years_count: c.anos_disponiveis.length,
        latest_readable_year: c.anos_disponiveis.at(-1) ?? null,
        readable_financial_periods_count: c.anos_disponiveis.length,
        latest_financial_period_label: c.anos_disponiveis.at(-1)?.toString() ?? null,
        latest_financial_period_display: c.anos_disponiveis.at(-1)
          ? `FY${c.anos_disponiveis.at(-1)}`
          : null,
        latest_financial_period_type: c.has_financial_data ? "annual" : null,
        latest_financial_period_year: c.anos_disponiveis.at(-1) ?? null,
        latest_financial_period_quarter: null,
        read_model_updated_at: c.has_financial_data
          ? new Date(Date.now() - 86_400_000).toISOString()
          : null,
        read_availability_code: c.has_financial_data ? "readable" : "no_data",
        read_availability_message: c.has_financial_data ? "Data available" : "No financial data",
        gics_sector: c.cd_cvm === 9512 ? "Energy" : c.cd_cvm === 14311 ? "Materials" : c.cd_cvm === 14673 ? "Consumer Staples" : null,
        gics_sector_slug: c.cd_cvm === 9512 ? "energy" : c.cd_cvm === 14311 ? "materials" : c.cd_cvm === 14673 ? "consumer-staples" : null,
        gics_industry_group: null,
        gics_industry: c.cd_cvm === 9512 ? "Oil, Gas & Consumable Fuels" : null,
        gics_sub_industry: c.cd_cvm === 9512 ? "Integrated Oil & Gas" : c.cd_cvm === 14311 ? "Steel" : c.cd_cvm === 14673 ? "Brewers" : null,
      } satisfies CompanyInfo;
    },

    get_company_financial_readiness: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const company = FIXTURE_COMPANIES.find((item) => item.cd_cvm === cdCvm);
      const years = company?.anos_disponiveis ?? [];
      const hasFinancialData = Boolean(company?.has_financial_data);
      const timestamp = hasFinancialData
        ? new Date(Date.now() - 86_400_000).toISOString()
        : null;

      return {
        cd_cvm: cdCvm,
        source_class: "official_reported",
        source_label: "Mock fixture · CVM DFP/ITR filings",
        availability_state: hasFinancialData ? "ready" : "missing",
        freshness_state: hasFinancialData ? "fresh" : "unknown",
        refresh_state: hasFinancialData ? "successful" : "not_recorded",
        has_local_financial_reports: hasFinancialData,
        available_periods: years.map((year) => ({
          period_label: `FY${year}`,
          period_display: `FY ${year}`,
          period_type: "annual",
          period_year: year,
          period_quarter: null,
        })),
        local_read_model_updated_at: timestamp,
        last_successful_refresh_at: timestamp,
        latest_local_evidence_at: timestamp,
        last_refresh_error: null,
        financial_export_eligible: hasFinancialData && years.length > 0,
        exportable_years: hasFinancialData ? years : [],
        refresh_available: true,
      };
    },

    get_company_years: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      return { years: c?.anos_disponiveis ?? [] } satisfies CompanyYearsResult;
    },

    get_company_statement_years: async (params) => {
      const cdCvm = Number(params?.cd_cvm ?? 0);
      return { years: FIXTURE_COMPANIES.find((company) => company.cd_cvm === cdCvm)?.anos_disponiveis ?? [] };
    },

    get_company_kpis: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      if (!c?.has_financial_data) {
        return { cd_cvm: cdCvm, years: [], annual: { columns: [], rows: [] }, quarterly: { columns: [], rows: [] }, error: "No financial data available" };
      }
      return mockKpis(cdCvm, c.anos_disponiveis);
    },

    get_company_statement: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const statementType = String(p?.statement_type ?? p?.stmt ?? "DRE");
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      if (!c?.has_financial_data) {
        return { cd_cvm: cdCvm, statement_type: statementType, years: [], table: { columns: [], rows: [] }, exclude_conflicts: true, error: "No financial data" } satisfies StatementMatrix;
      }
      return mockStatement(cdCvm, statementType);
    },

    get_company_filters: async () => ({
      sectors: SECTOR_SLUGS.map((s) => ({
        sector_name: s.name,
        sector_slug: s.slug,
        company_count: s.count,
        gics_sector: null,
        gics_sector_slug: null,
        gics_sub_industry: null,
      })),
    } satisfies CompanyFiltersResponse),

    get_sectors: async (params) => {
      const p = params as Record<string, unknown>;
      const groupBy = String(p?.group_by ?? "sector");

      if (groupBy === "sub_sector") {
        const subSectors = [
          { name: "Integrated Oil & Gas", slug: "integrated-oil-gas", parent: "Energy", parentSlug: "energy" },
          { name: "Steel", slug: "steel", parent: "Materials", parentSlug: "materials" },
          { name: "Brewers", slug: "brewers", parent: "Consumer Staples", parentSlug: "consumer-staples" },
          { name: "Alternative Carriers", slug: "alternative-carriers", parent: "Communication Services", parentSlug: "communication-services" },
        ];
        return {
          items: subSectors.map((s) => ({
            sector_name: s.name,
            sector_slug: s.slug,
            company_count: 1,
            latest_year: YEAR - 1,
            snapshot: { roe: 10, mg_ebit: 15, mg_liq: 7 },
            sub_industries: [],
            sub_industry_breakdown: [],
            group_type: "sub_sector",
            parent_sector_name: s.parent,
            parent_sector_slug: s.parentSlug,
            companies: [],
          })),
        } satisfies SectorDirectoryResponse;
      }

      if (groupBy === "cvm_sector") {
        return {
          items: SECTOR_SLUGS.map((s) => ({
            sector_name: s.name,
            sector_slug: s.slug,
            company_count: s.count,
            latest_year: YEAR - 1,
            snapshot: { roe: null, mg_ebit: null, mg_liq: null },
            sub_industries: [],
            sub_industry_breakdown: [],
            group_type: "cvm_sector",
            parent_sector_name: null,
            parent_sector_slug: null,
            companies: [],
          })),
        } satisfies SectorDirectoryResponse;
      }

      // Default to "sector" (GICS Sectors)
      const gicsSectors = [
        { name: "Energy", slug: "energy" },
        { name: "Materials", slug: "materials" },
        { name: "Consumer Staples", slug: "consumer-staples" },
        { name: "Communication Services", slug: "communication-services" },
      ];
      return {
        items: gicsSectors.map((s) => ({
          sector_name: s.name,
          sector_slug: s.slug,
          company_count: 1,
          latest_year: YEAR - 1,
          snapshot: { roe: 12, mg_ebit: 18, mg_liq: 8 },
          sub_industries: [],
          sub_industry_breakdown: [],
          group_type: "sector",
          parent_sector_name: null,
          parent_sector_slug: null,
          companies: [],
        })),
      } satisfies SectorDirectoryResponse;
    },

    get_sector_detail: async (params) => {
      const p = params as Record<string, unknown>;
      const slug = String(p?.sector_slug ?? "");
      const sector = SECTOR_SLUGS.find((s) => s.slug === slug);
      const companies = FIXTURE_COMPANIES.filter((c) => c.sector_slug === slug);
      return {
        sector_name: sector?.name ?? slug,
        sector_slug: slug,
        company_count: companies.length,
        available_years: [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1],
        selected_year: YEAR - 1,
        yearly_overview: [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1].map((y) => ({ year: y, roe: 12, mg_ebit: 18, mg_liq: 8 })),
        companies: companies.map((c) => ({
          cd_cvm: c.cd_cvm,
          company_name: c.company_name,
          ticker_b3: c.ticker_b3,
          gics_sub_industry: null,
          roe: 12,
          mg_ebit: 18,
          mg_liq: 8,
        })),
        parent_sector_name: null,
        parent_sector_slug: null,
        not_found: !sector,
      } satisfies SectorDetailResponse;
    },

    get_sub_sector_detail: async (params) => {
      // Delegate to sector detail for mock purposes
      const p = params as Record<string, unknown>;
      const slug = String(p?.sector_slug ?? "");
      const sector = SECTOR_SLUGS.find((s) => s.slug === slug);
      return {
        sector_name: sector?.name ?? slug,
        sector_slug: slug,
        company_count: 0,
        available_years: [YEAR - 1],
        selected_year: YEAR - 1,
        yearly_overview: [],
        companies: [],
        parent_sector_name: null,
        parent_sector_slug: null,
      } satisfies SectorDetailResponse;
    },

    get_company_market_history_status: async (params: { cd_cvm: number; ticker?: string | null }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const ticker = resolveMockTicker(cdCvm, params?.ticker);
      
      if (!ticker) {
        return {
          cd_cvm: cdCvm,
          ticker: null,
          available_tickers: [],
          has_local_data: false,
          first_date: null,
          last_date: null,
          row_count: 0,
          last_downloaded_at: null,
          is_stale: true,
          warnings: ["No ticker resolved for this CVM code."],
        };
      }

      const hasLocalData = DOWNLOADED_MARKET_HISTORIES.has(cdCvm);
      
      return {
        cd_cvm: cdCvm,
        ticker,
        available_tickers: resolveMockCompanyTickers(cdCvm, params?.ticker),
        has_local_data: hasLocalData,
        first_date: hasLocalData ? "2024-06-08" : null,
        last_date: hasLocalData ? "2026-06-08" : null,
        row_count: hasLocalData ? 730 : 0,
        last_downloaded_at: hasLocalData ? NOW : null,
        is_stale: !hasLocalData,
        warnings: [],
      };
    },

    get_company_market_history: async (params: {
      cd_cvm: number;
      ticker?: string | null;
      start_date?: string | null;
      end_date?: string | null;
      period?: string | null;
      interval?: string;
    }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const ticker = resolveMockTicker(cdCvm, params?.ticker);
      
      if (!ticker) {
        return {
          cd_cvm: cdCvm,
          ticker: "",
          source: "yahoo_finance",
          provider_status: "unofficial_free",
          requested_start_date: String(params?.start_date ?? null),
          requested_end_date: String(params?.end_date ?? null),
          actual_start_date: null,
          actual_end_date: null,
          interval: String(params?.interval ?? "1d"),
          last_downloaded_at: null,
          is_stale: true,
          has_local_data: false,
          warnings: ["No ticker resolved for this CVM code."],
          observations: [],
          summary: null,
        };
      }

      const hasLocalData = DOWNLOADED_MARKET_HISTORIES.has(cdCvm);
      if (!hasLocalData) {
        return {
          cd_cvm: cdCvm,
          ticker,
          source: "yahoo_finance",
          provider_status: "unofficial_free",
          requested_start_date: String(params?.start_date ?? null),
          requested_end_date: String(params?.end_date ?? null),
          actual_start_date: null,
          actual_end_date: null,
          interval: String(params?.interval ?? "1d"),
          last_downloaded_at: null,
          is_stale: true,
          has_local_data: false,
          warnings: ["No local market history has been downloaded yet."],
          observations: [],
          summary: null,
        };
      }

      const observations = [];
      const numDays = 730;
      const initialClose = cdCvm === 14311 ? 110.0 : 35.0;
      let prevClose = initialClose;
      
      let seed = cdCvm;
      function pseudoRandom() {
        const x = Math.sin(seed++) * 10000;
        return x - Math.floor(x);
      }

      for (let i = numDays; i >= 0; i--) {
        const d = new Date(Date.now() - i * 24 * 3600 * 1000);
        const dateStr = d.toISOString().split("T")[0];
        
        const change = (pseudoRandom() - 0.48) * 1.5;
        const close = Math.round((prevClose + change) * 100) / 100;
        const open = Math.round((prevClose + (pseudoRandom() - 0.5) * 0.5) * 100) / 100;
        const high = Math.round(Math.max(open, close) * 1.02 * 100) / 100;
        const low = Math.round(Math.min(open, close) * 0.98 * 100) / 100;
        const adjClose = Math.round(close * 0.95 * 100) / 100;
        const volume = Math.round(5_000_000 + pseudoRandom() * 10_000_000);
        
        const dividend = (i > 0 && i % 180 === 0) ? 1.25 : 0.0;
        
        prevClose = close;
        
        observations.push({
          date: dateStr,
          open,
          high,
          low,
          close,
          adjusted_close: adjClose,
          volume,
          dividend,
          split_ratio: 1.0,
          price_return_index: Math.round((close / initialClose) * 1000) / 1000,
          total_return_index: Math.round((adjClose / (initialClose * 0.95)) * 1000) / 1000,
          ttm_dividend_yield: dividend > 0 ? 0.085 : 0.082,
        });
      }

      const finalClose = prevClose;
      const annualizedTotalReturn = Math.round((Math.sqrt((finalClose * 0.95) / (initialClose * 0.95)) - 1.0) * 1000) / 1000;

      return {
        cd_cvm: cdCvm,
        ticker,
        source: "yahoo_finance",
        provider_status: "unofficial_free",
        requested_start_date: String(params?.start_date ?? null),
        requested_end_date: String(params?.end_date ?? null),
        actual_start_date: observations[0].date,
        actual_end_date: observations[observations.length - 1].date,
        interval: String(params?.interval ?? "1d"),
        last_downloaded_at: NOW,
        is_stale: false,
        has_local_data: true,
        warnings: [],
        observations,
        summary: {
          initial_close: initialClose,
          final_close: finalClose,
          absolute_change: Math.round((finalClose - initialClose) * 100) / 100,
          price_return: Math.round(((finalClose / initialClose) - 1.0) * 1000) / 1000,
          total_return: Math.round(((finalClose * 0.95 / (initialClose * 0.95)) - 1.0) * 1000) / 1000,
          annualized_total_return: annualizedTotalReturn,
          period_high: Math.round(initialClose * 1.3 * 100) / 100,
          period_low: Math.round(initialClose * 0.8 * 100) / 100,
          average_daily_volume: 8500000.0,
          dividends_per_share: 5.0,
          first_available_date: observations[0].date,
          last_available_date: observations[observations.length - 1].date,
        },
      };
    },

    refresh_company_market_history: async (params: { cd_cvm: number; ticker?: string | null }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const ticker = resolveMockTicker(cdCvm, params?.ticker);
      if (!ticker) {
        return {
          ok: false,
          ticker: "",
          requested_start_date: null,
          requested_end_date: null,
          provider_date_range: null,
          downloaded_rows: 0,
          inserted_rows: 0,
          updated_rows: 0,
          unchanged_rows: 0,
          rejected_rows: 0,
          provider_warnings: ["No ticker resolved"],
          completion_timestamp: NOW,
          refresh_duration_seconds: 0.0,
        };
      }
      
      DOWNLOADED_MARKET_HISTORIES.add(cdCvm);
      
      return {
        ok: true,
        ticker,
        requested_start_date: null,
        requested_end_date: null,
        provider_date_range: "2024-06-08 to 2026-06-08",
        downloaded_rows: 730,
        inserted_rows: 730,
        updated_rows: 0,
        unchanged_rows: 0,
        rejected_rows: 0,
        provider_warnings: [],
        completion_timestamp: NOW,
        refresh_duration_seconds: 0.12,
      };
    },

    refresh_all_company_market_history: async (params: { cd_cvm: number }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const tickers = resolveMockCompanyTickers(cdCvm);
      const results = tickers.map((ticker) => ({
        ok: true,
        ticker,
        requested_start_date: null,
        requested_end_date: null,
        provider_date_range: "2024-06-08 to 2026-06-08",
        downloaded_rows: 730,
        inserted_rows: 730,
        updated_rows: 0,
        unchanged_rows: 0,
        rejected_rows: 0,
        provider_warnings: [],
        completion_timestamp: NOW,
        refresh_duration_seconds: 0.12,
      }));
      DOWNLOADED_MARKET_HISTORIES.add(cdCvm);
      return {
        ok: results.length > 0,
        cd_cvm: cdCvm,
        attempted_count: results.length,
        success_count: results.length,
        failure_count: 0,
        results,
        error: results.length ? null : "No ticker resolved",
      };
    },
  };
}
