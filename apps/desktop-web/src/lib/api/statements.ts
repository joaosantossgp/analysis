import { callBridge, getBridgeMode } from "../bridge/adapter";
import type { StatementMatrix } from "../bridge/types";
import type { CompanyYearsResultUI } from "./companyDetail";

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable. Launch with python -m desktop.app --vite or the packaged exe.";

export const STATEMENT_OPTIONS = [
  { value: "DRE", label: "DRE", description: "Income" },
  { value: "BPA", label: "BPA", description: "Assets" },
  { value: "BPP", label: "BPP", description: "Liabilities & equity" },
  { value: "DFC", label: "DFC", description: "Cash flow" },
] as const;

export type StatementType = (typeof STATEMENT_OPTIONS)[number]["value"];

export type CompanyStatementResult =
  | { mode: "desktop"; matrix: StatementMatrix }
  | { mode: "browser"; matrix: null; reason: string };

export async function fetchCompanyStatementYears(cdCvm: number, statementType: StatementType): Promise<CompanyYearsResultUI> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", years: [], reason: BROWSER_REASON };
  }
  const result = await callBridge("get_company_statement_years", { cd_cvm: cdCvm, stmt: statementType });
  if (result.error) throw new Error(result.error);
  return { mode: "desktop", years: result.years ?? [] };
}

export function normalizeStatementType(value: string | null | undefined): StatementType {
  const upper = String(value ?? "").toUpperCase();
  return STATEMENT_OPTIONS.some((item) => item.value === upper)
    ? (upper as StatementType)
    : "DRE";
}

export async function fetchCompanyStatement(
  cdCvm: number,
  years: number[],
  statementType: StatementType,
): Promise<CompanyStatementResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", matrix: null, reason: BROWSER_REASON };
  }
  if (years.length === 0) {
    return {
      mode: "desktop",
      matrix: {
        cd_cvm: cdCvm,
        statement_type: statementType,
        years: [],
        table: { columns: [], rows: [] },
        exclude_conflicts: true,
      },
    };
  }
  const matrix = await callBridge("get_company_statement", {
    cd_cvm: cdCvm,
    years,
    stmt: statementType,
  });
  if (matrix.error) {
    throw new Error(matrix.error);
  }
  return { mode: "desktop", matrix };
}
