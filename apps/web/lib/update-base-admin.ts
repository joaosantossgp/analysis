import type {
  BaseHealthSnapshot,
  BatchJobStatus,
  BatchRefreshMode,
  CompanySectorFilter,
} from "./api.ts";

export type DataLoadState = "loading" | "available" | "unavailable";

export type BaseHealthSummary = {
  totalCompanies: number | null;
  companiesWithHistoricalData: number | null;
  companiesWithoutHistoricalData: number | null;
  companiesWithAnyLocalFinancialReport: number | null;
  companiesPartialLocal: number | null;
  companiesWithRefreshStatusRecorded: number | null;
  companiesWithLastRefreshError: number | null;
  completedCells: number | null;
  missingCells: number | null;
  coveragePct: number | null;
  generatedAt: string | null;
  startYear: number | null;
  endYear: number | null;
  healthStatus: string | null;
  etaHours: number | null;
};

export type UpdateModeEstimate = {
  affected: number | null;
  unitLabel: string;
  description: string;
  duration: string;
};

export type UpdateBaseHistoryItem = {
  id: string;
  date: string;
  typeLabel: string;
  status: "success" | "partial" | "failed" | "cancelled";
  duration: string;
  processed: number;
  failures: number;
};

export type HistoryState =
  | "loading"
  | "has_history"
  | "active_jobs_no_history"
  | "no_history_no_active_job"
  | "source_unavailable";

const TERMINAL_STATES = new Set(["success", "error", "cancelled", "interrupted"]);
const ACTIVE_STATES = new Set(["queued", "running"]);
const MODE_LABELS: Record<BatchRefreshMode, string> = {
  full: "Completa",
  missing: "Faltantes",
  outdated: "Desatualizadas",
  failed: "Com falha",
};
const STAGE_PROGRESS_FLOOR: Record<string, number> = {
  planning: 8,
  download_extract: 35,
  process_data: 58,
  persist_reports: 82,
  finalizing: 95,
};

const numberFormatter = new Intl.NumberFormat("pt-BR");

export function getDefaultBaseHealthWindow(referenceDate = new Date()): {
  startYear: number;
  endYear: number;
} {
  const endYear = referenceDate.getFullYear() - 1;
  return { startYear: endYear - 1, endYear };
}

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

export function buildBaseHealthSummary(health: BaseHealthSnapshot | null): BaseHealthSummary {
  const totalCompanies = health?.total_companies ?? null;
  const companiesWithHistoricalData = health?.companies_with_historical_data ?? null;
  const companiesWithoutHistoricalData =
    health?.companies_without_historical_data ?? null;

  return {
    totalCompanies,
    companiesWithHistoricalData,
    companiesWithoutHistoricalData,
    companiesWithAnyLocalFinancialReport:
      health?.companies_with_any_local_financial_report ?? null,
    companiesPartialLocal: health?.companies_partial_local ?? null,
    companiesWithRefreshStatusRecorded:
      health?.companies_with_refresh_status_recorded ?? null,
    companiesWithLastRefreshError: health?.companies_with_last_refresh_error ?? null,
    completedCells: health?.completed_cells ?? null,
    missingCells: health?.missing_cells ?? null,
    coveragePct: health?.pct ?? null,
    generatedAt: health?.generated_at ?? null,
    startYear: health?.start_year ?? null,
    endYear: health?.end_year ?? null,
    healthStatus: health?.health_status ?? null,
    etaHours: health?.eta_hours ?? null,
  };
}

function formatEtaHours(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Calculada ao iniciar";
  if (value < 1) return `~${Math.max(1, Math.round(value * 60))}m`;
  const hours = Math.floor(value);
  const minutes = Math.round((value - hours) * 60);
  return minutes > 0 ? `~${hours}h ${minutes}m` : `~${hours}h`;
}

export function buildUpdateModeEstimates({
  health,
  sectors,
  selectedSectorSlug,
}: {
  health: BaseHealthSnapshot | null;
  sectors: CompanySectorFilter[];
  selectedSectorSlug: string | null;
}): Record<BatchRefreshMode, UpdateModeEstimate> {
  const summary = buildBaseHealthSummary(health);
  const selectedSector = sectors.find((sector) => sector.sector_slug === selectedSectorSlug);
  const fullCount = selectedSector?.company_count ?? summary.totalCompanies;
  const windowLabel =
    summary.startYear != null && summary.endYear != null
      ? `${summary.startYear}-${summary.endYear}`
      : "janela atual";

  return {
    full: {
      affected: fullCount,
      unitLabel: "empresas",
      description:
        fullCount != null
          ? selectedSector
            ? `${formatNumber(fullCount)} empresas no setor ${selectedSector.sector_name}`
            : `${formatNumber(fullCount)} empresas no cadastro`
          : "Empresas resolvidas pelo backend ao iniciar",
      duration: formatEtaHours(summary.etaHours),
    },
    missing: {
      affected: summary.missingCells,
      unitLabel: "lacunas",
      description:
        summary.missingCells != null
          ? `${formatNumber(summary.missingCells)} lacunas na janela ${windowLabel}`
          : "Lacunas resolvidas pelo backend ao iniciar",
      duration: formatEtaHours(summary.etaHours),
    },
    outdated: {
      affected: null,
      unitLabel: "empresas",
      description: "Empresas defasadas calculadas pelo backend ao iniciar",
      duration: "Calculada ao iniciar",
    },
    failed: {
      affected: null,
      unitLabel: "empresas",
      description: "Falhas recentes calculadas pelo backend ao iniciar",
      duration: "Calculada ao iniciar",
    },
  };
}

export function isActiveBatchJob(job: BatchJobStatus): boolean {
  return ACTIVE_STATES.has(job.state);
}

export function isTerminalBatchJob(job: BatchJobStatus): boolean {
  return TERMINAL_STATES.has(job.state);
}

function timestampForJob(job: BatchJobStatus): string | null {
  return job.finished_at ?? job.updated_at ?? job.started_at ?? job.accepted_at ?? null;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "Sem data";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(startIso: string | null | undefined, finishIso: string | null | undefined): string {
  if (!startIso || !finishIso) return "n/d";
  const start = new Date(startIso);
  const finish = new Date(finishIso);
  if (Number.isNaN(start.getTime()) || Number.isNaN(finish.getTime())) return "n/d";
  const seconds = Math.max(0, Math.round((finish.getTime() - start.getTime()) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function statusForJob(job: BatchJobStatus): UpdateBaseHistoryItem["status"] {
  if (job.state === "cancelled" || job.state === "interrupted") return "cancelled";
  if (job.state === "error") return "failed";
  if (job.failures > 0) return "partial";
  return "success";
}

export function buildHistoryRows(jobs: BatchJobStatus[]): UpdateBaseHistoryItem[] {
  return jobs
    .filter(isTerminalBatchJob)
    .sort((a, b) => {
      const aDate = new Date(timestampForJob(a) ?? "").getTime() || 0;
      const bDate = new Date(timestampForJob(b) ?? "").getTime() || 0;
      return bDate - aDate;
    })
    .map((job) => ({
      id: job.job_id,
      date: formatDateTime(timestampForJob(job)),
      typeLabel: job.mode ? MODE_LABELS[job.mode] : "Lote",
      status: statusForJob(job),
      duration: formatDuration(job.started_at, job.finished_at),
      processed: job.processed,
      failures: job.failures,
    }))
}

export function getHistoryState({
  jobsState,
  activeJobCount,
  historyCount,
}: {
  jobsState: DataLoadState;
  activeJobCount: number;
  historyCount: number;
}): HistoryState {
  if (jobsState === "loading") return "loading";
  if (jobsState === "unavailable") return "source_unavailable";
  if (historyCount > 0) return "has_history";
  if (activeJobCount > 0) return "active_jobs_no_history";
  return "no_history_no_active_job";
}

export function getStageProgressFloor(stage: string | null | undefined): number {
  if (!stage) return 0;
  return STAGE_PROGRESS_FLOOR[stage] ?? 0;
}

export function computeRefreshProgress({
  numericPct,
  stageFloor,
  isStalled,
}: {
  numericPct: number;
  stageFloor: number;
  isStalled: boolean;
}): number {
  const boundedNumeric = Number.isFinite(numericPct)
    ? Math.max(0, Math.min(99, Math.round(numericPct)))
    : 0;
  const boundedStage = Math.max(0, Math.min(99, Math.round(stageFloor)));
  if (!isStalled) {
    return Math.max(boundedNumeric, boundedStage);
  }
  // When backend progress is temporarily static, keep a conservative visual floor by stage.
  return Math.max(boundedNumeric, boundedStage, 5);
}
