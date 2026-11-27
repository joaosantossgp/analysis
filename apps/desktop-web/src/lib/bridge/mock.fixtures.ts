import type { CompanyDirectoryItem } from "./types";

export const NOW = new Date().toISOString();
export const YEAR = new Date().getFullYear();

export interface FixtureCompany {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
  sector_name: string;
  sector_slug: string;
  data_status: string;
  anos_disponiveis: number[];
  total_rows: number;
  has_financial_data: boolean;
  cnpj: string | null;
}

export const FIXTURE_COMPANIES: FixtureCompany[] = [
  {
    cd_cvm: 9512,
    company_name: "PETROBRAS PN",
    ticker_b3: "PETR4",
    sector_name: "Petróleo e Gás",
    sector_slug: "petroleo-e-gas",
    data_status: "complete",
    anos_disponiveis: [YEAR - 5, YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1],
    total_rows: 18450,
    has_financial_data: true,
    cnpj: "33.000.167/0001-01",
  },
  {
    cd_cvm: 14311,
    company_name: "VALE ON",
    ticker_b3: "VALE3",
    sector_name: "Mineração",
    sector_slug: "mineracao",
    data_status: "complete",
    anos_disponiveis: [YEAR - 5, YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1],
    total_rows: 15820,
    has_financial_data: true,
    cnpj: "33.592.510/0001-54",
  },
  {
    cd_cvm: 14673,
    company_name: "AMBEV SA",
    ticker_b3: "ABEV3",
    sector_name: "Alimentos e Bebidas",
    sector_slug: "alimentos-e-bebidas",
    data_status: "partial",
    anos_disponiveis: [YEAR - 3, YEAR - 2, YEAR - 1],
    total_rows: 6200,
    has_financial_data: true,
    cnpj: "07.526.557/0001-00",
  },
  {
    cd_cvm: 4170,
    company_name: "OI SA",
    ticker_b3: "OIBR3",
    sector_name: "Telecomunicações",
    sector_slug: "telecomunicacoes",
    data_status: "failed",
    anos_disponiveis: [YEAR - 5, YEAR - 4],
    total_rows: 3100,
    has_financial_data: false,
    cnpj: "76.535.764/0001-43",
  },
  {
    cd_cvm: 5258,
    company_name: "XP INC",
    ticker_b3: null,
    sector_name: "Financeiro",
    sector_slug: "financeiro",
    data_status: "no_history",
    anos_disponiveis: [],
    total_rows: 0,
    has_financial_data: false,
    cnpj: null,
  },
  {
    cd_cvm: 99001,
    company_name: "EMPRESA DEMO LTDA",
    ticker_b3: null,
    sector_name: "Outros",
    sector_slug: "outros",
    data_status: "unmapped",
    anos_disponiveis: [],
    total_rows: 0,
    has_financial_data: false,
    cnpj: null,
  },
];

export const SECTOR_SLUGS = [
  { name: "Petróleo e Gás", slug: "petroleo-e-gas", count: 1 },
  { name: "Mineração", slug: "mineracao", count: 1 },
  { name: "Alimentos e Bebidas", slug: "alimentos-e-bebidas", count: 1 },
  { name: "Telecomunicações", slug: "telecomunicacoes", count: 1 },
  { name: "Financeiro", slug: "financeiro", count: 1 },
  { name: "Outros", slug: "outros", count: 1 },
];


// ---------------------------------------------------------------------------
// Company directory item helpers
// ---------------------------------------------------------------------------

export function toDirectoryItem(c: FixtureCompany): CompanyDirectoryItem {
  return {
    cd_cvm: c.cd_cvm,
    company_name: c.company_name,
    ticker_b3: c.ticker_b3,
    setor_cvm: c.sector_name,
    sector_name: c.sector_name,
    sector_slug: c.sector_slug,
    anos_disponiveis: c.anos_disponiveis,
    total_rows: c.total_rows,
    has_financial_data: c.has_financial_data,
    coverage_rank: c.has_financial_data ? 1 : null,
    data_status: c.data_status,
    gics_sector: c.cd_cvm === 9512 ? "Energy" : c.cd_cvm === 14311 ? "Materials" : c.cd_cvm === 14673 ? "Consumer Staples" : null,
    gics_sector_slug: c.cd_cvm === 9512 ? "energy" : c.cd_cvm === 14311 ? "materials" : c.cd_cvm === 14673 ? "consumer-staples" : null,
    gics_industry_group: null,
    gics_industry: c.cd_cvm === 9512 ? "Oil, Gas & Consumable Fuels" : null,
    gics_sub_industry: c.cd_cvm === 9512 ? "Integrated Oil & Gas" : c.cd_cvm === 14311 ? "Steel" : c.cd_cvm === 14673 ? "Brewers" : null,
  };
}
