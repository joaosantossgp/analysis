import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  cancelRefresh,
  defaultRefreshWindow,
  fetchBaseHealth,
  fetchDatabaseDiagnostics,
  fetchRefreshJob,
  fetchRefreshJobs,
  isActiveRefreshJob,
  isTerminalRefreshJob,
  refreshProgress,
  startBaseRefresh,
} from "@/lib/api/updateBase";
import { PageHeader as UnifiedPageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { useRefreshJobInvalidation } from "@/hooks/useRefreshJobInvalidation";
import type {
  BaseHealthSnapshot,
  DatabaseDiagnostics,
  RefreshJobStatus,
} from "@/lib/bridge/types";

const ACTIVE_POLL_MS = 2_000;
const IDLE_POLL_MS = 10_000;
const DIAG_ACTIVE_POLL_MS = 3_000;
const DIAG_IDLE_POLL_MS = 30_000;

export function UpdateBasePage() {
  const queryClient = useQueryClient();
  const defaults = useMemo(() => defaultRefreshWindow(), []);
  const [bridgeReady, setBridgeReady] = useState(false);
  const invalidateRefreshQueries = useRefreshJobInvalidation();

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const jobsQuery = useQuery({
    queryKey: ["refresh-jobs"],
    queryFn: fetchRefreshJobs,
    enabled: bridgeReady,
    refetchInterval: (query) => {
      const items = query.state.data?.mode === "desktop" ? query.state.data.items : [];
      return items.some(isActiveRefreshJob) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    },
  });

  const jobs = jobsQuery.data?.mode === "desktop" ? jobsQuery.data.items : [];
  const activeJobFromList = jobs.find(isActiveRefreshJob) ?? null;
  const latestJob = jobs[0] ?? null;
  const trackedJobId = activeJobFromList?.job_id ?? latestJob?.job_id ?? null;

  const jobQuery = useQuery({
    queryKey: ["refresh-job", trackedJobId],
    queryFn: () => fetchRefreshJob(trackedJobId ?? ""),
    enabled: bridgeReady && Boolean(trackedJobId),
    refetchInterval: (query) => {
      const job = query.state.data?.mode === "desktop" ? query.state.data.job : null;
      return isActiveRefreshJob(job) ? ACTIVE_POLL_MS : false;
    },
  });

  const trackedJob =
    jobQuery.data?.mode === "desktop" ? jobQuery.data.job : activeJobFromList ?? latestJob;
  const isRunning = isActiveRefreshJob(trackedJob) || isActiveRefreshJob(activeJobFromList);

  const healthQuery = useQuery({
    queryKey: ["base-health", defaults.startYear, defaults.endYear],
    queryFn: () =>
      fetchBaseHealth({
        startYear: defaults.startYear,
        endYear: defaults.endYear,
        forceRefresh: true,
      }),
    enabled: bridgeReady,
    refetchInterval: isRunning ? 5_000 : false,
  });

  const diagnosticsQuery = useQuery({
    queryKey: ["db-diagnostics"],
    queryFn: fetchDatabaseDiagnostics,
    enabled: bridgeReady,
    refetchInterval: isRunning ? DIAG_ACTIVE_POLL_MS : DIAG_IDLE_POLL_MS,
  });

  const diagnostics =
    diagnosticsQuery.data?.mode === "desktop" ? diagnosticsQuery.data.diagnostics : null;

  const invalidatedJobRef = useRef<string | null>(null);

  useEffect(() => {
    if (!trackedJob) return;
    if (
      isTerminalRefreshJob(trackedJob) &&
      invalidatedJobRef.current !== trackedJob.job_id
    ) {
      invalidatedJobRef.current = trackedJob.job_id;
      invalidateRefreshQueries();
    }
  }, [trackedJob, invalidateRefreshQueries]);

  const startMutation = useMutation({
    mutationFn: () =>
      startBaseRefresh({
        mode: "missing",
        limit: 9999,
        startYear: defaults.startYear,
        endYear: defaults.endYear,
        cdCvm: null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["refresh-jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["base-health"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => cancelRefresh(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["refresh-jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["base-health"] });
      void queryClient.invalidateQueries({ queryKey: ["db-diagnostics"] });
      if (trackedJobId) {
        void queryClient.invalidateQueries({ queryKey: ["refresh-job", trackedJobId] });
      }
    },
  });

  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.snapshot : null;
  const browserReason =
    healthQuery.data?.mode === "browser"
      ? healthQuery.data.reason
      : jobsQuery.data?.mode === "browser"
        ? jobsQuery.data.reason
        : diagnosticsQuery.data?.mode === "browser"
          ? diagnosticsQuery.data.reason
          : null;

  return (
    <section className="space-y-6">
      <PageHeader bridgeReady={bridgeReady} />

      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}

      <UpdateCard
        disabled={!bridgeReady || isRunning || startMutation.isPending}
        running={isRunning}
        pending={startMutation.isPending}
        activeJob={trackedJob}
        startError={startMutation.error}
        health={health}
        diagnostics={diagnostics}
        onUpdate={() => startMutation.mutate()}
        onCancel={(jobId) => cancelMutation.mutate(jobId)}
        cancelling={cancelMutation.isPending}
      />

      <CompactJobLine job={trackedJob} />
    </section>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function PageHeader({ bridgeReady }: { bridgeReady: boolean }) {
  return (
    <header className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <UnifiedPageHeader
        title="Atualizar Base"
        subtitle="Mantém seu banco local do CVMAnalytics atualizado."
        actions={
          <div className="flex items-center gap-3">
            <Link
              to="/data-coverage"
              className="rounded-full border border-zinc-700 bg-zinc-800/60 px-3 py-1 text-xs text-zinc-200 font-mono hover:text-white"
            >
              Cobertura de dados →
            </Link>
            <span
              className={
                bridgeReady
                  ? "rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200 font-mono"
                  : "rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200 font-mono"
              }
            >
              {bridgeReady ? "Bridge ready" : "Connecting bridge"}
            </span>
          </div>
        }
      />
    </header>
  );
}

function UpdateCard({
  disabled,
  running,
  pending,
  activeJob,
  startError,
  health,
  diagnostics,
  onUpdate,
  onCancel,
  cancelling,
}: {
  disabled: boolean;
  running: boolean;
  pending: boolean;
  activeJob: RefreshJobStatus | null | undefined;
  startError: unknown;
  health: BaseHealthSnapshot | null;
  diagnostics: DatabaseDiagnostics | null;
  onUpdate: () => void;
  onCancel: (jobId: string) => void;
  cancelling: boolean;
}) {
  const progress = activeJob ? refreshProgress(activeJob) : 0;
  const stepLabel = activeJob?.stage ? formatStageHuman(activeJob.stage) : null;
  const lastUpdate = diagnostics?.latest_success_at;

  const statusMessage = running
    ? "Atualizando sua base local…"
    : health && health.pct > 80
      ? "Sua base está atualizada."
      : health && health.pct > 0
        ? "Sua base está parcialmente atualizada. Algumas empresas têm dados pendentes."
        : "Sua base pode estar desatualizada.";

  const statusClass = running
    ? "text-amber-200"
    : health && health.pct > 80
      ? "text-emerald-300"
      : "text-amber-200";

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-medium ${statusClass}`}>{statusMessage}</p>
          {lastUpdate ? (
            <p className="mt-1 text-xs text-zinc-500">
              Última atualização: {formatDateTime(lastUpdate)}
            </p>
          ) : null}
          {running && activeJob ? (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-zinc-400">
                Processando {formatInt(activeJob.processed)} de {formatInt(activeJob.queued)}{" "}
                empresas{stepLabel ? ` · ${stepLabel}` : ""}
              </p>
              <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full bg-cyan-400 transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {running && activeJob ? (
            <button
              type="button"
              disabled={cancelling}
              onClick={() => onCancel(activeJob.job_id)}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-rose-700 hover:text-rose-200 disabled:opacity-50"
            >
              {cancelling ? "Cancelando…" : "Cancelar"}
            </button>
          ) : null}
          <button
            type="button"
            disabled={disabled}
            onClick={onUpdate}
            className="rounded-md border border-emerald-500/50 bg-emerald-500/15 px-5 py-2.5 text-sm font-semibold text-emerald-100 hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-600"
          >
            {pending ? "Iniciando…" : running ? "Atualizando…" : "Atualizar base"}
          </button>
        </div>
      </div>
      {startError ? (
        <p
          role="alert"
          className="mt-4 rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300"
        >
          {startError instanceof Error ? startError.message : String(startError)}
        </p>
      ) : null}
    </article>
  );
}

function CompactJobLine({ job }: { job: RefreshJobStatus | null | undefined }) {
  if (!job || isActiveRefreshJob(job)) return null;
  const ts = job.updated_at ?? job.finished_at ?? null;
  return (
    <p className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-xs text-zinc-500 shadow-lg">
      Último job:{" "}
      <span className={jobBadgeClass(job.state)}>{formatJobState(job.state)}</span>
      {ts ? <span className="ml-2">· {formatDateTime(ts)}</span> : null}
    </p>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatInt(value: number | null | undefined): string {
  return new Intl.NumberFormat("pt-BR").format(Number(value ?? 0));
}

function formatJobState(value: string | null | undefined): string {
  const normalized = String(value ?? "unknown");
  if (normalized === "already_current") return "Already current";
  return normalized.replace(/_/g, " ");
}

function formatStage(value: string): string {
  return value.replace(/_/g, " ");
}

function formatStageHuman(stage: string): string {
  const map: Record<string, string> = {
    queued: "Na fila",
    planning: "Planejando",
    download_extract: "Baixando arquivos da CVM",
    process_data: "Processando dados",
    persist_reports: "Gravando no banco local",
    finalizing: "Finalizando",
  };
  return map[stage] ?? formatStage(stage);
}

function formatDateTime(value: string | null): string {
  if (!value) return "No timestamp";
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

function jobBadgeClass(state: string | null | undefined): string {
  const base = "rounded-full border px-2 py-0.5 text-xs capitalize";
  if (state === "success") return `${base} border-emerald-500/30 text-emerald-200`;
  if (state === "error") return `${base} border-rose-500/30 text-rose-200`;
  if (state === "running" || state === "queued")
    return `${base} border-amber-500/30 text-amber-200`;
  return `${base} border-zinc-700 text-zinc-400`;
}
