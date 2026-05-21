import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelRefresh,
  defaultRefreshWindow,
  fetchBaseHealth,
  fetchRefreshJob,
  fetchRefreshJobs,
  isActiveRefreshJob,
  isTerminalRefreshJob,
  REFRESH_MODES,
  refreshProgress,
  startBaseRefresh,
  type StartRefreshParams,
} from "@/lib/api/updateBase";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { BaseHealthSnapshot, RefreshJobStatus, RefreshMode } from "@/lib/bridge/types";

const ACTIVE_POLL_MS = 2_000;
const IDLE_POLL_MS = 10_000;
const MAX_SAFE_LIMIT = 100;

export function UpdateBasePage() {
  const queryClient = useQueryClient();
  const defaults = useMemo(() => defaultRefreshWindow(), []);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [mode, setMode] = useState<RefreshMode>("missing");
  const [limit, setLimit] = useState(1);
  const [startYear, setStartYear] = useState(defaults.startYear);
  const [endYear, setEndYear] = useState(defaults.endYear);
  const [companyCode, setCompanyCode] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

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
  const trackedJobId = selectedJobId ?? activeJobFromList?.job_id ?? latestJob?.job_id ?? null;

  const jobQuery = useQuery({
    queryKey: ["refresh-job", trackedJobId],
    queryFn: () => fetchRefreshJob(trackedJobId ?? ""),
    enabled: bridgeReady && Boolean(trackedJobId),
    refetchInterval: (query) => {
      const job = query.state.data?.mode === "desktop" ? query.state.data.job : null;
      return isActiveRefreshJob(job) ? ACTIVE_POLL_MS : false;
    },
  });

  const trackedJob = jobQuery.data?.mode === "desktop" ? jobQuery.data.job : activeJobFromList ?? latestJob;
  const isRunning = isActiveRefreshJob(trackedJob) || isActiveRefreshJob(activeJobFromList);

  const healthQuery = useQuery({
    queryKey: ["base-health", startYear, endYear],
    queryFn: () => fetchBaseHealth({ startYear, endYear, forceRefresh: true }),
    enabled: bridgeReady,
    refetchInterval: isRunning ? 5_000 : false,
  });

  useEffect(() => {
    if (isTerminalRefreshJob(trackedJob)) {
      void queryClient.invalidateQueries({ queryKey: ["base-health"] });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    }
  }, [queryClient, trackedJob?.job_id, trackedJob?.state]);

  const startMutation = useMutation({
    mutationFn: (params: StartRefreshParams) => startBaseRefresh(params),
    onSuccess: (result) => {
      if (result.job_id) {
        setSelectedJobId(result.job_id);
      }
      void queryClient.invalidateQueries({ queryKey: ["refresh-jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["base-health"] });
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => cancelRefresh(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["refresh-jobs"] });
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
        : null;
  const emptyDatabase = isEmptyDatabase(health);
  const parsedCompanyCode = parseOptionalCompanyCode(companyCode);
  const companyCodeInvalid = companyCode.trim() !== "" && parsedCompanyCode == null;
  const actionDisabled = !bridgeReady || isRunning || startMutation.isPending || companyCodeInvalid;

  function handleStart() {
    startMutation.mutate({
      mode,
      limit,
      startYear,
      endYear,
      cdCvm: parsedCompanyCode,
    });
  }

  return (
    <section className="space-y-6">
      <PageHeader bridgeReady={bridgeReady} />

      {browserReason ? <BrowserModeBanner reason={browserReason} /> : null}

      <StatusGrid
        health={health}
        healthLoading={!bridgeReady || healthQuery.isLoading}
        healthError={healthQuery.error}
        activeJob={trackedJob}
        jobsLoading={jobsQuery.isLoading}
      />

      {emptyDatabase ? <EmptyDatabaseNotice /> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <RefreshControlPanel
          mode={mode}
          limit={limit}
          startYear={startYear}
          endYear={endYear}
          companyCode={companyCode}
          companyCodeInvalid={companyCodeInvalid}
          disabled={actionDisabled}
          running={isRunning}
          pending={startMutation.isPending}
          startError={startMutation.error}
          onMode={setMode}
          onLimit={setLimit}
          onStartYear={setStartYear}
          onEndYear={setEndYear}
          onCompanyCode={setCompanyCode}
          onStart={handleStart}
        />

        <LocalDataPanel />
      </div>

      <JobPanel
        job={trackedJob}
        jobs={jobs}
        selectedJobId={trackedJobId}
        loading={jobsQuery.isLoading || jobQuery.isLoading}
        error={jobsQuery.error ?? jobQuery.error ?? cancelMutation.error}
        cancelling={cancelMutation.isPending}
        onSelectJob={setSelectedJobId}
        onCancel={(jobId) => cancelMutation.mutate(jobId)}
      />
    </section>
  );
}

function PageHeader({ bridgeReady }: { bridgeReady: boolean }) {
  return (
    <header className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-widest text-zinc-500">
            Local database maintenance
          </p>
          <h2 className="text-2xl font-semibold text-zinc-50">Atualizar Base</h2>
          <p className="max-w-2xl text-sm leading-6 text-zinc-400">
            Download and organize CVM filings into the local desktop database. The
            refresh runs in Python through the pywebview bridge and keeps this UI responsive.
          </p>
        </div>
        <span
          className={
            bridgeReady
              ? "rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-200"
              : "rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-200"
          }
        >
          {bridgeReady ? "Bridge ready" : "Connecting bridge"}
        </span>
      </div>
    </header>
  );
}

function StatusGrid({
  health,
  healthLoading,
  healthError,
  activeJob,
  jobsLoading,
}: {
  health: BaseHealthSnapshot | null;
  healthLoading: boolean;
  healthError: unknown;
  activeJob: RefreshJobStatus | null;
  jobsLoading: boolean;
}) {
  const progress = refreshProgress(activeJob);
  const jobState = activeJob?.state ?? (jobsLoading ? "loading" : "idle");
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard
        label="Database health"
        value={healthLoading ? "Loading" : healthError ? "Error" : health?.health_status || "Unknown"}
        detail={health ? `${formatPct(health.pct)} coverage in ${health.start_year}-${health.end_year}` : "Local SQLite"}
        tone={healthError ? "bad" : health && health.pct > 0 ? "good" : "warn"}
      />
      <MetricCard
        label="Companies"
        value={health ? formatInt(health.total_companies) : "0"}
        detail={
          health
            ? `${formatInt(health.companies_with_historical_data)} with history`
            : "Catalog not loaded"
        }
      />
      <MetricCard
        label="Coverage cells"
        value={health ? formatInt(health.completed_cells) : "0"}
        detail={health ? `${formatInt(health.missing_cells)} missing` : "No snapshot"}
      />
      <MetricCard
        label="Current job"
        value={formatJobState(jobState)}
        detail={
          activeJob
            ? `${formatInt(activeJob.processed)} / ${formatInt(activeJob.queued)} processed (${progress}%)`
            : "No active refresh"
        }
        tone={activeJob?.state === "error" ? "bad" : isActiveRefreshJob(activeJob) ? "warn" : "neutral"}
      />
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-200"
        : tone === "bad"
          ? "text-rose-300"
          : "text-zinc-100";
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 shadow-lg">
      <p className="text-xs uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`mt-2 text-xl font-semibold ${toneClass}`}>{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{detail}</p>
    </article>
  );
}

function EmptyDatabaseNotice() {
  return (
    <article className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
      <p className="font-medium">Your local database has no financial reports yet.</p>
      <p className="mt-1 text-amber-100/80">
        Run Update Base to download and organize available CVM data. The first run can start
        with a small limit and may take several minutes depending on network and CVM file size.
      </p>
    </article>
  );
}

function RefreshControlPanel({
  mode,
  limit,
  startYear,
  endYear,
  companyCode,
  companyCodeInvalid,
  disabled,
  running,
  pending,
  startError,
  onMode,
  onLimit,
  onStartYear,
  onEndYear,
  onCompanyCode,
  onStart,
}: {
  mode: RefreshMode;
  limit: number;
  startYear: number;
  endYear: number;
  companyCode: string;
  companyCodeInvalid: boolean;
  disabled: boolean;
  running: boolean;
  pending: boolean;
  startError: unknown;
  onMode: (mode: RefreshMode) => void;
  onLimit: (limit: number) => void;
  onStartYear: (year: number) => void;
  onEndYear: (year: number) => void;
  onCompanyCode: (value: string) => void;
  onStart: () => void;
}) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <header className="mb-4">
        <h3 className="text-lg font-semibold text-zinc-100">Refresh scope</h3>
        <p className="mt-1 text-xs text-zinc-500">
          Default is a constrained missing-data refresh so first-run validation stays controllable.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2">
        {REFRESH_MODES.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onMode(option.value)}
            className={
              mode === option.value
                ? "rounded-md border border-cyan-500/50 bg-cyan-500/10 p-3 text-left"
                : "rounded-md border border-zinc-800 bg-zinc-950/50 p-3 text-left hover:border-zinc-600"
            }
          >
            <span className="block text-sm font-medium text-zinc-100">{option.label}</span>
            <span className="mt-1 block text-xs leading-5 text-zinc-500">
              {option.description}
            </span>
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <NumberField
          label="Start year"
          value={startYear}
          min={2010}
          max={endYear}
          onChange={onStartYear}
        />
        <NumberField
          label="End year"
          value={endYear}
          min={startYear}
          max={new Date().getFullYear()}
          onChange={onEndYear}
        />
        <NumberField
          label="Company limit"
          value={limit}
          min={1}
          max={MAX_SAFE_LIMIT}
          onChange={onLimit}
        />
        <OptionalCvmField
          value={companyCode}
          invalid={companyCodeInvalid}
          onChange={onCompanyCode}
        />
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={disabled}
          onClick={onStart}
          className="rounded-md border border-emerald-500/50 bg-emerald-500/15 px-4 py-2 text-sm font-medium text-emerald-100 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-600"
        >
          {pending ? "Starting..." : running ? "Refresh running" : "Atualizar base"}
        </button>
        <p className="text-xs text-zinc-500">
          One refresh job can run at a time. Status updates poll every 2 seconds while active.
        </p>
      </div>

      {startError ? (
        <p role="alert" className="mt-4 rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
          {startError instanceof Error ? startError.message : String(startError)}
        </p>
      ) : null}
      {companyCodeInvalid ? (
        <p role="alert" className="mt-4 rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
          Use a positive numeric CVM code or leave the field blank.
        </p>
      ) : null}
    </article>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs uppercase tracking-wider text-zinc-500">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(event) => {
          const next = Number.parseInt(event.target.value, 10);
          if (Number.isFinite(next)) {
            onChange(Math.max(min, Math.min(max, next)));
          }
        }}
        className="h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 font-mono text-sm text-zinc-100 outline-none focus:border-cyan-700"
      />
    </label>
  );
}

function OptionalCvmField({
  value,
  invalid,
  onChange,
}: {
  value: string;
  invalid: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs uppercase tracking-wider text-zinc-500">CVM code</span>
      <input
        type="text"
        inputMode="numeric"
        value={value}
        placeholder="9512"
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value.replace(/\D/g, "").slice(0, 8))}
        className={
          invalid
            ? "h-10 w-full rounded-md border border-rose-800 bg-zinc-950 px-3 font-mono text-sm text-zinc-100 outline-none focus:border-rose-600"
            : "h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 font-mono text-sm text-zinc-100 outline-none focus:border-cyan-700"
        }
      />
      <span className="block text-xs leading-5 text-zinc-500">
        Optional. Leave blank for catalog order; fill it for a targeted company refresh.
      </span>
    </label>
  );
}

function LocalDataPanel() {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <h3 className="text-lg font-semibold text-zinc-100">Local storage</h3>
      <dl className="mt-4 space-y-3 text-sm">
        <div>
          <dt className="text-xs uppercase tracking-wider text-zinc-500">Runtime root</dt>
          <dd className="mt-1 font-mono text-xs text-zinc-200">%LOCALAPPDATA%\CVMAnalytics</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-zinc-500">Database</dt>
          <dd className="mt-1 font-mono text-xs text-zinc-200">
            %LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-zinc-500">Output reports</dt>
          <dd className="mt-1 font-mono text-xs text-zinc-200">%LOCALAPPDATA%\CVMAnalytics\output</dd>
        </div>
      </dl>
      <p className="mt-4 text-xs leading-5 text-zinc-500">
        Refresh data stays on this machine. The app downloads public CVM filings and writes local
        SQLite data and generated reports under the desktop user-data folder.
      </p>
    </article>
  );
}

function JobPanel({
  job,
  jobs,
  selectedJobId,
  loading,
  error,
  cancelling,
  onSelectJob,
  onCancel,
}: {
  job: RefreshJobStatus | null;
  jobs: RefreshJobStatus[];
  selectedJobId: string | null;
  loading: boolean;
  error: unknown;
  cancelling: boolean;
  onSelectJob: (jobId: string | null) => void;
  onCancel: (jobId: string) => void;
}) {
  const progress = refreshProgress(job);
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 shadow-lg">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-800 p-5">
        <div>
          <h3 className="text-lg font-semibold text-zinc-100">Refresh job status</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Persisted job history is stored in the local user-data folder.
          </p>
        </div>
        {job && isActiveRefreshJob(job) ? (
          <button
            type="button"
            disabled={cancelling}
            onClick={() => onCancel(job.job_id)}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 hover:border-rose-700 hover:text-rose-200 disabled:opacity-50"
          >
            {cancelling ? "Cancelling..." : "Cancel"}
          </button>
        ) : null}
      </header>

      <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-4">
          {loading && !job ? (
            <p className="text-sm text-zinc-500">Loading refresh status...</p>
          ) : job ? (
            <CurrentJob job={job} progress={progress} />
          ) : (
            <p className="rounded border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
              No refresh job has been started in this runtime yet.
            </p>
          )}

          {error ? (
            <p role="alert" className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
              {error instanceof Error ? error.message : String(error)}
            </p>
          ) : null}

          <LogPanel job={job} />
        </div>

        <JobHistory jobs={jobs} selectedJobId={selectedJobId} onSelectJob={onSelectJob} />
      </div>
    </article>
  );
}

function CurrentJob({ job, progress }: { job: RefreshJobStatus; progress: number }) {
  return (
    <div className="space-y-4 rounded border border-zinc-800 bg-zinc-950/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-zinc-500">{shortJobId(job.job_id)}</p>
          <h4 className="mt-1 text-base font-semibold text-zinc-100">
            {formatJobState(job.state)}
          </h4>
        </div>
        <span className={jobBadgeClass(job.state)}>{job.mode ?? "refresh"}</span>
      </div>

      <div>
        <div className="mb-2 flex justify-between text-xs text-zinc-500">
          <span>{job.stage ? formatStage(job.stage) : "Waiting for stage"}</span>
          <span>{progress}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
          <div
            className="h-full rounded-full bg-cyan-400 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <dl className="grid gap-3 text-sm sm:grid-cols-4">
        <Field label="Queued" value={formatInt(job.queued)} />
        <Field label="Processed" value={formatInt(job.processed)} />
        <Field label="Failures" value={formatInt(job.failures)} />
        <Field label="Elapsed" value={formatElapsed(job)} />
      </dl>

      {job.error ? (
        <p className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
          {job.error}
        </p>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-zinc-100">{value}</dd>
    </div>
  );
}

function LogPanel({ job }: { job: RefreshJobStatus | null }) {
  const lines = (job?.log_lines ?? []).slice(-12).reverse();
  return (
    <section className="rounded border border-zinc-800 bg-zinc-950/50">
      <header className="border-b border-zinc-800 px-4 py-3">
        <h4 className="text-sm font-medium text-zinc-100">Recent log</h4>
      </header>
      <div className="max-h-72 overflow-auto p-4">
        {lines.length ? (
          <ol className="space-y-2">
            {lines.map((line, index) => (
              <li key={`${line}-${index}`} className="font-mono text-xs leading-5 text-zinc-400">
                {line}
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-zinc-500">No log lines yet.</p>
        )}
      </div>
    </section>
  );
}

function JobHistory({
  jobs,
  selectedJobId,
  onSelectJob,
}: {
  jobs: RefreshJobStatus[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string | null) => void;
}) {
  return (
    <aside className="rounded border border-zinc-800 bg-zinc-950/50">
      <header className="border-b border-zinc-800 px-4 py-3">
        <h4 className="text-sm font-medium text-zinc-100">History</h4>
      </header>
      <div className="max-h-96 overflow-auto">
        {jobs.length ? (
          <div className="divide-y divide-zinc-800">
            {jobs.slice(0, 8).map((item) => (
              <button
                type="button"
                key={item.job_id}
                onClick={() => onSelectJob(item.job_id)}
                className={
                  item.job_id === selectedJobId
                    ? "block w-full bg-cyan-500/10 px-4 py-3 text-left"
                    : "block w-full px-4 py-3 text-left hover:bg-zinc-900"
                }
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-zinc-400">{shortJobId(item.job_id)}</span>
                  <span className={jobBadgeClass(item.state)}>{formatJobState(item.state)}</span>
                </span>
                <span className="mt-2 block text-xs text-zinc-500">
                  {formatDateTime(item.updated_at ?? item.started_at ?? item.accepted_at ?? null)}
                </span>
                <span className="mt-1 block text-xs text-zinc-500">
                  {formatInt(item.processed)} / {formatInt(item.queued)} processed
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="p-4 text-sm text-zinc-500">No persisted jobs.</p>
        )}
      </div>
    </aside>
  );
}

function BrowserModeBanner({ reason }: { reason: string }) {
  return (
    <article className="rounded-lg border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-100">
      <p className="font-medium">Browser-mode preview</p>
      <p className="mt-1 text-amber-100/80">{reason}</p>
    </article>
  );
}

function isEmptyDatabase(health: BaseHealthSnapshot | null): boolean {
  if (!health) return false;
  return (
    health.total_companies > 0 &&
    health.companies_with_any_local_financial_report === 0 &&
    health.completed_cells === 0
  );
}

function parseOptionalCompanyCode(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function formatInt(value: number | null | undefined): string {
  return new Intl.NumberFormat("pt-BR").format(Number(value ?? 0));
}

function formatPct(value: number | null | undefined): string {
  return `${Number(value ?? 0).toLocaleString("pt-BR", {
    maximumFractionDigits: 1,
  })}%`;
}

function formatJobState(value: string | null | undefined): string {
  const normalized = String(value ?? "unknown");
  if (normalized === "already_current") return "Already current";
  return normalized.replace(/_/g, " ");
}

function formatStage(value: string): string {
  return value.replace(/_/g, " ");
}

function shortJobId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}...` : value;
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

function formatElapsed(job: RefreshJobStatus): string {
  const start = new Date(job.started_at ?? job.accepted_at ?? "").getTime();
  const end = job.finished_at ? new Date(job.finished_at).getTime() : Date.now();
  if (!Number.isFinite(start) || Number.isNaN(start)) return "n/d";
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function jobBadgeClass(state: string | null | undefined): string {
  const base = "rounded-full border px-2 py-0.5 text-xs capitalize";
  if (state === "success") return `${base} border-emerald-500/30 text-emerald-200`;
  if (state === "error") return `${base} border-rose-500/30 text-rose-200`;
  if (state === "running" || state === "queued") return `${base} border-amber-500/30 text-amber-200`;
  return `${base} border-zinc-700 text-zinc-400`;
}
