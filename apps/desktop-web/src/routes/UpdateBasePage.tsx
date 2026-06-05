import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { useRefreshJobInvalidation } from "@/hooks/useRefreshJobInvalidation";
import { fetchDataCoverage } from "@/lib/api/dataCoverage";
import {
  BATCH_SIZE_OPTIONS,
  CVM_MIN_YEAR,
  DataUpdateBlockedError,
  defaultRefreshWindow,
  fetchBaseHealth,
  fetchCompanyUniverseSelection,
  fetchDatabaseDiagnostics,
  fetchDataUpdateSettings,
  fetchRefreshJob,
  fetchRefreshJobs,
  isActiveRefreshJob,
  isTerminalRefreshJob,
  refreshProgress,
  resetLocalDatabase,
  saveDataUpdateSettings,
  startDataUpdate,
} from "@/lib/api/updateBase";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type {
  BaseHealthSnapshot,
  CompanyUniversePreset,
  CompanyUniverseSelection,
  DatabaseDiagnostics,
  DataCoverageResponse,
  DataUpdateSettings,
  RefreshJobStatus,
  ResetLocalDatabaseResponse,
} from "@/lib/bridge/types";

const ACTIVE_POLL_MS = 2_000;
const IDLE_POLL_MS = 10_000;
const DIAG_ACTIVE_POLL_MS = 3_000;
const DIAG_IDLE_POLL_MS = 30_000;

const PRESET_LABEL: Record<CompanyUniversePreset, string> = {
  top_100: "Top 100",
  top_200: "Top 200",
  top_500: "Top 500",
  all: "All available companies",
};

const RESET_CONFIRMATION = {
  restart_current: "RESET",
  recreate_local: "REBUILD",
} as const;

type ResetAction = keyof typeof RESET_CONFIRMATION;

const CURRENT_YEAR = new Date().getFullYear();

const YEAR_PRESETS: Array<{ label: string; start: number; end: number }> = [
  { label: "Last 3 years", start: CURRENT_YEAR - 2, end: CURRENT_YEAR },
  { label: "Last 5 years", start: CURRENT_YEAR - 4, end: CURRENT_YEAR },
  { label: "Last 10 years", start: CURRENT_YEAR - 9, end: CURRENT_YEAR },
  { label: "Full History", start: CVM_MIN_YEAR, end: CURRENT_YEAR },
];

const FALLBACK_SETTINGS: DataUpdateSettings = {
  universe_preset: "top_200",
  batch_size: 100,
  retry_failed: true,
  recompute_coverage: true,
  start_year: CURRENT_YEAR - 4,
  end_year: CURRENT_YEAR,
};

function yearRangeError(start: number, end: number): string | null {
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "Invalid years.";
  if (start < CVM_MIN_YEAR) return `Minimum start year: ${CVM_MIN_YEAR}.`;
  if (end > CURRENT_YEAR) return `Maximum end year: ${CURRENT_YEAR}.`;
  if (start > end) return "Start year must be less than or equal to end year.";
  return null;
}

export function UpdateBasePage() {
  const queryClient = useQueryClient();
  const invalidateRefreshQueries = useRefreshJobInvalidation();
  const defaults = useMemo(() => defaultRefreshWindow(), []);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [bridgeMode, setBridgeMode] = useState<"desktop" | "browser" | "mock" | null>(null);
  const [draftSettings, setDraftSettings] =
    useState<DataUpdateSettings>(FALLBACK_SETTINGS);
  const [settingsTouched, setSettingsTouched] = useState(false);
  const [lastStartedJobId, setLastStartedJobId] = useState<string | null>(null);
  const [autoRetryParentJobId, setAutoRetryParentJobId] = useState<string | null>(null);
  const [resetAction, setResetAction] = useState<ResetAction | null>(null);
  const [resetConfirmation, setResetConfirmation] = useState("");

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then((mode) => {
      if (!cancelled) {
        setBridgeMode(mode);
        setBridgeReady(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const settingsQuery = useQuery({
    queryKey: ["data-update-settings"],
    queryFn: fetchDataUpdateSettings,
    enabled: bridgeReady,
    staleTime: 15_000,
  });

  useEffect(() => {
    const settings =
      settingsQuery.data?.mode === "desktop" ? settingsQuery.data.settings : null;
    if (!settings || settingsTouched) return;
    setDraftSettings(settings);
  }, [settingsQuery.data, settingsTouched]);

  const universeQuery = useQuery({
    queryKey: ["company-universe-selection", draftSettings.universe_preset],
    queryFn: () => fetchCompanyUniverseSelection(draftSettings.universe_preset),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

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
        forceRefresh: false,
      }),
    enabled: bridgeReady,
    refetchInterval: isRunning ? 5_000 : false,
  });

  const diagnosticsQuery = useQuery({
    queryKey: ["db-diagnostics"],
    queryFn: () => fetchDatabaseDiagnostics(),
    enabled: bridgeReady,
    refetchInterval: isRunning ? DIAG_ACTIVE_POLL_MS : DIAG_IDLE_POLL_MS,
  });

  const coverageQuery = useQuery({
    queryKey: ["data-coverage"],
    queryFn: fetchDataCoverage,
    enabled: bridgeReady,
    staleTime: 30_000,
    refetchInterval: isRunning ? 8_000 : false,
  });

  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.snapshot : null;
  const diagnostics =
    diagnosticsQuery.data?.mode === "desktop" ? diagnosticsQuery.data.diagnostics : null;
  const coverage = coverageQuery.data?.mode === "desktop" ? coverageQuery.data.data : null;
  const selection =
    universeQuery.data?.mode === "desktop" ? universeQuery.data.selection : null;
  const browserReason =
    settingsQuery.data?.mode === "browser"
      ? settingsQuery.data.reason
      : healthQuery.data?.mode === "browser"
        ? healthQuery.data.reason
        : jobsQuery.data?.mode === "browser"
          ? jobsQuery.data.reason
          : coverageQuery.data?.mode === "browser"
            ? coverageQuery.data.reason
            : null;

  const invalidatedJobRef = useRef<string | null>(null);
  useEffect(() => {
    if (!trackedJob) return;
    if (
      isTerminalRefreshJob(trackedJob) &&
      invalidatedJobRef.current !== trackedJob.job_id
    ) {
      invalidatedJobRef.current = trackedJob.job_id;
      invalidateRefreshQueries();
      if (draftSettings.recompute_coverage) {
        void queryClient.invalidateQueries({ queryKey: ["data-coverage"] });
      }
    }
  }, [draftSettings.recompute_coverage, invalidateRefreshQueries, queryClient, trackedJob]);

  const yearError = yearRangeError(draftSettings.start_year, draftSettings.end_year);

  const startMutation = useMutation({
    mutationFn: () =>
      startDataUpdate({
        mode: "missing",
        universePreset: draftSettings.universe_preset,
        batchSize: draftSettings.batch_size,
        retryFailed: draftSettings.retry_failed,
        recomputeCoverage: draftSettings.recompute_coverage,
        startYear: draftSettings.start_year,
        endYear: draftSettings.end_year,
      }),
    onSuccess: (result) => {
      if (result.job_id) setLastStartedJobId(result.job_id);
      setAutoRetryParentJobId(null);
      invalidateRefreshQueries();
    },
  });

  const retryMutation = useMutation({
    mutationFn: () =>
      startDataUpdate({
        mode: "failed",
        universePreset: draftSettings.universe_preset,
        batchSize: draftSettings.batch_size,
        retryFailed: false,
        recomputeCoverage: draftSettings.recompute_coverage,
        startYear: draftSettings.start_year,
        endYear: draftSettings.end_year,
      }),
    onSuccess: (result) => {
      if (result.job_id) setLastStartedJobId(result.job_id);
      invalidateRefreshQueries();
    },
  });

  useEffect(() => {
    if (!trackedJob || !lastStartedJobId) return;
    if (trackedJob.job_id !== lastStartedJobId) return;
    if (!draftSettings.retry_failed || retryMutation.isPending) return;
    if (!isTerminalRefreshJob(trackedJob) || trackedJob.mode === "failed") return;
    if (autoRetryParentJobId === trackedJob.job_id) return;
    if (Number(trackedJob.failures || 0) <= 0) return;
    setAutoRetryParentJobId(trackedJob.job_id);
    retryMutation.mutate();
  }, [
    autoRetryParentJobId,
    draftSettings.retry_failed,
    lastStartedJobId,
    retryMutation,
    trackedJob,
  ]);

  const saveSettingsMutation = useMutation({
    mutationFn: () => saveDataUpdateSettings(draftSettings),
    onSuccess: (settings) => {
      setDraftSettings(settings);
      setSettingsTouched(false);
      void queryClient.invalidateQueries({ queryKey: ["data-update-settings"] });
      void queryClient.invalidateQueries({ queryKey: ["company-universe-selection"] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: (args: { action: ResetAction; confirm: string }) =>
      resetLocalDatabase(args),
    onSuccess: (result, variables) => {
      setResetAction(null);
      setResetConfirmation("");
      void queryClient.invalidateQueries();
      if (variables.action === "recreate_local") {
        startMutation.mutate();
      } else {
        void settingsQuery.refetch();
      }
      return result;
    },
  });

  const loading = !bridgeReady || settingsQuery.isLoading;
  const desktopMode = bridgeMode === "desktop";
  const updateDisabled =
    !desktopMode || loading || isRunning || startMutation.isPending || retryMutation.isPending || Boolean(yearError);

  return (
    <section className="space-y-5">
      <PageHeader
        title="Database Updates"
        subtitle="Manage updates, rebuilds, and coverage for your local database."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <LinkButton to="/data-coverage">View Data Coverage</LinkButton>
            <StatusPill tone={desktopMode ? "good" : "warn"}>
              {desktopMode ? "Bridge ready" : bridgeReady ? "Browser mode" : "Connecting"}
            </StatusPill>
          </div>
        }
      />

      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}
      {loading ? <StateBanner variant="loading" title="Loading database operation…" /> : null}

      <SummaryGrid
        health={health}
        diagnostics={diagnostics}
        coverage={coverage}
        selection={selection}
        settings={draftSettings}
        activeJob={isRunning ? trackedJob : null}
      />

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]">
        <div className="space-y-5">
          <UpdatePanel
            settings={draftSettings}
            selection={selection}
            activeJob={isRunning ? trackedJob : null}
            latestJob={!isRunning ? trackedJob : latestJob}
            updateDisabled={updateDisabled}
            starting={startMutation.isPending}
            retrying={retryMutation.isPending}
            error={startMutation.error ?? retryMutation.error}
            yearError={yearError}
            onUpdate={() => startMutation.mutate()}
          />
          <ManagementPanel
            diagnostics={diagnostics}
            resetResult={resetMutation.data ?? null}
            resetError={resetMutation.error}
            resetting={resetMutation.isPending}
            canManage={desktopMode}
            onChooseReset={(action) => {
              setResetAction(action);
              setResetConfirmation("");
            }}
          />
          <AdvancedDiagnostics
            diagnostics={diagnostics}
            jobs={jobs}
          />
        </div>

        <SettingsPanel
          settings={draftSettings}
          saving={saveSettingsMutation.isPending}
          canSave={desktopMode}
          saveError={saveSettingsMutation.error}
          saved={!settingsTouched && saveSettingsMutation.isSuccess}
          onChange={(next) => {
            startMutation.reset();
            retryMutation.reset();
            setAutoRetryParentJobId(null);
            setSettingsTouched(true);
            setDraftSettings(next);
          }}
          onSave={() => saveSettingsMutation.mutate()}
        />
      </section>

      {resetAction ? (
        <ResetConfirmation
          action={resetAction}
          value={resetConfirmation}
          running={resetMutation.isPending}
          settings={draftSettings}
          onChange={setResetConfirmation}
          onCancel={() => {
            setResetAction(null);
            setResetConfirmation("");
          }}
          onConfirm={() =>
            resetMutation.mutate({
              action: resetAction,
              confirm: resetConfirmation,
            })
          }
        />
      ) : null}
    </section>
  );
}

function SummaryGrid({
  health,
  diagnostics,
  coverage,
  selection,
  settings,
  activeJob,
}: {
  health: BaseHealthSnapshot | null;
  diagnostics: DatabaseDiagnostics | null;
  coverage: DataCoverageResponse | null;
  selection: CompanyUniverseSelection | null;
  settings: DataUpdateSettings;
  activeJob: RefreshJobStatus | null | undefined;
}) {
  const pending = coverage
    ? coverage.filter_counts.all ?? (
        coverage.summary.partial +
        coverage.summary.no_financial +
        coverage.summary.failed +
        coverage.summary.unmapped
      )
    : health?.missing_cells ?? null;
  const failed = coverage?.summary.failed ?? diagnostics?.refresh_errors_count ?? null;

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
      <MetricCard
        label="Status"
        value={activeJob ? "Update in progress" : statusLabel(health)}
        detail={health ? `${fmtPct(health.pct)} annual coverage` : "Checking database"}
        tone={activeJob ? "warn" : statusTone(health)}
      />
      <MetricCard
        label="Company Universe"
        value={PRESET_LABEL[settings.universe_preset]}
        detail={`${fmtInt(selection?.selected_count ?? 0)} companies selected`}
      />
      <MetricCard
        label="Complete Companies"
        value={fmtInt(coverage?.summary.complete ?? health?.companies_fully_updated ?? 0)}
        detail="with usable data"
        tone="good"
      />
      <MetricCard
        label="Pending Issues"
        value={pending == null ? "—" : fmtInt(pending)}
        detail="missing, partial, or stale"
        tone={pending ? "warn" : "good"}
      />
      <MetricCard
        label="Failures"
        value={failed == null ? "—" : fmtInt(failed)}
        detail="last update"
        tone={failed ? "bad" : "good"}
      />
      <MetricCard
        label="Last Update"
        value={formatDateTimeShort(diagnostics?.latest_success_at ?? null)}
        detail={diagnostics?.latest_attempt_at ? `attempt ${formatDateTimeShort(diagnostics.latest_attempt_at)}` : "no attempt recorded"}
      />
    </div>
  );
}

function UpdatePanel({
  settings,
  selection,
  activeJob,
  latestJob,
  updateDisabled,
  starting,
  retrying,
  error,
  yearError,
  onUpdate,
}: {
  settings: DataUpdateSettings;
  selection: CompanyUniverseSelection | null;
  activeJob: RefreshJobStatus | null | undefined;
  latestJob: RefreshJobStatus | null | undefined;
  updateDisabled: boolean;
  starting: boolean;
  retrying: boolean;
  error: unknown;
  yearError: string | null;
  onUpdate: () => void;
}) {
  const queued = activeJob?.queued ?? 0;
  const processed = activeJob?.processed ?? 0;
  const progress = activeJob ? refreshProgress(activeJob) : 0;
  const phase = activeJob?.stage ? formatStageHuman(activeJob.stage) : "Waiting";
  const latestMessage = activeJob?.log_lines?.at(-1) ?? null;

  return (
    <Card
      title="Update"
      eyebrow="Main flow"
      actions={
        <button
          type="button"
          disabled={updateDisabled}
          onClick={onUpdate}
          className="rounded-md border border-emerald-500/50 bg-emerald-500/15 px-4 py-2 text-sm font-semibold text-emerald-100 hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-600"
        >
          {starting ? "Starting…" : activeJob ? "Updating…" : "Update Database"}
        </button>
      }
    >
      <p className="text-sm leading-6 text-zinc-300">
        Updates up to <strong className="text-zinc-100">{fmtInt(settings.batch_size)}</strong>{" "}
        pending companies from the{" "}
        <strong className="text-zinc-100">{PRESET_LABEL[settings.universe_preset]}</strong>{" "}
        universe · period{" "}
        <strong className="text-zinc-100">{settings.start_year}–{settings.end_year}</strong>.
        The batch size limits how many companies are processed per run to keep the app responsive.
      </p>
      <p className="mt-2 text-xs text-zinc-500">
        The backend processes the batch in a sequential job. Parallel concurrency is not
        exposed because there is no safe control in the UI yet.
      </p>

      <p className="mt-3 text-xs text-zinc-400 border-t border-zinc-800/50 pt-2 leading-relaxed">
        Market-cap data is fetched from Yahoo Finance, an unofficial free data source. CVMAnalytics stores a local snapshot for auditability. Values may differ from official B3 data.
      </p>

      {selection?.warning ? (
        <InlineNotice tone="warning">{selection.warning}</InlineNotice>
      ) : null}

      {yearError ? (
        <InlineNotice tone="error">{yearError}</InlineNotice>
      ) : null}

      {activeJob ? (
        <div className="mt-5 rounded border border-cyan-500/20 bg-cyan-500/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-cyan-100">{phase}</p>
              <p className="mt-1 text-xs text-zinc-400">
                {fmtInt(processed)} of {fmtInt(queued)} companies processed
                {activeJob.current_cvm ? ` · CVM ${activeJob.current_cvm}` : ""}
                {" · "}{settings.start_year}–{settings.end_year}
              </p>
            </div>
            <div className="font-mono text-sm text-cyan-100">{progress}%</div>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-sm bg-zinc-800">
            <div
              className="h-full rounded-sm bg-cyan-400 transition-all"
              style={{ width: `${Math.max(4, Math.min(100, progress))}%` }}
            />
          </div>
          <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-3">
            <Field label="Elapsed" value={formatElapsed(activeJob.started_at ?? activeJob.accepted_at ?? null)} />
            <Field label="ETA" value="n/a" />
            <Field label="Failures" value={fmtInt(activeJob.failures)} tone={activeJob.failures ? "bad" : "neutral"} />
          </dl>
          {latestMessage ? (
            <p className="mt-3 truncate font-mono text-xs text-zinc-500">{latestMessage}</p>
          ) : null}
        </div>
      ) : null}

      {/* Suppress the previous run's summary when the latest attempt did not
          start — otherwise a stale "Completed" sits next to the error/blocked
          notice and reads as a contradiction. */}
      {!activeJob && latestJob && !error ? <ResultSummary job={latestJob} /> : null}

      {retrying ? (
        <InlineNotice tone="warning">
          Retrying companies that failed in the previous batch.
        </InlineNotice>
      ) : null}

      {error ? (
        error instanceof DataUpdateBlockedError ? (
          <InlineNotice tone="warning">
            <span className="font-semibold">Configuration needed — no job was started.</span>{" "}
            {error.message}
          </InlineNotice>
        ) : (
          <InlineNotice tone="error">
            {error instanceof Error ? error.message : String(error)}
          </InlineNotice>
        )
      ) : null}
    </Card>
  );
}

function ResultSummary({ job }: { job: RefreshJobStatus }) {
  const result = job.result as Record<string, unknown> | null | undefined;
  const summary = result?.summary as Record<string, unknown> | undefined;
  const planning = result?.planning_stats as Record<string, unknown> | undefined;
  const success = Number(summary?.success_count ?? (job.state === "success" ? job.processed : 0));
  const skipped = Number(planning?.skipped_companies_all_complete ?? 0);
  const failed = Number(summary?.error_count ?? job.failures ?? 0);
  const noData = Number(summary?.no_data_count ?? 0);
  const tone = job.state === "success" && failed === 0 ? "good" : failed > 0 ? "warn" : "neutral";
  const marketCap = result?.market_cap_result as Record<string, any> | undefined;

  return (
    <div className={`mt-5 rounded border p-4 ${resultClass(tone)}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{formatJobState(job.state)}</p>
          <p className="mt-1 text-xs opacity-80">
            Finished at {formatDateTime(job.finished_at ?? job.updated_at ?? null)}
          </p>
        </div>
        {failed > 0 ? <LinkButton to="/data-coverage">View pending issues</LinkButton> : null}
      </div>
      <dl className="mt-4 grid gap-3 sm:grid-cols-4">
        <Field label="Updated" value={fmtInt(success)} />
        <Field label="No new data" value={fmtInt(noData + skipped)} />
        <Field label="Failed" value={fmtInt(failed)} tone={failed ? "bad" : "neutral"} />
        <Field label="Job" value={shortJobId(job.job_id)} mono />
      </dl>
      {marketCap ? (
        <div className="mt-4 border-t border-zinc-800/50 pt-4">
          <p className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Market Cap Snapshot Step</p>
          <div className="grid gap-3 sm:grid-cols-5">
            <Field label="Status" value={marketCap.status || "n/a"} tone={marketCap.status === "success" ? "good" : marketCap.status === "warning" ? "warn" : "bad"} />
            <Field label="Source" value={marketCap.source || "n/a"} />
            <Field label="Provider Status" value={marketCap.provider_status || "n/a"} tone={marketCap.provider_status === "unofficial_free" ? "warn" : "neutral"} />
            <Field label="Rows Count" value={marketCap.row_count != null ? fmtInt(marketCap.row_count) : "n/a"} />
            <Field label="As of Date" value={marketCap.as_of_date || "n/a"} />
          </div>
          {marketCap.warnings && marketCap.warnings.length > 0 ? (
            <div className="mt-2 text-xs text-amber-200 opacity-90">
              <span className="font-semibold">Warnings:</span> {marketCap.warnings.join("; ")}
            </div>
          ) : null}
          {marketCap.error ? (
            <div className="mt-2 text-xs text-rose-300">
              <span className="font-semibold">Error:</span> {marketCap.error}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SettingsPanel({
  settings,
  saving,
  canSave,
  saveError,
  saved,
  onChange,
  onSave,
}: {
  settings: DataUpdateSettings;
  saving: boolean;
  canSave: boolean;
  saveError: unknown;
  saved: boolean;
  onChange: (settings: DataUpdateSettings) => void;
  onSave: () => void;
}) {
  const yearErr = yearRangeError(settings.start_year, settings.end_year);
  const activePreset = YEAR_PRESETS.find(
    (p) => p.start === settings.start_year && p.end === settings.end_year,
  );

  return (
    <Card title="Update Settings" eyebrow="Scope and safety">
      <div className="space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-zinc-500">
            Company Universe
          </span>
          <select
            value={settings.universe_preset}
            onChange={(event) =>
              onChange({
                ...settings,
                universe_preset: event.target.value as CompanyUniversePreset,
              })
            }
            className="mt-2 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-cyan-600 focus:outline-none"
          >
            {Object.entries(PRESET_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-xs uppercase tracking-wider text-zinc-500">
            Companies per Batch
          </span>
          <select
            value={settings.batch_size}
            onChange={(event) =>
              onChange({
                ...settings,
                batch_size: Number(event.target.value) as DataUpdateSettings["batch_size"],
              })
            }
            className="mt-2 w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-cyan-600 focus:outline-none"
          >
            {BATCH_SIZE_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-zinc-500">
            Number of companies processed per batch.
          </span>
        </label>

        <div>
          <span className="text-xs uppercase tracking-wider text-zinc-500">
            Year Range
          </span>
          <p className="mt-1 text-xs text-zinc-500">
            Choose which years will be downloaded or updated in the local database.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {YEAR_PRESETS.map((preset) => {
              const isActive = activePreset?.label === preset.label;
              return (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() =>
                    onChange({ ...settings, start_year: preset.start, end_year: preset.end })
                  }
                  className={`rounded border px-2 py-1 text-xs transition-colors ${
                    isActive
                      ? "border-cyan-600 bg-cyan-600/15 text-cyan-100"
                      : "border-zinc-700 bg-zinc-950/50 text-zinc-300 hover:border-zinc-500"
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs text-zinc-500">Start Year</span>
              <input
                type="number"
                min={CVM_MIN_YEAR}
                max={CURRENT_YEAR}
                value={settings.start_year}
                onChange={(event) =>
                  onChange({ ...settings, start_year: Number(event.target.value) })
                }
                className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100 focus:border-cyan-600 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="text-xs text-zinc-500">End Year</span>
              <input
                type="number"
                min={CVM_MIN_YEAR}
                max={CURRENT_YEAR}
                value={settings.end_year}
                onChange={(event) =>
                  onChange({ ...settings, end_year: Number(event.target.value) })
                }
                className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100 focus:border-cyan-600 focus:outline-none"
              />
            </label>
          </div>
          {yearErr ? (
            <InlineNotice tone="error">{yearErr}</InlineNotice>
          ) : null}
        </div>

        <Toggle
          checked={settings.retry_failed}
          label="Retry companies with errors"
          onChange={(checked) => onChange({ ...settings, retry_failed: checked })}
        />
        <Toggle
          checked={settings.recompute_coverage}
          label="Recompute coverage on completion"
          onChange={(checked) => onChange({ ...settings, recompute_coverage: checked })}
        />

        <div className="rounded border border-zinc-800 bg-zinc-950/50 p-3 text-xs leading-5 text-zinc-500">
          The main flow uses the selected universe and updates only pending companies
          by default. Full refresh and parallel concurrency are outside the main flow
          until there is safe backend control.
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-zinc-800 pt-4">
          <span className="text-xs text-zinc-500">
            {saved ? "Settings saved." : "Changes apply to the next update."}
          </span>
          <button
            type="button"
            disabled={saving || !canSave}
            onClick={onSave}
            className="rounded border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:border-cyan-700 hover:text-cyan-100 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
        {saveError ? (
          <InlineNotice tone="error">
            {saveError instanceof Error ? saveError.message : String(saveError)}
          </InlineNotice>
        ) : null}
      </div>
    </Card>
  );
}

function ManagementPanel({
  diagnostics,
  resetResult,
  resetError,
  resetting,
  canManage,
  onChooseReset,
}: {
  diagnostics: DatabaseDiagnostics | null;
  resetResult: ResetLocalDatabaseResponse | null;
  resetError: unknown;
  resetting: boolean;
  canManage: boolean;
  onChooseReset: (action: ResetAction) => void;
}) {
  return (
    <Card title="Database Management" eyebrow="Protected actions">
      <div className="grid gap-3 md:grid-cols-2">
        <ActionBox
          title="Reset Current Database"
          body="Clears setup state, job history, and update errors. Local financial data is preserved."
          disabled={resetting || !canManage}
          onClick={() => onChooseReset("restart_current")}
        />
        <ActionBox
          title="Rebuild Local Database"
          body="Creates a backup, removes the local SQLite database, and starts a new update with the selected settings."
          danger
          disabled={resetting || !canManage}
          onClick={() => onChooseReset("recreate_local")}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <LinkButton to="/data-coverage">Open Data Coverage</LinkButton>
        <LinkButton to="/status">View diagnostics</LinkButton>
      </div>
      <p className="mt-3 text-xs leading-5 text-zinc-500">
        This action may remove local data and cannot be undone without a backup.
        Current path: <span className="font-mono text-zinc-400">{diagnostics?.db_path ?? "n/a"}</span>
      </p>
      {resetResult ? (
        <InlineNotice tone="success">
          {resetResult.message ?? "Operation completed."}
          {resetResult.backup_path ? ` Backup: ${resetResult.backup_path}` : ""}
        </InlineNotice>
      ) : null}
      {resetError ? (
        <InlineNotice tone="error">
          {resetError instanceof Error ? resetError.message : String(resetError)}
        </InlineNotice>
      ) : null}
    </Card>
  );
}

function AdvancedDiagnostics({
  diagnostics,
  jobs,
}: {
  diagnostics: DatabaseDiagnostics | null;
  jobs: RefreshJobStatus[];
}) {
  return (
    <details className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <summary className="cursor-pointer text-sm font-semibold text-zinc-100">
        Advanced Diagnostics
      </summary>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="rounded border border-zinc-800 bg-zinc-950/50 p-3">
          <h3 className="text-xs uppercase tracking-wider text-zinc-500">Local Database</h3>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <Field label="File" value={diagnostics?.db_path ?? "n/a"} mono />
            <Field label="Size" value={formatBytes(diagnostics?.db_size_bytes)} />
            <Field label="Companies" value={fmtInt(diagnostics?.row_counts.companies ?? 0)} />
            <Field label="Financial rows" value={fmtInt(diagnostics?.row_counts.financial_reports ?? 0)} />
            <Field label="Jobs" value={fmtInt(diagnostics?.row_counts.refresh_jobs ?? 0)} />
            <Field label="QA logs" value={fmtInt(diagnostics?.row_counts.qa_logs ?? 0)} />
          </dl>
          {diagnostics?.latest_error ? (
            <InlineNotice tone="error">{diagnostics.latest_error}</InlineNotice>
          ) : null}
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-950/50 p-3">
          <h3 className="text-xs uppercase tracking-wider text-zinc-500">Recent History</h3>
          {jobs.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">No jobs recorded.</p>
          ) : (
            <ol className="mt-3 divide-y divide-zinc-800">
              {jobs.slice(0, 6).map((job) => (
                <li key={job.job_id} className="grid gap-2 py-2 text-xs sm:grid-cols-[6rem_5rem_minmax(0,1fr)]">
                  <span className={jobBadgeClass(job.state)}>{formatJobState(job.state)}</span>
                  <span className="font-mono text-zinc-500">{fmtInt(job.processed)}/{fmtInt(job.queued)}</span>
                  <span className="truncate text-zinc-400">
                    {formatDateTime(job.updated_at ?? job.finished_at ?? job.accepted_at ?? null)}
                    {job.error ? ` · ${job.error}` : ""}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </details>
  );
}

function ResetConfirmation({
  action,
  value,
  running,
  settings,
  onChange,
  onCancel,
  onConfirm,
}: {
  action: ResetAction;
  value: string;
  running: boolean;
  settings: DataUpdateSettings;
  onChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const expected = RESET_CONFIRMATION[action];
  const destructive = action === "recreate_local";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <section className="w-full max-w-lg rounded-lg border border-zinc-700 bg-zinc-950 p-5 shadow-2xl">
        <p className="text-xs uppercase tracking-wider text-amber-200">
          Confirmation required
        </p>
        <h2 className="mt-2 text-lg font-semibold text-zinc-100">
          {destructive ? "Rebuild Local Database" : "Reset Current Database"}
        </h2>
        <p className="mt-3 text-sm leading-6 text-zinc-300">
          {destructive
            ? `The local SQLite database will be backed up and removed. After that, the update will start with the selected settings: ${PRESET_LABEL[settings.universe_preset]} · ${settings.start_year}–${settings.end_year}.`
            : "Setup state, jobs, and errors will be cleared. Local financial data will be preserved."}
        </p>
        <label className="mt-4 block">
          <span className="text-xs text-zinc-500">
            Type <span className="font-mono text-zinc-100">{expected}</span> to confirm.
          </span>
          <input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            className="mt-2 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-100 focus:border-amber-500 focus:outline-none"
            autoFocus
          />
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            disabled={running}
            onClick={onCancel}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:border-zinc-500 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={running || value !== expected}
            onClick={onConfirm}
            className="rounded border border-rose-500/60 bg-rose-500/15 px-3 py-1.5 text-sm font-semibold text-rose-100 hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-600"
          >
            {running ? "Running…" : "Confirm"}
          </button>
        </div>
      </section>
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
  tone?: Tone;
}) {
  return (
    <article className={`rounded-lg border bg-zinc-900/60 p-4 shadow-lg ${borderClass(tone)}`}>
      <p className="text-xs uppercase tracking-wider text-zinc-500">{label}</p>
      <p className={`mt-2 min-h-10 text-sm font-semibold leading-5 ${toneText(tone)}`}>{value}</p>
      <p className="mt-1 text-xs leading-5 text-zinc-500">{detail}</p>
    </article>
  );
}

function Card({
  title,
  eyebrow,
  actions,
  children,
}: {
  title: string;
  eyebrow: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500">{eyebrow}</p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-100">{title}</h2>
        </div>
        {actions}
      </header>
      {children}
    </article>
  );
}

function Toggle({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-950/50 p-3">
      <span className="text-sm text-zinc-200">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-cyan-500"
      />
    </label>
  );
}

function ActionBox({
  title,
  body,
  danger,
  disabled,
  onClick,
}: {
  title: string;
  body: string;
  danger?: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded border p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        danger
          ? "border-rose-500/30 bg-rose-500/5 hover:bg-rose-500/10"
          : "border-zinc-800 bg-zinc-950/50 hover:border-zinc-600"
      }`}
    >
      <span className={`text-sm font-semibold ${danger ? "text-rose-100" : "text-zinc-100"}`}>
        {title}
      </span>
      <span className="mt-2 block text-xs leading-5 text-zinc-500">{body}</span>
    </button>
  );
}

function Field({
  label,
  value,
  tone = "neutral",
  mono = false,
}: {
  label: string;
  value: string;
  tone?: Tone;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className={`mt-1 break-words text-sm ${mono ? "font-mono" : ""} ${toneText(tone)}`}>
        {value}
      </dd>
    </div>
  );
}

function InlineNotice({
  tone,
  children,
}: {
  tone: "success" | "warning" | "error";
  children: ReactNode;
}) {
  const cls =
    tone === "success"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
      : tone === "warning"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-100"
        : "border-rose-900/60 bg-rose-950/40 text-rose-200";
  return <p className={`mt-3 rounded border p-3 text-xs leading-5 ${cls}`}>{children}</p>;
}

function LinkButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="rounded border border-zinc-700 bg-zinc-950/40 px-3 py-1.5 text-xs font-medium text-zinc-200 hover:border-cyan-700 hover:text-cyan-100"
    >
      {children}
    </Link>
  );
}

function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`rounded-full border px-3 py-1 text-xs ${pillClass(tone)}`}>
      {children}
    </span>
  );
}

type Tone = "neutral" | "good" | "warn" | "bad";

function statusLabel(health: BaseHealthSnapshot | null): string {
  if (!health) return "Checking database";
  if (health.pct >= 90) return "Database up to date";
  if (health.pct > 0) return "Database partially updated";
  return "Database out of date";
}

function statusTone(health: BaseHealthSnapshot | null): Tone {
  if (!health) return "neutral";
  if (health.pct >= 90) return "good";
  if (health.pct > 0) return "warn";
  return "bad";
}

function borderClass(tone: Tone): string {
  if (tone === "good") return "border-emerald-500/20";
  if (tone === "warn") return "border-amber-500/30";
  if (tone === "bad") return "border-rose-500/30";
  return "border-zinc-800";
}

function toneText(tone: Tone): string {
  if (tone === "good") return "text-emerald-200";
  if (tone === "warn") return "text-amber-200";
  if (tone === "bad") return "text-rose-300";
  return "text-zinc-100";
}

function pillClass(tone: Tone): string {
  if (tone === "good") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
  if (tone === "warn") return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  if (tone === "bad") return "border-rose-500/30 bg-rose-500/10 text-rose-200";
  return "border-zinc-700 bg-zinc-950/70 text-zinc-300";
}

function resultClass(tone: Tone): string {
  if (tone === "good") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-100";
  if (tone === "warn") return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  return "border-zinc-800 bg-zinc-950/50 text-zinc-200";
}

function jobBadgeClass(state: string | null | undefined): string {
  const base = "rounded-full border px-2 py-0.5 text-center text-[11px] capitalize";
  if (state === "success") return `${base} border-emerald-500/30 text-emerald-200`;
  if (state === "error") return `${base} border-rose-500/30 text-rose-200`;
  if (state === "running" || state === "queued") {
    return `${base} border-amber-500/30 text-amber-200`;
  }
  return `${base} border-zinc-700 text-zinc-400`;
}

function formatStageHuman(stage: string): string {
  const map: Record<string, string> = {
    queued: "Queued",
    market_cap: "Refreshing market-cap snapshot",
    planning: "Planning",
    download_extract: "Downloading CVM files",
    process_data: "Processing data",
    persist_reports: "Saving to local database",
    finalizing: "Finalizing",
  };
  return map[stage] ?? stage.replace(/_/g, " ");
}

function formatJobState(value: string | null | undefined): string {
  const normalized = String(value ?? "unknown");
  if (normalized === "already_current") return "No pending issues";
  if (normalized === "success") return "Completed";
  if (normalized === "error") return "Completed with failures";
  if (normalized === "cancelled") return "Cancelled";
  if (normalized === "running") return "In progress";
  if (normalized === "queued") return "Queued";
  return normalized.replace(/_/g, " ");
}

function fmtInt(value: number | null | undefined): string {
  return new Intl.NumberFormat("en-US").format(Number(value ?? 0));
}

function fmtPct(value: number | null | undefined): string {
  return `${Number(value ?? 0).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDateTimeShort(value: string | null): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

function formatElapsed(value: string | null): string {
  if (!value) return "n/a";
  const start = new Date(value).getTime();
  if (Number.isNaN(start)) return "n/a";
  const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function formatBytes(bytes: number | null | undefined): string {
  if (!Number.isFinite(bytes) || Number(bytes) <= 0) return "0 bytes";
  const units = ["bytes", "KB", "MB", "GB"];
  let value = Number(bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function shortJobId(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}
