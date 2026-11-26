// Excel export and model mapping workspace bridge types.

import type { CompanyInfo } from "./types.companies";

export type OpenCompanyExcelMappingWindowResult = {
  ok: boolean;
  reused?: boolean;
  error?: string | null;
};

export type ExportCompanyResult = {
  ok: boolean;
  file_path?: string;
  file_name?: string;
  output_dir?: string;
  size_bytes?: number;
  revealed?: boolean;
  error?: string;
};

export type ExportMarketHistoryResult = ExportCompanyResult & {
  observation_count?: number;
  first_observation_date?: string | null;
  last_observation_date?: string | null;
};

export type OutputDirInfo = {
  path: string | null;
  exists: boolean;
  error?: string;
};

export type ExcelMappingSource = {
  statement_type: string;
  line_id_base: string;
  cd_conta: string | null;
  label_snapshot: string | null;
  sign: number;
  position: number;
};

export type ExcelMappingEntry = {
  target_id: string;
  target_label: string;
  group: string;
  statement_type: string;
  display_order: number;
  indent_level: number;
  required: boolean;
  operation: "direct" | "sum" | "sum_with_sign" | string;
  is_subtotal: boolean;
  sources: ExcelMappingSource[];
};

export type ExcelMappingDefinition = {
  preset_id: string;
  name: string;
  description: string | null;
  origin: "system" | "user" | string;
  default_mapping_version: string;
  sector_tags: string[];
  notes: string | null;
  validation_status: string | null;
  created_at: string | null;
  updated_at: string | null;
  entries: ExcelMappingEntry[];
};

export type ExcelMappingPresetSummary = {
  preset_id: string;
  name: string;
  description: string | null;
  origin: "system" | "user" | string;
  default_mapping_version: string;
  sector_tags: string[];
  notes: string | null;
  validation_status: string | null;
  created_at: string | null;
  updated_at: string | null;
  company_default: boolean;
};

export type ExcelMappingRawLine = {
  statement_type: string;
  line_id_base: string;
  cd_conta: string | null;
  ds_conta: string | null;
  standard_name: string | null;
  label: string;
  normalized_label: string;
  periods_present: string[];
  sample_values_by_period?: Record<string, number | null>;
  mapped_targets?: Array<{ target_id: string; target_label: string; group: string }>;
};

export type ExcelMappingPreviewRow = {
  target_id: string;
  target_label: string;
  group: string;
  statement_type: string;
  display_order: number;
  indent_level: number;
  required: boolean;
  operation: "direct" | "sum" | "sum_with_sign" | string;
  is_subtotal: boolean;
  source_count: number;
  warning_count: number;
  error_count: number;
  values_by_period: Record<string, number | null>;
  check_status?: Record<string, {
    status: "pass" | "rounding_difference" | "mismatch" | "unavailable" | "calculated";
    variance: number | null;
    reported_value: number | null;
  }>;
};

export type ExcelMappingValidationIssue = {
  severity: "error" | "warning" | string;
  code: string;
  message: string;
  target_id: string | null;
  source_id: string | null;
};

export type ExcelMappingResolution = {
  target_id: string;
  period: string;
  selected_source_id: string | null;
  selected_source_label: string | null;
  status: "auto_accepted" | "suggested" | "ambiguous" | "conflict" | "unresolved" | "manually_confirmed" | string;
  score: number;
  confidence_margin: number;
  resolved_value: number | null;
  evidence: string[];
  warnings: string[];
};

export type ExcelMappingWorkspace = {
  ok: boolean;
  company: CompanyInfo;
  presets: ExcelMappingPresetSummary[];
  active_preset_id: string;
  company_default_preset_id: string;
  mapping: ExcelMappingDefinition;
  period_scope_label?: string | null;
  preview_periods: string[];
  model_preview_rows: ExcelMappingPreviewRow[];
  raw_lines: ExcelMappingRawLine[];
  resolutions?: ExcelMappingResolution[];
  validation: ExcelMappingValidationIssue[];
  formula_definitions?: Record<string, {
    dependencies: string[];
    required: string[];
  }>;
  is_financial?: boolean;
  error?: string;
};

export type SaveExcelMappingPresetResult = {
  ok: boolean;
  preset?: ExcelMappingDefinition;
  presets?: ExcelMappingPresetSummary[];
  error?: string;
};

export type SetCompanyExcelMappingDefaultResult = {
  ok: boolean;
  cd_cvm?: number;
  preset_id?: string;
  error?: string;
};
