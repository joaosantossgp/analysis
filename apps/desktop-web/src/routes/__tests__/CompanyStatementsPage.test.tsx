import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatementGrid, StatementPanel } from "../CompanyStatementsPage";
import { fetchCompanyYears } from "@/lib/api/companyDetail";
import { fetchCompanyStatement, fetchCompanyStatementYears } from "@/lib/api/statements";
import type { StatementMatrix } from "@/lib/bridge/types";

const base: StatementMatrix = {
  cd_cvm: 4170, statement_type: "DRE", years: [2024], exclude_conflicts: true,
  table: { columns: ["CD_CONTA", "DS_CONTA", "3Q24"], rows: [{ CD_CONTA: "3.99.01.02", DS_CONTA: "ON", "3Q24": 3.14 }] },
};

afterEach(() => vi.unstubAllGlobals());

function render(matrix: StatementMatrix) {
  return renderToStaticMarkup(<StatementGrid matrix={matrix} statementType="DRE" selectedYears={[2024]} refreshing={false} />);
}

describe("Statement financial QA", () => {
  it("discovers partial statement years separately from annual years and reaches their QA", async () => {
    const matrix: StatementMatrix = { ...base, statement_type: "DFC", table: { columns: [], rows: [] },
      qa_events: [{ type: "MISSING_PREDECESSOR", period: "2Q24", cd_conta: "6.01", action: "Review missing Q1 source." }] };
    vi.stubGlobal("window", { pywebview: { api: {
      get_company_years: async () => ({ years: [] }),
      get_company_statement_years: async (params: Record<string, unknown>) => {
        expect(params).toEqual({ cd_cvm: 4170, stmt: "DFC" });
        return { years: [2024] };
      },
      get_company_statement: async (params: Record<string, unknown>) => {
        expect(params).toEqual({ cd_cvm: 4170, stmt: "DFC", years: [2024] });
        return matrix;
      },
    } } });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    try {
      await client.fetchQuery({ queryKey: ["company-years", 4170], queryFn: () => fetchCompanyYears(4170) });
      const discovered = await client.fetchQuery({ queryKey: ["company-statement-years", 4170, "DFC"], queryFn: () => fetchCompanyStatementYears(4170, "DFC") });
      expect(discovered.years).toEqual([2024]);
      await client.fetchQuery({ queryKey: ["company-statement", 4170, "DFC", "2024"], queryFn: () => fetchCompanyStatement(4170, discovered.years, "DFC") });
      const markup = renderToStaticMarkup(<QueryClientProvider client={client}><StatementPanel cdCvm={4170} statementType="DFC" bridgeReady /></QueryClientProvider>);
      expect(markup).toContain("Review missing Q1 source.");
      expect(markup).not.toContain("No annual statements");
    } finally { client.clear(); }
  });

  it("shows actionable QA when every analytical value is unavailable", () => {
    const markup = render({ ...base, table: { columns: [], rows: [] }, quality_evidence: "available",
      qa_events: [{ type: "MISSING_PREDECESSOR", cd_conta: "6.01", period: "3Q24", unit: "BRL thousands", missing_inputs: ["2Q24"], action: "Review the original filing." }] } as StatementMatrix);
    expect(markup).toContain("financial QA event");
    expect(markup).toContain("6.01");
    expect(markup).toContain("2Q24");
    expect(markup).toContain("Review the original filing.");
  });

  it("lists each QA source and flags one missing from the local database", () => {
    const markup = render({ ...base, quality_evidence: "available",
      qa_events: [{ type: "MISSING_OBSERVATION", cd_conta: "3.01", period: "2024", action: "Review.",
        source_inputs: [
          { SOURCE_FILE: "dfp_cia_aberta_DRE_con_2024.csv", VERSAO: "2", DT_INI_EXERC: "2024-01-01", DT_FIM_EXERC: "2024-12-31", RAW_VL_CONTA: "10" },
          { observation_id: "abc123", evidence_status: "missing" },
        ] }] } as StatementMatrix);
    expect(markup).toContain("dfp_cia_aberta_DRE_con_2024.csv · version 2");
    expect(markup).toContain("Source observation abc123 is missing from the local database");
  });

  it("keeps missing legacy evidence explicit", () => {
    expect(render(base)).toContain("Legacy source/period QA evidence unavailable");
  });

  it("shows reported EPS with per-share units and decimal precision", () => {
    const markup = render(base);
    expect(markup).toContain("BRL/share");
    expect(markup).toContain("3.14");
  });
});
