import type {
  BridgeApi,
} from "./types";

export function createMockCoverageMethods(): Partial<BridgeApi> {
  return {
    get_coverage_universes: async () => {
      return [
        {
          id: "63c536bd-c1d5-44d8-8275-3b03c498f36e",
          name: "Equity I",
          purpose: "Companhias com familiaridade",
          analysis_type: "Equity",
          benchmark: "IBOV",
          status: "active",
          company_count: 5,
          created_at: "2026-06-17T00:10:38Z",
          updated_at: "2026-06-17T00:34:26Z"
        },
        {
          id: "c59accae-996d-4d12-a67a-5424f3832787",
          name: "Equity II",
          purpose: "Novas teses de cobertura",
          analysis_type: "Equity",
          benchmark: "IBOV",
          status: "draft",
          company_count: 3,
          created_at: "2026-06-17T00:14:11Z",
          updated_at: "2026-06-17T00:34:18Z"
        }
      ];
    },

    get_coverage_universe: async (params: any) => {
      const id = params?.id || "63c536bd-c1d5-44d8-8275-3b03c498f36e";
      const name = id === "63c536bd-c1d5-44d8-8275-3b03c498f36e" ? "Equity I" : "Equity II";
      const status = id === "63c536bd-c1d5-44d8-8275-3b03c498f36e" ? "active" : "draft";
      return {
        id,
        name,
        purpose: id === "63c536bd-c1d5-44d8-8275-3b03c498f36e" ? "Companhias com familiaridade" : "Novas teses de cobertura",
        analysis_type: "Equity",
        benchmark: "IBOV",
        status,
        created_at: "2026-06-17T00:10:38Z",
        updated_at: "2026-06-17T00:34:26Z",
        assumptions: {
          weights: {
            market_cap_weight: 0.3,
            volume_weight: 0.3,
            holding_weight: 0.2,
            sector_weight: 0.2
          },
          tier_hours: {
            must_cover: 120,
            core: 80,
            watchlist: 30,
            opportunistic: 45,
            excluded: 5,
            inappropriate: 5
          },
          manager_decision: {
            status,
            decided_at: "2026-06-18T10:00:00Z",
            notes: "Initial universe setup approved by team"
          }
        }
      };
    },

    calculate_coverage_priority_scores: async (_params: any) => {
      const items = [
        {
          cd_cvm: 9512,
          company_name: "PETROBRAS PN",
          ticker_b3: "PETR4",
          gics_sector: "Energy",
          market_cap: 500000000000,
          market_cap_brl: 500000000000,
          volume_brl: 1500000000,
          holding_pct: 5.2,
          tier: "must_cover",
          final_score: 92.5,
          score_status: "normal",
          owner: "Thiago",
          rationale: "Fator estratégico nacional de relevância máxima",
          has_financial_data: true,
          completed_checklist_count: 5,
          total_checklist_count: 5
        },
        {
          cd_cvm: 14311,
          company_name: "VALE ON",
          ticker_b3: "VALE3",
          gics_sector: "Materials",
          market_cap: 320000000000,
          market_cap_brl: 320000000000,
          volume_brl: 1200000000,
          holding_pct: 8.5,
          tier: "must_cover",
          final_score: 88.0,
          score_status: "normal",
          owner: "Thiago",
          rationale: "Maior produtor global de minério de ferro",
          has_financial_data: true,
          completed_checklist_count: 4,
          total_checklist_count: 5
        },
        {
          cd_cvm: 14673,
          company_name: "AMBEV SA",
          ticker_b3: "ABEV3",
          gics_sector: "Consumer Staples",
          market_cap: 210000000000,
          market_cap_brl: 210000000000,
          volume_brl: 450000000,
          holding_pct: 2.1,
          tier: "core",
          final_score: 75.2,
          score_status: "normal",
          owner: "Felipe",
          rationale: "Geração de caixa resiliente e liderança de mercado",
          has_financial_data: true,
          completed_checklist_count: 3,
          total_checklist_count: 5
        },
        {
          cd_cvm: 4170,
          company_name: "OI SA",
          ticker_b3: "OIBR3",
          gics_sector: "Telecommunication Services",
          market_cap: 1200000000,
          market_cap_brl: 1200000000,
          volume_brl: 15000000,
          holding_pct: 0.0,
          tier: "watchlist",
          final_score: 18.5,
          score_status: "partial",
          owner: null,
          rationale: "Empresa em recuperação judicial",
          has_financial_data: true,
          completed_checklist_count: 1,
          total_checklist_count: 5
        },
        {
          cd_cvm: 5258,
          company_name: "XP INC",
          ticker_b3: "XPBR31",
          gics_sector: "Financials",
          market_cap: 85000000000,
          market_cap_brl: 85000000000,
          volume_brl: 180000000,
          holding_pct: 1.5,
          tier: "watchlist",
          final_score: 0.0,
          score_status: "blocked",
          owner: "Felipe",
          rationale: "Dados financeiros insuficientes para cálculo automatizado",
          has_financial_data: false,
          completed_checklist_count: 0,
          total_checklist_count: 5
        }
      ];
      return { items, _bridge_ms: 120 };
    },

    get_company_coverage_checklists: async (_params: any) => {
      const items = [
        { item_key: "annual_report_reviewed", is_completed: true, comments: "Annual report (DFP) 2025 read and checked.", rationale: "Mandatory" },
        { item_key: "earnings_call_listened", is_completed: true, comments: "4Q25 earnings call listened.", rationale: "Qualitative factor" },
        { item_key: "financial_model_updated", is_completed: false, comments: "Missing capex projection.", rationale: "Model V2" },
        { item_key: "competitor_benchmarking", is_completed: false, comments: "Awaiting peers benchmarking.", rationale: "Comparative" },
        { item_key: "investment_thesis_drafted", is_completed: false, comments: "", rationale: "Executive summary" }
      ];
      return { items };
    },

    get_coverage_work_queue: async (_params: any) => {
      const items = [
        {
          cd_cvm: 9512,
          company_name: "PETROBRAS PN",
          ticker_b3: "PETR4",
          tier: "must_cover",
          owner: "Thiago",
          reason: "Missing financial model update with refining assumptions.",
          severity: "high",
          task_type: "checklist_gap",
          suggested_action: "Complete 'financial_model_updated' checklist item."
        },
        {
          cd_cvm: 14311,
          company_name: "VALE ON",
          ticker_b3: "VALE3",
          tier: "must_cover",
          owner: "Thiago",
          reason: "Sector benchmarking is outdated.",
          severity: "high",
          task_type: "checklist_gap",
          suggested_action: "Complete 'competitor_benchmarking' checklist item."
        },
        {
          cd_cvm: 4170,
          company_name: "OI SA",
          ticker_b3: "OIBR3",
          tier: "watchlist",
          owner: null,
          reason: "No analyst assigned to cover this company.",
          severity: "low",
          task_type: "unassigned_owner",
          suggested_action: "Assign a coverage analyst for OI SA."
        },
        {
          cd_cvm: 5258,
          company_name: "XP INC",
          ticker_b3: "XPBR31",
          tier: "watchlist",
          owner: "Felipe",
          reason: "Missing market cap historical series (Score Blocked).",
          severity: "medium",
          task_type: "missing_market_cap",
          suggested_action: "Import market cap data or refresh XP INC manually."
        }
      ];
      return { items };
    },

    get_coverage_capacity_data: async (_params: any) => {
      return {
        available_hours: 1600,
        required_hours: 1040,
        capacity_utilization_pct: 65.0,
        warnings: [
          "XP INC (XPBR31) has missing or invalid GICS classification. Complexity marked as unknown."
        ],
        tier_counts: {
          must_cover: 2,
          core: 1,
          watchlist: 2,
          opportunistic: 0,
          excluded: 0,
          inappropriate: 0
        },
        tier_hours: {
          must_cover: 240,
          core: 80,
          watchlist: 60,
          opportunistic: 0,
          excluded: 0,
          inappropriate: 0
        },
        tier_hours_assumptions: {
          must_cover: 120,
          core: 80,
          watchlist: 30,
          opportunistic: 45,
          excluded: 5,
          inappropriate: 5
        },
        by_owner: {
          "Thiago": { company_count: 2, required_hours: 200.0, utilization_pct: 12.5 },
          "Felipe": { company_count: 2, required_hours: 140.0, utilization_pct: 8.75 },
          "Unassigned": { company_count: 1, required_hours: 30.0, utilization_pct: 1.88 }
        },
        gics_unknown_companies: [
          { cd_cvm: 5258, company_name: "XP INC", ticker_b3: "XPBR31", tier: "watchlist" }
        ]
      };
    },

    get_coverage_recommendation: async (_params: any) => {
      return {
        universe_id: _params?.universe_id || "63c536bd-c1d5-44d8-8275-3b03c498f36e",
        company_count: 5,
        keep: [
          { cd_cvm: 9512, company_name: "PETROBRAS PN", ticker_b3: "PETR4", tier: "must_cover", score_status: "normal", final_score: 92.5, owner: "Thiago" },
          { cd_cvm: 14311, company_name: "VALE ON", ticker_b3: "VALE3", tier: "must_cover", score_status: "normal", final_score: 88.0, owner: "Thiago" },
          { cd_cvm: 14673, company_name: "AMBEV SA", ticker_b3: "ABEV3", tier: "core", score_status: "normal", final_score: 75.2, owner: "Felipe" }
        ],
        review: [
          { cd_cvm: 4170, company_name: "OI SA", ticker_b3: "OIBR3", tier: "watchlist", score_status: "partial", final_score: 18.5, owner: null }
        ],
        blocked: [
          { cd_cvm: 5258, company_name: "XP INC", ticker_b3: "XPBR31", tier: "watchlist", score_status: "blocked", final_score: 0.0, owner: "Felipe" }
        ],
        excluded: [],
        missing_data_risks: {
          missing_market_cap_count: 1,
          missing_gics_count: 1,
          unassigned_owner_count: 1
        },
        proposed_actions: [
          "Import market cap or quotes data for XP INC.",
          "Assign coverage analyst for OI SA.",
          "Complete the qualitative checklist for Vale and Petrobras."
        ],
        risks: [
          "XP INC (XPBR31) is blocked due to missing basic financial data.",
          "Missing GICS classification for XP INC prevents accurate sector complexity estimation."
        ]
      };
    },

    get_coverage_decision_history: async (_params: any) => {
      return {
        items: [
          {
            id: 1,
            event_type: "manager_decision_change",
            previous_value: "draft",
            new_value: "approved",
            rationale: "Quarterly review finalized. Portfolio approved for execution.",
            timestamp: "2026-06-18T10:00:00Z",
            author: "Manager",
            company_name: "All",
            ticker_b3: null,
            cd_cvm: null
          },
          {
            id: 2,
            event_type: "owner_change",
            previous_value: null,
            new_value: "Thiago",
            rationale: "Thiago takes over major commodities producers.",
            timestamp: "2026-06-17T11:30:00Z",
            author: "Manager",
            company_name: "VALE ON",
            ticker_b3: "VALE3",
            cd_cvm: 14311
          },
          {
            id: 3,
            event_type: "override_change",
            previous_value: null,
            new_value: "95.0",
            rationale: "Strategic relevance of energy sector in the portfolio.",
            timestamp: "2026-06-17T11:25:00Z",
            author: "Manager",
            company_name: "PETROBRAS PN",
            ticker_b3: "PETR4",
            cd_cvm: 9512
          }
        ]
      };
    },

    save_manual_score_override: async () => ({ success: true }),

    update_company_owner_analyst: async () => ({ success: true }),

    save_coverage_capacity_scenario: async () => ({ success: true }),

    save_coverage_manager_decision: async () => ({ success: true, status: "approved", decided_at: new Date().toISOString() }),

    duplicate_coverage_universe: async () => ({ success: true, universe_id: "duplicate-mock-id" }),

    delete_coverage_universe: async () => ({ success: true }),

    create_coverage_universe: async () => ({ success: true, universe_id: "new-mock-id" }),

    update_coverage_universe: async () => ({ success: true }),

    bulk_update_companies_in_coverage_universe: async () => ({ success: true }),

    add_company_to_coverage_universe: async () => ({ success: true }),

    remove_company_from_coverage_universe: async () => ({ success: true }),
  };
}
