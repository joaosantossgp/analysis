"use client";

import {
  AlertTriangleIcon,
  BarChart3Icon,
  Building2Icon,
  CheckCircle2Icon,
  ChevronRightIcon,
  CircleStopIcon,
  Clock3Icon,
  CloudOffIcon,
  DownloadIcon,
  FileClockIcon,
  FilterIcon,
  HistoryIcon,
  LockIcon,
  PlayIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SlidersHorizontalIcon,
  TerminalSquareIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  cancelBatchJob,
  fetchBaseHealth,
  fetchBatchJobs,
  type CompanySectorFilter,
  type CompanySuggestionItem,
  fetchBatchJobStatus,
  fetchBatchRefresh,
  fetchCompanyFilters,
  fetchCompanySuggestions,
  fetchRequestRefresh,
  resolveBatchRefreshCvmRange,
} from "@/lib/api";
import {
  buildBaseHealthSummary,
  buildHistoryRows,
  buildUpdateModeEstimates,
  computeRefreshProgress,
  getStageProgressFloor,
  getDefaultBaseHealthWindow,
  getHistoryState,
  isActiveBatchJob,
  type DataLoadState,
} from "@/lib/update-base-admin";
import { cn } from "@/lib/utils";

type AppState =
  | "idle"
  | "confirming"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "source_unavailable"
  | "no_permission"
  | "already_running";

type UpdateType = "full" | "missing" | "outdated" | "failed";
type UpdateScope = "single_company" | "sector" | "all";
type SingleCompanyMode = "on_demand" | "batch_single";
type LogType = "info" | "success" | "warning" | "error" | "dim";

type LogLine = {
  time: string;
  message: string;
  type: LogType;
};

type HistoryItem = {
  id: string;
  date: string;
  typeLabel: string;
  status: "success" | "partial" | "failed" | "cancelled";
  duration: string;
  processed: number;
  failures: number;
};

type NavItem = {
  id: string;
  label: string;
  icon: LucideIcon;
};

type OperationalBannerTone = "error" | "warning" | "info";

const REFRESH_STAGES = [
  "planning",
  "download_extract",
  "process_data",
  "persist_reports",
  "finalizing",
] as const;

const UPDATE_TYPE_META: Record<
  UpdateType,
  { label: string; shortLabel: string; icon: LucideIcon }
> = {
  full: {
    label: "Atualizacao completa",
    shortLabel: "Completa",
    icon: RefreshCwIcon,
  },
  missing: {
    label: "Empresas faltantes",
    shortLabel: "Faltantes",
    icon: Building2Icon,
  },
  outdated: {
    label: "Dados desatualizados",
    shortLabel: "Desatualizadas",
    icon: FileClockIcon,
  },
  failed: {
    label: "Reprocessar falhas",
    shortLabel: "Com falha",
    icon: RotateCcwIcon,
  },
};

const STATUS_OPTIONS = [
  { value: "all", label: "Todos os status" },
  { value: "missing", label: "Sem dados" },
  { value: "outdated", label: "Desatualizado" },
  { value: "failed", label: "Com falha" },
  { value: "active", label: "Ativo" },
];

function formatNumber(value: number) {
  return value.toLocaleString("pt-BR");
}

function formatPercent(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "n/d";
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function formatDateTimeLabel(value: string | null) {
  if (!value) return "Nao verificada";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function nowAsLogTime() {
  const now = new Date();
  return [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cn("text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground", className)}>
      {children}
    </p>
  );
}

function StatusBadge({
  tone,
  children,
}: {
  tone: "success" | "warning" | "error" | "neutral" | "running";
  children: React.ReactNode;
}) {
  const styles = {
    success: "border-emerald-400/25 bg-emerald-400/10 text-emerald-300",
    warning: "border-amber-400/25 bg-amber-400/10 text-amber-300",
    error: "border-destructive/25 bg-destructive/10 text-destructive",
    neutral: "border-border/70 bg-muted/45 text-muted-foreground",
    running: "border-primary/25 bg-primary/10 text-primary",
  };

  return (
    <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.14em]", styles[tone])}>
      {children}
    </span>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: LucideIcon; title: string }) {
  return (
    <div className="mb-4 flex items-center gap-2.5">
      <Icon className="size-4.5 text-primary" strokeWidth={1.8} />
      <h2 className="font-heading text-lg font-semibold tracking-[-0.01em]">{title}</h2>
    </div>
  );
}

function OperationalBanner({
  tone,
  icon: Icon,
  title,
  description,
  action,
}: {
  tone: OperationalBannerTone;
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  const toneClasses = {
    error: "border-destructive/20 bg-destructive/5",
    warning: "border-amber-400/20 bg-amber-400/5",
    info: "border-primary/25 bg-primary/5",
  } as const;
  const iconClasses = {
    error:
      "border-destructive/25 bg-destructive/10 text-destructive",
    warning:
      "border-amber-400/25 bg-amber-400/10 text-amber-300",
    info: "border-primary/25 bg-primary/10 text-primary",
  } as const;

  return (
    <Card className={cn("animate-in rounded-[1.15rem]", toneClasses[tone])}>
      <CardContent className="flex flex-col gap-4 px-5 sm:flex-row sm:items-center">
        <div
          className={cn(
            "flex size-11 shrink-0 items-center justify-center rounded-[0.9rem] border",
            iconClasses[tone],
          )}
        >
          <Icon className="size-5" />
        </div>
        <div className="flex-1">
          <h3 className="font-heading font-semibold">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
        {action}
      </CardContent>
    </Card>
  );
}

function SourceHealth({ status }: { status: "available" | "partial" | "offline" }) {
  const map = {
    available: {
      icon: CheckCircle2Icon,
      label: "Disponivel",
      className: "text-emerald-300",
    },
    partial: {
      icon: AlertTriangleIcon,
      label: "Parcial",
      className: "text-amber-300",
    },
    offline: {
      icon: CloudOffIcon,
      label: "Offline",
      className: "text-destructive",
    },
  };
  const item = map[status];
  const Icon = item.icon;

  return (
    <div className={cn("flex items-center gap-1.5 text-sm font-medium", item.className)}>
      <Icon className="size-4" strokeWidth={1.8} />
      {item.label}
    </div>
  );
}

function StatTile({
  label,
  value,
  subvalue,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string;
  subvalue?: string;
  icon: LucideIcon;
  tone?: "default" | "success" | "warning";
}) {
  const toneClass = {
    default: "text-foreground",
    success: "text-emerald-300",
    warning: "text-amber-300",
  };

  return (
    <Card className="rounded-[1.1rem] bg-card/92 shadow-[0_18px_50px_-42px_rgba(16,30,24,0.35)]">
      <CardContent className="space-y-3 px-4">
        <div className="flex items-start justify-between gap-3">
          <Eyebrow>{label}</Eyebrow>
          <Icon className={cn("size-4", toneClass[tone])} strokeWidth={1.8} />
        </div>
        <div className={cn("font-heading text-3xl font-semibold tabular-nums tracking-[-0.03em]", toneClass[tone])}>
          {value}
        </div>
        {subvalue ? <p className="text-xs text-muted-foreground">{subvalue}</p> : null}
      </CardContent>
    </Card>
  );
}

function AdminSelect({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<string | { value: string; label: string }>;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-[0.75rem] border border-border/70 bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-3 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {options.map((option) => {
          const item = typeof option === "string" ? { value: option, label: option } : option;
          return (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          );
        })}
      </select>
    </label>
  );
}

function AdminInput({
  label,
  placeholder,
  value,
  onChange,
  disabled,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </span>
      <input
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full rounded-[0.75rem] border border-input bg-background px-3 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-3 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-50"
      />
    </label>
  );
}

function LogEntry({ line }: { line: LogLine }) {
  const colors: Record<LogType, string> = {
    info: "text-sky-300",
    success: "text-emerald-300",
    warning: "text-amber-300",
    error: "text-destructive",
    dim: "text-muted-foreground",
  };

  return (
    <div className="grid grid-cols-[4rem_1fr] gap-3 py-0.5 font-mono text-xs leading-5">
      <span className="text-muted-foreground">{line.time}</span>
      <span className={colors[line.type]}>{line.message}</span>
    </div>
  );
}

function HistoryRow({ item }: { item: HistoryItem }) {
  const tone = {
    success: "success",
    partial: "warning",
    failed: "error",
    cancelled: "neutral",
  } as const;

  return (
    <div className="grid min-w-[760px] grid-cols-[160px_115px_110px_90px_110px_75px_36px] items-center gap-3 border-b border-border/45 px-5 py-3 last:border-b-0">
      <span className="font-mono text-xs text-foreground/86">{item.date}</span>
      <span className="text-sm text-muted-foreground">{item.typeLabel}</span>
      <StatusBadge tone={tone[item.status]}>
        {item.status === "partial" ? "Parcial" : item.status === "failed" ? "Falhou" : item.status === "cancelled" ? "Cancelada" : "Sucesso"}
      </StatusBadge>
      <span className="font-mono text-xs text-muted-foreground">{item.duration}</span>
      <span className="font-mono text-xs text-foreground">{formatNumber(item.processed)}</span>
      <span className={cn("font-mono text-xs", item.failures > 0 ? "text-destructive" : "text-muted-foreground")}>
        {item.failures}
      </span>
      <Button variant="ghost" size="icon-sm" aria-label="Abrir detalhes do historico">
        <ChevronRightIcon className="size-4" />
      </Button>
    </div>
  );
}

function ConfirmationDialog({
  updateType,
  impactLabel,
  durationLabel,
  filters,
  onCancel,
  onConfirm,
}: {
  updateType: UpdateType;
  impactLabel: string;
  durationLabel: string;
  filters: string[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const meta = UPDATE_TYPE_META[updateType];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm">
      <Card className="w-full max-w-lg rounded-[1.35rem] border-border/70 bg-card shadow-[0_30px_90px_-40px_rgba(0,0,0,0.6)]">
        <CardHeader className="border-b border-border/60 pb-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Eyebrow className="mb-2">Confirmacao obrigatoria</Eyebrow>
              <CardTitle className="text-xl">Iniciar atualizacao em massa?</CardTitle>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={onCancel} aria-label="Fechar confirmacao">
              <XIcon className="size-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-5 px-5">
          <div className="rounded-[1rem] border border-amber-400/20 bg-amber-400/8 p-4 text-sm leading-6 text-amber-100/90">
            Esta operacao pode reprocessar muitas companhias e deve ser usada apenas para
            manutencao da base. Para uma empresa individual, use o fluxo on-demand da pagina da companhia.
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-[0.95rem] border border-border/60 bg-background/70 p-4">
              <Eyebrow>Tipo</Eyebrow>
              <p className="mt-2 font-medium">{meta.label}</p>
            </div>
            <div className="rounded-[0.95rem] border border-border/60 bg-background/70 p-4">
              <Eyebrow>Impacto estimado</Eyebrow>
              <p className="mt-2 font-mono font-medium">{impactLabel}</p>
            </div>
            <div className="rounded-[0.95rem] border border-border/60 bg-background/70 p-4">
              <Eyebrow>Duracao prevista</Eyebrow>
              <p className="mt-2 font-mono font-medium">{durationLabel}</p>
            </div>
            <div className="rounded-[0.95rem] border border-border/60 bg-background/70 p-4">
              <Eyebrow>Filtros</Eyebrow>
              <p className="mt-2 text-sm text-muted-foreground">
                {filters.length ? `${filters.length} ativo(s)` : "Nenhum"}
              </p>
            </div>
          </div>
          {filters.length ? (
            <div className="flex flex-wrap gap-2">
              {filters.map((filter) => (
                <span key={filter} className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs text-primary">
                  {filter}
                </span>
              ))}
            </div>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>
              Cancelar
            </Button>
            <Button onClick={onConfirm}>
              <PlayIcon className="size-4" />
              Iniciar agora
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

type UpdateBasePageProps = {
  initialSectors?: CompanySectorFilter[];
};

function parseUpdateBaseSearchParams(sp: URLSearchParams): {
  updateScope: UpdateScope;
  singleCompanyMode: SingleCompanyMode;
  updateType: UpdateType;
  singleCvm: string;
  filterSector: string;
  filterStatus: string;
  filterCvmFrom: string;
  filterCvmTo: string;
  activeSection: string;
  jobId: string | null;
} {
  const scope = sp.get("scope");
  const updateScope: UpdateScope =
    scope === "single_company" || scope === "sector" || scope === "all" ? scope : "all";

  const mode = sp.get("mode");
  const updateType: UpdateType =
    mode === "full" || mode === "missing" || mode === "outdated" || mode === "failed" ? mode : "full";

  const sectorParam = sp.get("sector");
  const filterSector = sectorParam && sectorParam.length > 0 ? sectorParam : "all";

  const statusParam = sp.get("status");
  const filterStatus = statusParam && statusParam.length > 0 ? statusParam : "all";

  const cvmFrom = sp.get("cvm_from") ?? "";
  const cvmTo = sp.get("cvm_to") ?? "";

  const singleCvmParam = sp.get("single_cvm") ?? "";

  const singleMode = sp.get("single_mode");
  const singleCompanyMode: SingleCompanyMode =
    singleMode === "on_demand" || singleMode === "batch_single" ? singleMode : "on_demand";

  const sectionParam = sp.get("section");
  const activeSection = sectionParam && sectionParam.length > 0 ? sectionParam : "status";

  const jobParam = sp.get("job_id");
  const jobId = jobParam && jobParam.length > 0 ? jobParam : null;

  return {
    updateScope,
    singleCompanyMode,
    updateType,
    singleCvm: singleCvmParam,
    filterSector,
    filterStatus,
    filterCvmFrom: cvmFrom,
    filterCvmTo: cvmTo,
    activeSection,
    jobId,
  };
}

export function UpdateBasePage({ initialSectors = [] }: UpdateBasePageProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlBoot = useMemo(() => {
    return parseUpdateBaseSearchParams(new URLSearchParams(searchParams.toString()));
    // One-shot bootstrap from the initial URL (matches legacy hydration effect).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [appState, setAppState] = useState<AppState>("idle");
  const [updateScope, setUpdateScope] = useState<UpdateScope>(urlBoot.updateScope);
  const [singleCompanyMode, setSingleCompanyMode] = useState<SingleCompanyMode>(urlBoot.singleCompanyMode);
  const [updateType, setUpdateType] = useState<UpdateType>(urlBoot.updateType);
  const [singleCvm, setSingleCvm] = useState(urlBoot.singleCvm);
  const [singleCompanyQuery, setSingleCompanyQuery] = useState("");
  const [singleCompanySuggestions, setSingleCompanySuggestions] = useState<CompanySuggestionItem[]>([]);
  const [singleCompanySuggestionState, setSingleCompanySuggestionState] = useState<DataLoadState>("available");
  const [selectedSingleCompany, setSelectedSingleCompany] = useState<CompanySuggestionItem | null>(null);
  const [filterSector, setFilterSector] = useState(urlBoot.filterSector);
  const [filterStatus, setFilterStatus] = useState(urlBoot.filterStatus);
  const [filterCvmFrom, setFilterCvmFrom] = useState(urlBoot.filterCvmFrom);
  const [filterCvmTo, setFilterCvmTo] = useState(urlBoot.filterCvmTo);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [processed, setProcessed] = useState(0);
  const [successCount, setSuccessCount] = useState(0);
  const [failCount, setFailCount] = useState(0);
  const [currentCompany, setCurrentCompany] = useState("");
  const [currentStep, setCurrentStep] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [activeSection, setActiveSection] = useState(urlBoot.activeSection);
  const [jobId, setJobId] = useState<string | null>(urlBoot.jobId);
  const [totalFromJob, setTotalFromJob] = useState(0);
  const [baseHealth, setBaseHealth] = useState<Awaited<ReturnType<typeof fetchBaseHealth>> | null>(null);
  const [baseHealthState, setBaseHealthState] = useState<DataLoadState>("loading");
  const [sectors, setSectors] = useState<CompanySectorFilter[]>(initialSectors);
  const [sectorState, setSectorState] = useState<DataLoadState>(
    initialSectors.length ? "available" : "loading",
  );
  const [batchJobs, setBatchJobs] = useState<Awaited<ReturnType<typeof fetchBatchJobs>>["items"]>([]);
  const [jobsState, setJobsState] = useState<DataLoadState>("loading");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [showSourceTechnicalDetails, setShowSourceTechnicalDetails] = useState(false);
  const [showExecutionTechnicalDetails, setShowExecutionTechnicalDetails] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logRef = useRef<HTMLDivElement | null>(null);
  const lastLogCountRef = useRef(0);
  const lastProgressRef = useRef(0);
  const stalledPollCountRef = useRef(0);
  const urlHydratedRef = useRef(true);
  const urlSyncRef = useRef(false);

  const trimmedSingleQuery = singleCompanyQuery.trim();
  const shouldFetchSuggestions = updateScope === "single_company" && trimmedSingleQuery.length >= 2;
  const visibleSuggestions = shouldFetchSuggestions ? singleCompanySuggestions : [];
  const visibleSuggestionState = shouldFetchSuggestions ? singleCompanySuggestionState : "available";

  const isCancelling = appState === "cancelling";
  const isCancelled = appState === "cancelled";
  const isActiveJob = appState === "running" || appState === "already_running" || isCancelling;
  const isRunning = appState === "running" || appState === "already_running";
  const isCompleted = appState === "completed";
  const canRun = appState === "idle";
  const canReset = isCompleted || isCancelled;
  const progressTone = isCancelling || isCancelled ? "warning" : isCompleted ? "success" : "running";
  const progressLabel = isCancelling
    ? "Cancelando..."
    : isCancelled
      ? "Cancelado"
      : isCompleted
        ? "Concluido"
        : "Em execucao...";
  const progressBadge = isCancelling
    ? "Cancelando"
    : isCancelled
      ? "Cancelado"
      : isCompleted
        ? "Concluido"
        : "Executando";
  const baseSummary = useMemo(
    () => buildBaseHealthSummary(baseHealth, sectors),
    [baseHealth, sectors],
  );
  const sectorOptions = useMemo(
    () => [
      { value: "all", label: "Todos os setores" },
      ...sectors.map((sector) => ({
        value: sector.sector_slug,
        label: `${sector.sector_name} (${formatNumber(sector.company_count)})`,
      })),
    ],
    [sectors],
  );
  const selectedSector = sectors.find(
    (sector) => sector.sector_slug === filterSector,
  );
  const updateModeEstimates = useMemo(
    () =>
      buildUpdateModeEstimates({
        health: baseHealth,
        sectors,
        selectedSectorSlug: filterSector !== "all" ? filterSector : null,
      }),
    [baseHealth, filterSector, sectors],
  );
  const selectedModeEstimate = updateModeEstimates[updateType];
  const total = totalFromJob || selectedModeEstimate.affected || 0;
  const selectedImpactLabel =
    updateScope === "single_company"
      ? "1 empresa"
      : selectedModeEstimate.affected != null
        ? `${formatNumber(selectedModeEstimate.affected)} ${selectedModeEstimate.unitLabel}`
        : "Resolvido ao iniciar";
  const activeBatchJobCount = batchJobs.filter(isActiveBatchJob).length;
  const historyItems: HistoryItem[] = buildHistoryRows(batchJobs);
  const historyState = getHistoryState({
    jobsState,
    activeJobCount: activeBatchJobCount,
    historyCount: historyItems.length,
  });
  const sourceHealthStatus =
    appState === "source_unavailable" || baseHealthState === "unavailable"
      ? "offline"
      : baseHealthState === "loading" || sectorState === "loading"
        ? "partial"
        : "available";
  const resolvedCvmRange = useMemo(
    () => resolveBatchRefreshCvmRange(filterCvmFrom, filterCvmTo),
    [filterCvmFrom, filterCvmTo],
  );
  const cvmRangeError = resolvedCvmRange.error;
  const hasInvalidCvmRange = cvmRangeError !== null;
  const parsedSingleCvm = Number(singleCvm.trim());
  const hasSingleCvmInput = singleCvm.trim().length > 0;
  const selectedSingleCompanyCode = selectedSingleCompany?.cd_cvm ?? null;
  const effectiveSingleCompanyCvm = selectedSingleCompanyCode ?? (hasSingleCvmInput ? parsedSingleCvm : null);
  const hasInvalidSingleCvm =
    updateScope === "single_company" &&
    (effectiveSingleCompanyCvm == null ||
      !Number.isFinite(effectiveSingleCompanyCvm) ||
      effectiveSingleCompanyCvm <= 0);
  const isSingleBatchMode = updateScope === "single_company" && singleCompanyMode === "batch_single";

  const activeFilters = useMemo(() => {
    const filters: string[] = [];
    if (updateScope === "single_company" && hasSingleCvmInput) {
      if (selectedSingleCompany) {
        filters.push(
          `Empresa: ${selectedSingleCompany.company_name}${selectedSingleCompany.ticker_b3 ? ` (${selectedSingleCompany.ticker_b3})` : ""}`,
        );
      } else {
        filters.push(`Empresa CVM: ${singleCvm.trim()}`);
      }
      filters.push(
        singleCompanyMode === "on_demand" ? "Modo: Rapido (on-demand)" : "Modo: Lote compativel",
      );
      return filters;
    }
    if (updateScope === "sector" && selectedSector) {
      filters.push(`Setor: ${selectedSector.sector_name}`);
    }
    if (filterStatus !== "all") {
      filters.push(`Status: ${STATUS_OPTIONS.find((item) => item.value === filterStatus)?.label ?? filterStatus}`);
    }
    if (filterCvmFrom) filters.push(`CVM >= ${filterCvmFrom}`);
    if (filterCvmTo) filters.push(`CVM <= ${filterCvmTo}`);
    return filters;
  }, [filterCvmFrom, filterCvmTo, filterStatus, hasSingleCvmInput, selectedSector, selectedSingleCompany, singleCompanyMode, singleCvm, updateScope]);

  const navItems: NavItem[] = useMemo(
    () => [
      { id: "status", label: "Estado da base", icon: BarChart3Icon },
      { id: "controls", label: "Controles", icon: SlidersHorizontalIcon },
      ...(isActiveJob || isCompleted || isCancelled ? [{ id: "progress", label: "Progresso", icon: Clock3Icon }] : []),
      ...(isCompleted ? [{ id: "results", label: "Resultados", icon: CheckCircle2Icon }] : []),
      { id: "history", label: "Historico", icon: HistoryIcon },
    ],
    [isActiveJob, isCancelled, isCompleted],
  );

  function addLog(message: string, type: LogType = "info") {
    setLogs((current) => [...current, { time: nowAsLogTime(), message, type }].slice(-100));
  }

  function clearTimer() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }

  function upsertBatchJob(job: (typeof batchJobs)[number]) {
    setBatchJobs((current) => {
      const next = current.filter((item) => item.job_id !== job.job_id);
      return [job, ...next];
    });
    setJobsState("available");
  }

  async function handleConfirm() {
    const currentRange = resolveBatchRefreshCvmRange(filterCvmFrom, filterCvmTo);
    const shouldValidateBatchRange = updateScope !== "single_company";

    if (shouldValidateBatchRange && currentRange.error) {
      setAppState("idle");
      setDispatchError(currentRange.error);
      return;
    }

    clearTimer();
    lastLogCountRef.current = 0;
    setAppState("running");
    setDispatchError(null);
    setProgress(0);
    setProcessed(0);
    setSuccessCount(0);
    setFailCount(0);
    setElapsed(0);
    setCurrentCompany("");
    setCurrentStep("");
    setLogs([]);
    setJobId(null);
    setTotalFromJob(0);
    lastProgressRef.current = 0;
    stalledPollCountRef.current = 0;

    if (updateScope === "single_company" && singleCompanyMode === "on_demand") {
      if (hasInvalidSingleCvm) {
        setAppState("idle");
        setDispatchError("Informe um codigo CVM valido para atualizar uma empresa especifica.");
        return;
      }
      const cdCvm = Math.trunc(effectiveSingleCompanyCvm ?? 0);
      addLog(`Iniciando atualizacao rapida da empresa ${cdCvm}...`, "info");
      try {
        const dispatch = await fetchRequestRefresh(cdCvm);
        addLog(dispatch.message, dispatch.status === "already_current" ? "success" : "info");
        if (dispatch.job_id) {
          setJobId(dispatch.job_id);
          setTotalFromJob(1);
          upsertBatchJob({
            job_id: dispatch.job_id,
            state: "queued",
            mode: "missing",
            queued: 1,
            processed: 0,
            failures: 0,
            accepted_at: dispatch.accepted_at,
            log_lines: [],
          });
          startPolling(dispatch.job_id);
          return;
        }
        setProgress(100);
        setProcessed(1);
        setSuccessCount(1);
        setElapsed(0);
        setAppState("completed");
      } catch (error) {
        setAppState("source_unavailable");
        setDispatchError(error instanceof Error ? error.message : "Falha ao iniciar atualizacao on-demand.");
        addLog(error instanceof Error ? error.message : "Falha ao iniciar atualizacao on-demand.", "error");
      }
      return;
    }

    addLog("Iniciando atualizacao em lote...", "info");
    addLog(`Tipo: ${UPDATE_TYPE_META[updateType].shortLabel}`, "dim");

    let dispatch: Awaited<ReturnType<typeof fetchBatchRefresh>>;
    try {
      dispatch = await fetchBatchRefresh({
        mode: updateType,
        sectorSlug: updateScope === "sector" ? selectedSector?.sector_slug ?? null : null,
        statusFilter: filterStatus !== "all" ? filterStatus : null,
        cvmRange:
          isSingleBatchMode
            ? { start: Math.trunc(effectiveSingleCompanyCvm ?? 0), end: Math.trunc(effectiveSingleCompanyCvm ?? 0) }
            : currentRange.cvmRange,
      });
    } catch (error) {
      setAppState("source_unavailable");
      setDispatchError(
        error instanceof Error
          ? error.message
          : "Falha ao conectar ao servico de atualizacao.",
      );
      addLog(
        error instanceof Error
          ? error.message
          : "Falha ao conectar ao servico de atualizacao.",
        "error",
      );
      return;
    }

    if (dispatch.status === "already_running") {
      setAppState("already_running");
      addLog("Ja existe uma atualizacao em andamento.", "warning");
      if (dispatch.job_id) {
        setJobId(dispatch.job_id);
        upsertBatchJob({
          job_id: dispatch.job_id,
          state: "running",
          mode: updateType,
          queued: dispatch.queued ?? selectedModeEstimate.affected ?? 0,
          processed: 0,
          failures: 0,
          log_lines: [],
        });
        startPolling(dispatch.job_id);
      }
      return;
    }

    if (dispatch.status === "already_current") {
      setAppState("completed");
      addLog(dispatch.message, "success");
      return;
    }

    if (dispatch.status === "error") {
      setAppState("source_unavailable");
      setDispatchError(dispatch.message ?? "Erro ao iniciar atualizacao.");
      addLog(dispatch.message ?? "Erro ao iniciar atualizacao.", "error");
      return;
    }

    const jid = dispatch.job_id ?? "";
    const queuedCount =
      dispatch.queued ??
      (isSingleBatchMode
        ? 1
        : selectedModeEstimate.affected ?? 0);
    setJobId(jid);
    setTotalFromJob(queuedCount);
    if (jid) {
      upsertBatchJob({
        job_id: jid,
        state: "queued",
        mode: updateType,
        queued: queuedCount,
        processed: 0,
        failures: 0,
        accepted_at: new Date().toISOString(),
        log_lines: [],
      });
    }
    addLog(`Job ${jid.slice(0, 8)} enfileirado (${queuedCount} empresas).`, "dim");
    startPolling(jid);
  }

  function startPolling(jid: string) {
    const startedAt = Date.now();
    intervalRef.current = setInterval(() => {
      void (async () => {
        let status: Awaited<ReturnType<typeof fetchBatchJobStatus>>;
        try {
          status = await fetchBatchJobStatus(jid);
        } catch {
          return;
        }

        const queued = status.queued || 1;
        const numericPct = Math.min(Math.round((status.processed / queued) * 100), 99);
        upsertBatchJob({ ...status, mode: status.mode ?? updateType });

        setProcessed(status.processed);
        setFailCount(status.failures);
        setSuccessCount(Math.max(0, status.processed - status.failures));
        setElapsed(Math.floor((Date.now() - startedAt) / 1000));
        if (status.current_cvm != null) setCurrentCompany(String(status.current_cvm));
        if (status.stage) setCurrentStep(status.stage);

        const logLines = status.log_lines ?? [];
        const newLines = logLines.slice(lastLogCountRef.current);
        lastLogCountRef.current = logLines.length;
        newLines.forEach((line) => addLog(line, "info"));
        const stageFloor = getStageProgressFloor(status.stage ?? null);
        const hasActivity = newLines.length > 0 || status.processed !== lastProgressRef.current;
        if (hasActivity) {
          stalledPollCountRef.current = 0;
        } else {
          stalledPollCountRef.current += 1;
        }
        lastProgressRef.current = status.processed;
        const isStalled = stalledPollCountRef.current >= 3;
        const displayPct = computeRefreshProgress({
          numericPct,
          stageFloor,
          isStalled,
        });
        setProgress(displayPct);

        const TERMINAL = new Set(["success", "error", "cancelled", "interrupted"]);
        if (TERMINAL.has(status.state)) {
          clearTimer();
          setProgress(status.state === "success" ? 100 : displayPct);
          setAppState(status.state === "cancelled" ? "cancelled" : "completed");
          addLog(
            status.state === "success"
              ? `Atualizacao concluida: ${status.processed} processadas.`
              : status.state === "cancelled"
                ? "Atualizacao cancelada pelo backend."
                : (status.error ?? `Atualizacao finalizada com estado: ${status.state}.`),
            status.state === "success" ? "success" : "warning",
          );
        }
      })();
    }, 2500);
  }

  async function handleCancel() {
    if (appState === "confirming") {
      setAppState("idle");
      return;
    }

    if (appState === "running" || appState === "already_running") {
      if (!jobId) {
        addLog("Cancelamento indisponivel: job ainda nao identificado.", "error");
        return;
      }

      const previousState = appState;
      setAppState("cancelling");
      addLog("Solicitando cancelamento do job...", "warning");

      try {
        const result = await cancelBatchJob(jobId);
        addLog(
          result.message || "Cancelamento solicitado. Aguardando confirmacao do backend.",
          "warning",
        );
      } catch (error) {
        setAppState(previousState);
        addLog(
          error instanceof Error ? error.message : "Falha ao solicitar cancelamento.",
          "error",
        );
      }
    }
  }

  function handleReset() {
    clearTimer();
    setAppState("idle");
    setDispatchError(null);
    setProgress(0);
    setProcessed(0);
    setSuccessCount(0);
    setFailCount(0);
    setCurrentCompany("");
    setCurrentStep("");
    setElapsed(0);
    setLogs([]);
    setJobId(null);
    setTotalFromJob(0);
    lastProgressRef.current = 0;
    stalledPollCountRef.current = 0;
  }

  function handleStartRequest() {
    if (updateScope === "single_company" && hasInvalidSingleCvm) {
      setDispatchError("Informe um codigo CVM valido para atualizar uma empresa especifica.");
      return;
    }
    if (cvmRangeError) {
      setDispatchError(cvmRangeError);
      return;
    }
    setDispatchError(null);
    setAppState("confirming");
  }

  function scrollToSection(id: string) {
    setActiveSection(id);
    document.getElementById(`section-${id}`)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  useEffect(() => {
    let alive = true;
    const window = getDefaultBaseHealthWindow();

    void fetchBaseHealth(window)
      .then((health) => {
        if (!alive) return;
        setBaseHealth(health);
        setBaseHealthState("available");
      })
      .catch(() => {
        if (!alive) return;
        setBaseHealth(null);
        setBaseHealthState("unavailable");
      });

    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (initialSectors.length) {
      return;
    }

    let alive = true;
    void fetchCompanyFilters()
      .then((filters) => {
        if (!alive) return;
        setSectors(filters.sectors);
        setSectorState("available");
      })
      .catch(() => {
        if (!alive) return;
        setSectors([]);
        setSectorState("unavailable");
      });

    return () => {
      alive = false;
    };
  }, [initialSectors]);

  useEffect(() => {
    if (!shouldFetchSuggestions) {
      return;
    }

    let alive = true;

    void (async () => {
      await Promise.resolve();
      if (!alive) return;
      setSingleCompanySuggestionState("loading");
      try {
        const payload = await fetchCompanySuggestions(trimmedSingleQuery, 8);
        if (!alive) return;
        setSingleCompanySuggestions(payload.items);
        setSingleCompanySuggestionState("available");
      } catch {
        if (!alive) return;
        setSingleCompanySuggestions([]);
        setSingleCompanySuggestionState("unavailable");
      }
    })();

    return () => {
      alive = false;
    };
  }, [shouldFetchSuggestions, trimmedSingleQuery]);

  useEffect(() => {
    let alive = true;
    void fetchBatchJobs()
      .then((payload) => {
        if (!alive) return;
        setBatchJobs(payload.items);
        setJobsState("available");
      })
      .catch(() => {
        if (!alive) return;
        setBatchJobs([]);
        setJobsState("unavailable");
      });

    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => () => clearTimer(), []);

  useEffect(() => {
    if (!urlHydratedRef.current || urlSyncRef.current) return;
    const params = new URLSearchParams(searchParams.toString());
    const setOrDelete = (key: string, value: string | null) => {
      if (value === null || value === "") params.delete(key);
      else params.set(key, value);
    };
    setOrDelete("scope", updateScope);
    setOrDelete("mode", updateType);
    setOrDelete("sector", updateScope === "sector" ? filterSector : null);
    setOrDelete("status", filterStatus !== "all" ? filterStatus : null);
    setOrDelete("cvm_from", filterCvmFrom || null);
    setOrDelete("cvm_to", filterCvmTo || null);
    setOrDelete("single_cvm", updateScope === "single_company" ? singleCvm : null);
    setOrDelete("single_mode", updateScope === "single_company" ? singleCompanyMode : null);
    setOrDelete("section", activeSection || null);
    setOrDelete("job_id", jobId || null);
    const next = params.toString();
    const current = searchParams.toString();
    if (next === current) return;
    urlSyncRef.current = true;
    router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    queueMicrotask(() => {
      urlSyncRef.current = false;
    });
  }, [
    activeSection,
    filterCvmFrom,
    filterCvmTo,
    filterSector,
    filterStatus,
    jobId,
    pathname,
    router,
    searchParams,
    singleCompanyMode,
    singleCvm,
    updateScope,
    updateType,
  ]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const operationalBanner = (() => {
    if (appState === "source_unavailable") {
      return (
        <OperationalBanner
          tone="error"
          icon={CloudOffIcon}
          title="Erro operacional"
          description={
            dispatchError ??
            "O servico de atualizacao nao conseguiu iniciar a operacao. Verifique a API e tente novamente."
          }
          action={(
            <Button variant="outline" onClick={() => setAppState("idle")}>
              <RefreshCwIcon className="size-4" />
              Tentar novamente
            </Button>
          )}
        />
      );
    }
    if (appState === "no_permission") {
      return (
        <OperationalBanner
          tone="warning"
          icon={LockIcon}
          title="Permissao insuficiente"
          description="Atualizacoes em lote exigem permissao de administrador. Voce ainda pode visualizar o estado da base e o historico."
        />
      );
    }
    if (appState === "already_running") {
      return (
        <OperationalBanner
          tone="info"
          icon={RefreshCwIcon}
          title="Atualizacao ja em execucao"
          description="Ja existe um job em andamento. Nao e possivel iniciar uma nova operacao ate ele finalizar."
        />
      );
    }
    if (baseHealthState === "unavailable") {
      return (
        <OperationalBanner
          tone="warning"
          icon={CloudOffIcon}
          title="Fonte parcialmente indisponivel"
          description="Nao foi possivel carregar /base-health. Os controles continuam disponiveis, mas os totais da base podem ficar incompletos."
        />
      );
    }
    return null;
  })();

  const historyEmptyCopy = {
    loading: {
      title: "Carregando jobs",
      description: "Consultando a fonte de refresh para separar historico e job ativo.",
    },
    has_history: {
      title: "",
      description: "",
    },
    active_jobs_no_history: {
      title: "Sem historico finalizado",
      description: `${activeBatchJobCount} job ativo detectado. O historico aparece quando a fonte expuser jobs finalizados.`,
    },
    no_history_no_active_job: {
      title: "Sem historico",
      description: "Nao ha historico persistente de jobs finalizados e tambem nao ha job ativo agora.",
    },
    source_unavailable: {
      title: "Fonte indisponivel",
      description: "Nao foi possivel consultar os jobs de refresh. O historico pode existir, mas a fonte nao respondeu.",
    },
  }[historyState];

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-background">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6 lg:flex-row lg:px-10">
        <aside className="top-20 h-fit shrink-0 rounded-[1.35rem] border border-border/70 bg-card/92 p-3 shadow-[0_20px_70px_-55px_rgba(16,30,24,0.35)] lg:sticky lg:w-64">
          <div className="px-3 py-3">
            <Eyebrow className="mb-1">Operacoes</Eyebrow>
            <h1 className="font-heading text-lg font-semibold tracking-[-0.02em]">
              Atualizar base
            </h1>
          </div>
          <nav className="flex flex-row gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => scrollToSection(item.id)}
                  className={cn(
                    "flex shrink-0 items-center gap-2 rounded-[0.85rem] px-3 py-2 text-left text-sm transition",
                    activeSection === item.id
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-accent/55 hover:text-foreground",
                  )}
                >
                  <Icon className="size-4" strokeWidth={1.8} />
                  {item.label}
                </button>
              );
            })}
          </nav>
          <div className="mt-4 rounded-[1rem] border border-border/55 bg-muted/25 p-3">
            <Eyebrow className="mb-2">Fonte CVM</Eyebrow>
            <SourceHealth status={sourceHealthStatus} />
          </div>
        </aside>

        <div className="min-w-0 flex-1 space-y-7">
          <header className="flex flex-col gap-4 rounded-[1.5rem] border border-border/70 bg-background/88 p-5 shadow-[0_24px_80px_-58px_rgba(16,30,24,0.38)] sm:p-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <Eyebrow className="mb-2">Base empresarial</Eyebrow>
              <h1 className="font-heading text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
                Atualizar base
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
                Atualiza a base empresarial em lote a partir dos dados publicos da CVM. Esta
                operacao reprocessa multiplas companhias abertas e nao substitui o refresh individual.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {isRunning || isCancelling ? (
                <Button variant="outline" onClick={handleCancel} disabled={isCancelling}>
                  {isCancelling ? (
                    <RefreshCwIcon className="size-4 animate-spin" />
                  ) : (
                    <CircleStopIcon className="size-4" />
                  )}
                  {isCancelling ? "Cancelando" : "Cancelar"}
                </Button>
              ) : null}
              {canReset ? (
                <Button variant="ghost" onClick={handleReset}>
                  <RefreshCwIcon className="size-4" />
                  Nova operacao
                </Button>
              ) : null}
            </div>
          </header>

          {operationalBanner}

          <section id="section-status" className="scroll-mt-24">
            <SectionTitle icon={BarChart3Icon} title="Estado da base" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatTile
                label="Total de empresas"
                value={baseSummary.totalCompanies != null ? formatNumber(baseSummary.totalCompanies) : "n/d"}
                subvalue={baseHealthState === "loading" ? "Carregando /base-health" : "Cadastro ativo"}
                icon={Building2Icon}
              />
              <StatTile
                label="Com historico"
                value={baseSummary.companiesWithHistoricalData != null ? formatNumber(baseSummary.companiesWithHistoricalData) : "n/d"}
                subvalue="Ao menos um ano anual disponivel"
                icon={CheckCircle2Icon}
                tone="success"
              />
              <StatTile
                label="Sem historico"
                value={baseSummary.companiesWithoutHistoricalData != null ? formatNumber(baseSummary.companiesWithoutHistoricalData) : "n/d"}
                subvalue="Cadastradas, ainda sem leitura local"
                icon={FileClockIcon}
                tone="warning"
              />
              <StatTile
                label="Ultima verificacao"
                value={formatDateTimeLabel(baseSummary.generatedAt)}
                subvalue={
                  baseSummary.startYear != null && baseSummary.endYear != null
                    ? `Janela ${baseSummary.startYear}-${baseSummary.endYear}`
                    : "Aguardando /base-health"
                }
                icon={Clock3Icon}
              />
              <StatTile
                label="Celulas completas"
                value={baseSummary.completedCells != null ? formatNumber(baseSummary.completedCells) : "n/d"}
                subvalue={`${formatPercent(baseSummary.coveragePct)} da janela`}
                icon={CheckCircle2Icon}
                tone="success"
              />
              <StatTile
                label="Lacunas pendentes"
                value={baseSummary.missingCells != null ? formatNumber(baseSummary.missingCells) : "n/d"}
                subvalue={baseSummary.healthStatus ?? "Fonte indisponivel"}
                icon={AlertTriangleIcon}
                tone="warning"
              />
            </div>

            <Card className="mt-3 rounded-[1.15rem] bg-card/92">
              <CardContent className="px-5">
                <button
                  type="button"
                  onClick={() => setShowSourceTechnicalDetails((value) => !value)}
                  className="flex w-full items-center justify-between py-1 text-left"
                >
                  <Eyebrow>Detalhes tecnicos da fonte</Eyebrow>
                  <ChevronRightIcon
                    className={cn("size-4 text-muted-foreground transition", showSourceTechnicalDetails && "rotate-90")}
                  />
                </button>
                {showSourceTechnicalDetails ? (
                  <div className="mt-3 flex flex-col gap-5 border-t border-border/55 pt-4 lg:flex-row lg:items-center">
                    <div className="flex-1">
                      <div className="flex flex-wrap gap-6">
                        <div>
                          <p className="mb-1 text-xs text-muted-foreground">CVM DFP/ITR</p>
                          <SourceHealth status={sourceHealthStatus} />
                        </div>
                        <div>
                          <p className="mb-1 text-xs text-muted-foreground">Dados cadastrais</p>
                          <SourceHealth status={sectorState === "unavailable" ? "offline" : sectorState === "loading" ? "partial" : "available"} />
                        </div>
                        <div>
                          <p className="mb-1 text-xs text-muted-foreground">API auxiliar</p>
                          <SourceHealth status={jobsState === "unavailable" ? "offline" : jobsState === "loading" ? "partial" : "available"} />
                        </div>
                      </div>
                    </div>
                    <div>
                      <Eyebrow className="mb-1">Ultima verificacao</Eyebrow>
                      <p className="font-mono text-sm tabular-nums">{formatDateTimeLabel(baseSummary.generatedAt)}</p>
                    </div>
                  </div>
                ) : (
                  <p className="pb-1 text-sm text-muted-foreground">
                    Exibe saude das fontes, API auxiliar e timestamp da ultima verificacao.
                  </p>
                )}
              </CardContent>
            </Card>
          </section>

          <section id="section-controls" className="scroll-mt-24">
            <SectionTitle icon={SlidersHorizontalIcon} title="Controles de atualizacao" />
            <Card className="rounded-[1.15rem] bg-card/92">
              <CardHeader>
                <Eyebrow>O que voce quer atualizar?</Eyebrow>
              </CardHeader>
              <CardContent className="grid gap-3 px-5 sm:grid-cols-3">
                {[
                  { value: "single_company", label: "Empresa especifica", desc: "Atualiza 1 companhia por codigo CVM" },
                  { value: "sector", label: "Setor especifico", desc: "Atualiza empresas de um setor" },
                  { value: "all", label: "Todas as empresas", desc: "Atualiza toda a base sem recorte" },
                ].map((scope) => (
                  <button
                    key={scope.value}
                    type="button"
                    disabled={!canRun}
                    onClick={() => {
                      setUpdateScope(scope.value as UpdateScope);
                      setDispatchError(null);
                    }}
                    className={cn(
                      "flex min-h-24 flex-col items-start gap-2 rounded-[1rem] border p-4 text-left transition",
                      updateScope === scope.value
                        ? "border-primary/45 bg-primary/8"
                        : "border-border/60 bg-background/70 hover:border-primary/25 hover:bg-muted/25",
                      !canRun && "cursor-not-allowed opacity-60",
                    )}
                  >
                    <p className="font-medium text-foreground">{scope.label}</p>
                    <p className="text-xs leading-5 text-muted-foreground">{scope.desc}</p>
                  </button>
                ))}
              </CardContent>
            </Card>

            {updateScope === "single_company" ? (
              <Card className="mt-3 rounded-[1.15rem] bg-card/92">
                <CardHeader>
                  <Eyebrow>Empresa especifica</Eyebrow>
                </CardHeader>
                <CardContent className="grid gap-3 px-5 sm:grid-cols-2">
                  <div className="space-y-2">
                    <AdminInput
                      label="Buscar empresa (nome ou ticker)"
                      placeholder="Ex: Petrobras ou PETR4"
                      value={singleCompanyQuery}
                      onChange={(value) => {
                        setSingleCompanyQuery(value);
                        setSelectedSingleCompany(null);
                        setDispatchError(null);
                      }}
                      disabled={!canRun}
                    />
                    {visibleSuggestionState === "loading" ? (
                      <p className="text-xs text-muted-foreground">Buscando sugestoes...</p>
                    ) : null}
                    {visibleSuggestions.length > 0 ? (
                      <div className="max-h-40 space-y-1 overflow-y-auto rounded-[0.75rem] border border-border/65 bg-background/60 p-2">
                        {visibleSuggestions.map((item) => (
                          <button
                            key={item.cd_cvm}
                            type="button"
                            className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted/40"
                            onClick={() => {
                              setSelectedSingleCompany(item);
                              setSingleCvm(String(item.cd_cvm));
                              setSingleCompanyQuery(
                                `${item.company_name}${item.ticker_b3 ? ` (${item.ticker_b3})` : ""}`,
                              );
                            }}
                          >
                            <span className="truncate">{item.company_name}</span>
                            <span className="ml-2 shrink-0 text-muted-foreground">
                              {item.ticker_b3 ?? `CVM ${item.cd_cvm}`}
                            </span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <AdminInput
                      label="Codigo CVM (opcional, avancado)"
                      placeholder="Ex: 9512"
                      value={singleCvm}
                      onChange={(value) => {
                        setSingleCvm(value);
                        setSelectedSingleCompany(null);
                        setDispatchError(null);
                      }}
                      disabled={!canRun}
                    />
                    {selectedSingleCompany ? (
                      <div className="rounded-[0.75rem] border border-border/65 bg-muted/25 px-3 py-2 text-xs">
                        <p className="font-medium text-foreground">
                          {selectedSingleCompany.company_name}
                        </p>
                        <p className="text-muted-foreground">
                          {selectedSingleCompany.ticker_b3 ?? "Sem ticker"} - CVM {selectedSingleCompany.cd_cvm}
                        </p>
                      </div>
                    ) : null}
                  </div>
                  <AdminSelect
                    label="Estrategia"
                    value={singleCompanyMode}
                    onChange={(value) => {
                      setSingleCompanyMode(value as SingleCompanyMode);
                      setDispatchError(null);
                    }}
                    options={[
                      { value: "on_demand", label: "Rapido (on-demand)" },
                      { value: "batch_single", label: "Lote compativel (CVM unico)" },
                    ]}
                    disabled={!canRun}
                  />
                </CardContent>
                <div className="px-5 pb-4 text-xs text-muted-foreground">
                  {singleCompanyMode === "on_demand"
                    ? "On-demand e mais rapido para 1 empresa e usa o endpoint dedicado."
                    : "Lote compativel usa o mesmo pipeline de batch com faixa CVM unica."}
                </div>
              </Card>
            ) : null}

            <Card className="mt-3 rounded-[1.15rem] bg-card/92">
              <CardHeader>
                <Eyebrow>Tipo de atualizacao</Eyebrow>
              </CardHeader>
              <CardContent className="grid gap-3 px-5 sm:grid-cols-2 xl:grid-cols-4">
                {(Object.keys(UPDATE_TYPE_META) as UpdateType[]).map((type) => {
                  const item = UPDATE_TYPE_META[type];
                  const estimate = updateModeEstimates[type];
                  const Icon = item.icon;
                  const active = updateType === type;
                  return (
                    <button
                      key={type}
                      type="button"
                      disabled={!canRun || (updateScope === "single_company" && singleCompanyMode === "on_demand")}
                      onClick={() => setUpdateType(type)}
                      className={cn(
                        "flex min-h-32 flex-col items-start gap-3 rounded-[1rem] border p-4 text-left transition",
                        active
                          ? "border-primary/45 bg-primary/8 shadow-[0_18px_44px_-34px_rgba(45,212,191,0.45)]"
                          : "border-border/60 bg-background/70 hover:border-primary/25 hover:bg-muted/25",
                        (!canRun || (updateScope === "single_company" && singleCompanyMode === "on_demand")) &&
                          "cursor-not-allowed opacity-60",
                      )}
                    >
                      <Icon className={cn("size-5", active ? "text-primary" : "text-muted-foreground")} strokeWidth={1.8} />
                      <div>
                        <p className="font-medium text-foreground">{item.label}</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{estimate.description}</p>
                      </div>
                    </button>
                  );
                })}
              </CardContent>
            </Card>

            <Card className="mt-3 rounded-[1.15rem] bg-card/92">
              <CardHeader className="flex-row items-center justify-between">
                <button
                  type="button"
                  onClick={() => setShowAdvancedFilters((value) => !value)}
                  className="flex items-center gap-2 text-left"
                >
                  <Eyebrow>Filtros opcionais</Eyebrow>
                  <ChevronRightIcon
                    className={cn("size-4 text-muted-foreground transition", showAdvancedFilters && "rotate-90")}
                  />
                </button>
                {showAdvancedFilters ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setFilterSector("all");
                      setFilterStatus("all");
                      setFilterCvmFrom("");
                      setFilterCvmTo("");
                      setDispatchError(null);
                    }}
                  >
                    Limpar
                  </Button>
                ) : null}
              </CardHeader>
              {showAdvancedFilters && updateScope !== "single_company" ? (
                <CardContent className="grid gap-3 px-5 sm:grid-cols-2 xl:grid-cols-4">
                  <AdminSelect label="Setor" value={filterSector} onChange={setFilterSector} options={sectorOptions} disabled={!canRun || sectorOptions.length === 1 || updateScope !== "sector"} />
                  <AdminSelect label="Status" value={filterStatus} onChange={setFilterStatus} options={STATUS_OPTIONS} disabled={!canRun} />
                  <AdminInput label="Cod. CVM - de" placeholder="Ex: 1000" value={filterCvmFrom} onChange={(value) => { setFilterCvmFrom(value); setDispatchError(null); }} disabled={!canRun} />
                  <AdminInput label="Cod. CVM - ate" placeholder="Ex: 9999" value={filterCvmTo} onChange={(value) => { setFilterCvmTo(value); setDispatchError(null); }} disabled={!canRun} />
                </CardContent>
              ) : (
                <CardContent className="px-5">
                  <p className="text-sm text-muted-foreground">
                    {updateScope === "single_company"
                      ? "No modo de empresa especifica, use o codigo CVM acima."
                      : "Use filtros apenas quando precisar limitar setor, status ou faixa de CVM."}
                  </p>
                </CardContent>
              )}
              {dispatchError || (updateScope !== "single_company" && hasInvalidCvmRange) || hasInvalidSingleCvm ? (
                <div className="mx-5 mb-4 rounded-[0.95rem] border border-destructive/20 bg-destructive/8 px-4 py-3 text-sm text-destructive">
                  {dispatchError ??
                    (hasInvalidSingleCvm
                      ? "Informe um codigo CVM valido para atualizar uma empresa especifica."
                      : cvmRangeError)}
                </div>
              ) : null}
              {activeFilters.length ? (
                <div className="flex items-center gap-2 px-5 pb-4 text-xs text-primary">
                  <FilterIcon className="size-4" />
                  {activeFilters.length} filtro{activeFilters.length !== 1 ? "s" : ""} ativo{activeFilters.length !== 1 ? "s" : ""}
                </div>
              ) : null}
            </Card>

            {canRun ? (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Button
                  size="lg"
                  onClick={handleStartRequest}
                  disabled={(updateScope !== "single_company" && hasInvalidCvmRange) || hasInvalidSingleCvm}
                >
                  <PlayIcon className="size-4" />
                  {updateScope === "single_company" ? "Iniciar atualizacao da empresa" : "Iniciar atualizacao"}
                </Button>
                <p className="text-xs text-muted-foreground">
                  {selectedImpactLabel} - {selectedModeEstimate.duration}
                </p>
              </div>
            ) : appState === "source_unavailable" ? (
              <div className="mt-4 flex items-center gap-2 rounded-[1rem] border border-destructive/20 bg-destructive/8 px-4 py-3 text-sm text-destructive">
                <CloudOffIcon className="size-4" />
                Fonte CVM indisponivel. Atualizacao bloqueada.
              </div>
            ) : appState === "no_permission" ? (
              <div className="mt-4 flex items-center gap-2 rounded-[1rem] border border-amber-400/20 bg-amber-400/8 px-4 py-3 text-sm text-amber-300">
                <LockIcon className="size-4" />
                Permissao de administrador necessaria para iniciar atualizacoes.
              </div>
            ) : null}
          </section>

          {(isActiveJob || isCompleted || isCancelled) ? (
            <section id="section-progress" className="scroll-mt-24">
              <SectionTitle icon={Clock3Icon} title="Progresso" />
              <Card className="rounded-[1.15rem] bg-card/92">
                <CardContent className="space-y-5 px-5">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      {isActiveJob ? (
                        <RefreshCwIcon className="size-5 animate-spin text-primary" />
                      ) : isCancelled ? (
                        <CircleStopIcon className="size-5 text-amber-300" />
                      ) : (
                        <CheckCircle2Icon className="size-5 text-emerald-300" />
                      )}
                      <span className="font-medium">{progressLabel}</span>
                      <StatusBadge tone={progressTone}>
                        {progressBadge}
                      </StatusBadge>
                    </div>
                    <span className={cn("font-heading text-3xl font-semibold tabular-nums", isCompleted && "text-emerald-300", isCancelled && "text-amber-300")}>
                      {progress}%
                    </span>
                  </div>

                  <Progress value={progress} indicatorClassName={cn(isActiveJob && "animate-pulse")} />
                  {isActiveJob && progress < 100 && total <= 5 ? (
                    <p className="text-xs text-muted-foreground">
                      Lote curto: pode concluir antes de variacoes visiveis na barra.
                    </p>
                  ) : null}

                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                      { label: "Processadas", value: processed, className: "text-foreground" },
                      { label: "Restantes", value: Math.max(total - processed, 0), className: "text-muted-foreground" },
                      { label: "Sucesso", value: successCount, className: "text-emerald-300" },
                      { label: "Falhas", value: failCount, className: failCount ? "text-destructive" : "text-muted-foreground" },
                    ].map((item) => (
                      <div key={item.label}>
                        <Eyebrow className="mb-1">{item.label}</Eyebrow>
                        <p className={cn("font-mono text-2xl font-semibold tabular-nums", item.className)}>{formatNumber(item.value)}</p>
                      </div>
                    ))}
                  </div>

                  {isActiveJob || logs.length ? (
                    <div className="border-t border-border/60 pt-5">
                      <button
                        type="button"
                        onClick={() => setShowExecutionTechnicalDetails((value) => !value)}
                        className="mb-3 flex w-full items-center justify-between text-left"
                      >
                        <Eyebrow>Detalhes tecnicos da execucao</Eyebrow>
                        <ChevronRightIcon
                          className={cn("size-4 text-muted-foreground transition", showExecutionTechnicalDetails && "rotate-90")}
                        />
                      </button>
                      {showExecutionTechnicalDetails ? (
                        <>
                          {isActiveJob ? (
                            <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr_auto] lg:items-center">
                              <div>
                                <Eyebrow className="mb-1">Empresa atual</Eyebrow>
                                <p className="font-mono text-sm font-medium">{currentCompany || "Preparando fila"}</p>
                              </div>
                              <div>
                                <Eyebrow className="mb-2">Etapa</Eyebrow>
                                <div className="flex flex-wrap gap-1.5">
                                  {REFRESH_STAGES.map((step) => (
                                    <span
                                      key={step}
                                      className={cn(
                                        "rounded-full border px-2.5 py-1 font-mono text-xs",
                                        currentStep === step
                                          ? "border-primary/35 bg-primary/12 text-primary"
                                          : "border-border/55 text-muted-foreground",
                                      )}
                                    >
                                      {step}
                                    </span>
                                  ))}
                                </div>
                              </div>
                              <div>
                                <Eyebrow className="mb-1">Tempo decorrido</Eyebrow>
                                <p className="font-mono text-sm tabular-nums">
                                  {String(Math.floor(elapsed / 60)).padStart(2, "0")}:{String(elapsed % 60).padStart(2, "0")}
                                </p>
                              </div>
                            </div>
                          ) : null}

                          {logs.length ? (
                            <div className={cn(isActiveJob && "mt-4")}>
                              <div className="mb-3 flex items-center justify-between">
                                <Eyebrow>Log em tempo real</Eyebrow>
                                <Button variant="ghost" size="sm" disabled>
                                  <DownloadIcon className="size-4" />
                                  Exportar log (em breve)
                                </Button>
                              </div>
                              <div ref={logRef} className="h-48 overflow-y-auto rounded-[0.95rem] border border-border/55 bg-muted/25 p-3">
                                {logs.map((line, index) => (
                                  <LogEntry key={`${line.time}-${index}`} line={line} />
                                ))}
                              </div>
                            </div>
                          ) : null}
                        </>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          Exibe empresa atual, etapa interna e log detalhado da execucao.
                        </p>
                      )}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </section>
          ) : null}

          {isCompleted ? (
            <section id="section-results" className="scroll-mt-24">
              <SectionTitle icon={CheckCircle2Icon} title="Resultados" />
              <Card className="rounded-[1.15rem] bg-card/92">
                <CardContent className="space-y-5 px-5">
                  <div className="flex flex-wrap items-center gap-4">
                    <div className={cn("flex size-12 items-center justify-center rounded-[1rem] border", failCount > 10 ? "border-amber-400/25 bg-amber-400/10 text-amber-300" : "border-emerald-400/25 bg-emerald-400/10 text-emerald-300")}>
                      {failCount > 10 ? <AlertTriangleIcon className="size-6" /> : <CheckCircle2Icon className="size-6" />}
                    </div>
                    <div className="flex-1">
                      <h3 className="font-heading text-lg font-semibold">{failCount > 10 ? "Sucesso parcial" : "Atualizacao concluida"}</h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {formatNumber(total)} empresas processadas em {Math.floor(elapsed / 60)}m {elapsed % 60}s
                      </p>
                    </div>
                    <StatusBadge tone={failCount > 10 ? "warning" : "success"}>{failCount > 10 ? "Parcial" : "Sucesso"}</StatusBadge>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                      { label: "Total processado", value: total, className: "text-foreground" },
                      { label: "Atualizadas", value: successCount, className: "text-emerald-300" },
                      { label: "Ignoradas", value: 0, className: "text-muted-foreground" },
                      { label: "Falhas", value: failCount, className: failCount ? "text-destructive" : "text-muted-foreground" },
                    ].map((item) => (
                      <div key={item.label}>
                        <Eyebrow className="mb-1">{item.label}</Eyebrow>
                        <p className={cn("font-mono text-3xl font-semibold tabular-nums", item.className)}>{formatNumber(item.value)}</p>
                      </div>
                    ))}
                  </div>

                  {failCount > 0 ? (
                    <div className="rounded-[1rem] border border-destructive/15 bg-destructive/5 p-4 text-sm leading-6 text-muted-foreground">
                      {failCount} empresa{failCount !== 1 ? "s" : ""} nao puderam ser atualizadas. Causa mais comum: timeout ao baixar ITR. Verifique o log para detalhes por empresa.
                    </div>
                  ) : null}

                  <div className="flex flex-wrap gap-2 border-t border-border/60 pt-5">
                    {failCount > 0 ? (
                      <Button onClick={handleReset}>
                        <RotateCcwIcon className="size-4" />
                        Reprocessar falhas
                      </Button>
                    ) : null}
                    <Button variant="outline">
                      <TerminalSquareIcon className="size-4" />
                      Ver log detalhado
                    </Button>
                    <Button variant="ghost" onClick={handleReset}>
                      <RefreshCwIcon className="size-4" />
                      Nova operacao
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </section>
          ) : null}

          <section id="section-history" className="scroll-mt-24">
            <SectionTitle icon={HistoryIcon} title="Historico de atualizacoes" />
            <Card className="rounded-[1.15rem] bg-card/92">
              <CardHeader className="flex-row items-center justify-between border-b border-border/55 pb-4">
                <div>
                  <Eyebrow>Jobs de refresh</Eyebrow>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {activeBatchJobCount > 0
                      ? `${activeBatchJobCount} job ativo`
                      : "Sem job ativo"}
                  </p>
                </div>
                <StatusBadge tone={historyState === "source_unavailable" ? "error" : activeBatchJobCount > 0 ? "running" : "neutral"}>
                  {historyState === "source_unavailable" ? "Fonte indisponivel" : activeBatchJobCount > 0 ? "Job ativo" : "Sem job ativo"}
                </StatusBadge>
              </CardHeader>
              <div className="overflow-x-auto">
                <div className="grid min-w-[760px] grid-cols-[160px_115px_110px_90px_110px_75px_36px] gap-3 border-b border-border/55 bg-muted/30 px-5 py-3">
                  {["Data/hora", "Tipo", "Status", "Duracao", "Processadas", "Falhas", ""].map((heading) => (
                    <Eyebrow key={heading}>{heading}</Eyebrow>
                  ))}
                </div>
                {historyItems.length ? (
                  historyItems.map((item) => (
                    <HistoryRow key={item.id} item={item} />
                  ))
                ) : (
                  <div className="min-w-[760px] px-5 py-8">
                    <div className="rounded-[1rem] border border-border/60 bg-muted/20 p-4">
                      <h3 className="font-heading text-sm font-semibold">{historyEmptyCopy.title}</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">{historyEmptyCopy.description}</p>
                    </div>
                  </div>
                )}
              </div>
            </Card>
          </section>
        </div>
      </div>

      {appState === "confirming" ? (
        <ConfirmationDialog
          updateType={updateType}
          impactLabel={selectedImpactLabel}
          durationLabel={selectedModeEstimate.duration}
          filters={activeFilters}
          onCancel={handleCancel}
          onConfirm={handleConfirm}
        />
      ) : null}
    </div>
  );
}
