import type {
  BridgeApi,
} from "./types";

export function createMockDistributionMethods(): Partial<BridgeApi> {
  return {
    get_distribution_distributors: async (params) => {
      const search = (params?.search || "").toLowerCase();
      const items = [
        {
          distributor_id: "coelba",
          canonical_name: "Neoenergia Coelba",
          trade_name: "COELBA",
          normalized_cnpj: "15139629000194",
          agent_code: "48",
          concession_type: "concession",
          primary_uf: "BA",
          status: "active",
          economic_group_id: "neoenergia",
          group_name: "Neoenergia",
          cd_cvm: 15539,
          company_name: "NEOENERGIA S.A.",
          ticker_b3: "NEOE3.SA",
        },
        {
          distributor_id: "cpfl_paulista",
          canonical_name: "CPFL Paulista",
          trade_name: "CPFL PAULISTA",
          normalized_cnpj: "33050196000188",
          agent_code: "25",
          concession_type: "concession",
          primary_uf: "SP",
          status: "active",
          economic_group_id: "cpfl",
          group_name: "CPFL Energia",
          cd_cvm: 18660,
          company_name: "CPFL ENERGIA S.A.",
          ticker_b3: "CPFE3.SA",
        }
      ].filter(item => !search || item.canonical_name.toLowerCase().includes(search) || item.trade_name.toLowerCase().includes(search));
      return { items, count: items.length };
    },

    get_distribution_distributor_detail: async (params) => {
      const distributor_id = params?.distributor_id || "coelba";
      const isCoelba = distributor_id === "coelba";
      return {
        identity: {
          distributor_id: isCoelba ? "coelba" : "cpfl_paulista",
          canonical_name: isCoelba ? "Neoenergia Coelba" : "CPFL Paulista",
          legal_name: isCoelba ? "COELBA DISTRIBUIDORA DE ENERGIA" : "COMPANHIA PAULISTA DE FORÇA E LUZ",
          trade_name: isCoelba ? "COELBA" : "CPFL PAULISTA",
          normalized_cnpj: isCoelba ? "15139629000194" : "33050196000188",
          agent_code: isCoelba ? "48" : "25",
          distributor_code: isCoelba ? "48" : "25",
          concession_type: "concession",
          primary_uf: isCoelba ? "BA" : "SP",
          service_area: isCoelba ? "State of Bahia" : "Interior of São Paulo State",
          status: "active",
        },
        ownership_history: [
          {
            ownership_id: isCoelba ? "coelba_neo" : "cpfl_paulista_cpfl",
            valid_from: "2000-01-01",
            valid_to: "2099-12-31",
            control_status: "controlled",
            ownership_percentage: 1.0,
            operational_consolidation_flag: 1,
            economic_group_id: isCoelba ? "neoenergia" : "cpfl",
            group_name: isCoelba ? "Neoenergia" : "CPFL Energia",
            cd_cvm: isCoelba ? 15539 : 18660,
            company_name: isCoelba ? "NEOENERGIA S.A." : "CPFL ENERGIA S.A.",
            ticker_b3: isCoelba ? "NEOE3.SA" : "CPFE3.SA",
          }
        ],
        available_periods: ["2025-01", "2025-02", "2025-03"],
      };
    },

    get_distribution_series: async (_params) => {
      const series = [
        {
          period: "2025-01",
          billed_energy_mwh: 1200.5,
          revenue_brl: 450000.0,
          measured_energy_mwh: 1300.0,
          injected_energy_mwh: 1400.0,
          losses_mwh: 100.0,
          losses_pct: 0.0769,
          dec_actual: 7.2,
          fec_actual: 5.1,
          dec_limit: 8.0,
          fec_limit: 6.0,
          compensation_count: 150,
          compensation_value: 45000.0,
          delinquency_pct: 0.021,
          mmgd_projects_count: 1200,
          mmgd_capacity_kw: 4500.0,
          te_homologated: 120.40,
          tusd_homologated: 150.50,
        },
        {
          period: "2025-02",
          billed_energy_mwh: 1250.0,
          revenue_brl: 470000.0,
          measured_energy_mwh: 1350.0,
          injected_energy_mwh: 1450.0,
          losses_mwh: 100.0,
          losses_pct: 0.074,
          dec_actual: 7.1,
          fec_actual: 5.0,
          dec_limit: 8.0,
          fec_limit: 6.0,
          compensation_count: 140,
          compensation_value: 42000.0,
          delinquency_pct: 0.020,
          mmgd_projects_count: 1250,
          mmgd_capacity_kw: 4700.0,
          te_homologated: 122.10,
          tusd_homologated: 152.00,
        }
      ];
      return { series, count: series.length };
    },

    get_distribution_mmgd_projects: async (params) => {
      const rows = [
        {
          project_id: "GD-MOCK-1",
          distributor_id: params?.distributor_id || "cpfl_paulista",
          municipality: "Campinas",
          uf: "SP",
          consumer_class: "Residential",
          tariff_subgroup: "B1",
          project_modality: "Local generation",
          enabled_modality: "Self-consumption",
          generation_type: "Solar",
          generation_source: "Solar radiation",
          size_category: "Microgeneration",
          latitude: -22.9,
          longitude: -47.06,
          connection_date: "2025-01-15",
          reference_month: params?.reference_month || "2025-02",
          installed_capacity_kw: 10.5,
          beneficiary_units_count: 1,
          source_row_hash: "mock-hash-1",
          snapshot_id: "mock-snapshot",
        },
      ];
      return {
        source: "managed_parquet" as const,
        dataset_id: "distribution_mmgd_projects",
        distributor_id: params?.distributor_id || "cpfl_paulista",
        reference_month: params?.reference_month || "2025-02",
        rows,
        projects: rows,
        count: rows.length,
        total_matching_rows: rows.length,
        limit: params?.limit || 50,
        offset: params?.offset || 0,
        truncated: false,
      };
    },

    get_distribution_refresh_status: async () => ({
      status: "idle",
      error: null,
      stage: "done",
      message: "Mock refresh finished",
      progress_current: 3,
      progress_total: 3,
    }),

    refresh_distribution_data: async () => ({
      status: "started",
      error: null,
    }),

    get_distribution_groups: async (_params) => {
      const items = [
        {
          economic_group_id: "neoenergia",
          group_name: "Neoenergia",
          cd_cvm: 15539,
          company_name: "NEOENERGIA S.A.",
          ticker_b3: "NEOE3.SA",
          distributors_count: 5,
        },
        {
          economic_group_id: "cpfl",
          group_name: "CPFL Energia",
          cd_cvm: 18660,
          company_name: "CPFL ENERGIA S.A.",
          ticker_b3: "CPFE3.SA",
          distributors_count: 4,
        }
      ];
      return { items, count: items.length };
    },

    get_distribution_group_detail: async (params) => {
      const group_id = params?.group_id || "neoenergia";
      const isNeo = group_id === "neoenergia";
      return {
        identity: {
          economic_group_id: isNeo ? "neoenergia" : "cpfl",
          group_name: isNeo ? "Neoenergia" : "CPFL Energia",
          cd_cvm: isNeo ? 15539 : 18660,
          company_name: isNeo ? "NEOENERGIA S.A." : "CPFL ENERGIA S.A.",
          ticker_b3: isNeo ? "NEOE3.SA" : "CPFE3.SA",
        },
        portfolio: [
          {
            ownership_id: isNeo ? "coelba_neo" : "cpfl_paulista_cpfl",
            distributor_id: isNeo ? "coelba" : "cpfl_paulista",
            canonical_name: isNeo ? "Neoenergia Coelba" : "CPFL Paulista",
            trade_name: isNeo ? "COELBA" : "CPFL PAULISTA",
            valid_from: "2000-01-01",
            valid_to: "2099-12-31",
            control_status: "controlled",
            ownership_percentage: 1.0,
            operational_consolidation_flag: 1,
          }
        ],
        available_periods: ["2025-01", "2025-02", "2025-03"],
      };
    },

    export_distribution_excel: async (_params) => {
      return {
        path: "C:\\Users\\mock\\Documents\\CVMAnalytics\\reports\\mock_export.xlsx",
        error: null,
      };
    },

    get_distribution_health: async (_params) => {
      return {
        counts: {
          market: 0,
          balance: 0,
          continuity: 0,
          tariffs: 0,
          delinquency: 0,
          mmgd: 0,
        },
        snapshots: [],
      };
    },
  };
}
