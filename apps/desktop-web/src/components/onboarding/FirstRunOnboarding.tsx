import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  COMPANY_UNIVERSE_PRESETS,
  completeOnboardingSetup,
  startOnboardingSetup,
} from "@/lib/api/onboarding";
import {
  cancelRefresh,
  fetchRefreshJob,
  isActiveRefreshJob,
  refreshProgress,
} from "@/lib/api/updateBase";
import { useRefreshJobInvalidation } from "@/hooks/useRefreshJobInvalidation";
import type {
  CompanyUniversePreset,
  OnboardingState,
  RefreshJobStatus,
} from "@/lib/bridge/types";
import { Button } from "@/components/ui/Button";
import { StateBanner } from "@/components/feedback/StateBanner";

type Props = {
  initialState: OnboardingState;
  onDone: () => void;
  onCancel?: () => void;
  cancelLabel?: string;
  surface?: "first-run" | "page";
};

export function FirstRunOnboarding({
  initialState,
  onDone,
  onCancel,
  cancelLabel = "Back",
  surface = "first-run",
}: Props) {
  const queryClient = useQueryClient();
  const invalidateRefreshQueries = useRefreshJobInvalidation();
  const [selectedPreset, setSelectedPreset] = useState<CompanyUniversePreset>("top_200");
  const [jobId, setJobId] = useState<string | null>(initialState.refresh_job_id ?? null);
  const [startedSelection, setStartedSelection] = useState<{
    preset: CompanyUniversePreset | null;
    count: number;
    source: string | null;
    warning: string | null;
  }>({
    preset: initialState.selected_company_universe,
    count: initialState.selected_company_count,
    source: initialState.company_universe_source,
    warning: initialState.warning,
  });

  const jobQuery = useQuery({
    queryKey: ["onboarding-refresh-job", jobId],
    queryFn: () => fetchRefreshJob(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const job = query.state.data?.mode === "desktop" ? query.state.data.job : null;
      return isActiveRefreshJob(job) ? 2_000 : false;
    },
  });

  const fallbackJob =
    jobId && jobId === initialState.refresh_job_id ? initialState.refresh_job : null;
  const job = jobQuery.data?.mode === "desktop" ? jobQuery.data.job : fallbackJob;
  const jobState = String(job?.state ?? "");
  const progress = refreshProgress(job);
  const isRunning = isActiveRefreshJob(job);
  const isSuccess = jobState === "success";
  const isFailureRaw = ["error", "cancelled", "interrupted"].includes(jobState);

  const hasEverSucceededRef = useRef(false);
  if (isSuccess) hasEverSucceededRef.current = true;

  const completeMutation = useMutation({
    mutationFn: completeOnboardingSetup,
    onSuccess: () => {
      invalidateRefreshQueries();
      void queryClient.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
  });

  const startMutation = useMutation({
    mutationFn: startOnboardingSetup,
    onSuccess: (response) => {
      const selection = response.selection;
      setStartedSelection({
        preset: selection?.preset ?? selectedPreset,
        count: selection?.selected_count ?? response.queued ?? 0,
        source: selection?.source ?? null,
        warning: selection?.warning ?? null,
      });
      if (response.job_id) {
        setJobId(response.job_id);
      } else {
        void completeMutation.mutateAsync().then(onDone);
      }
      void queryClient.invalidateQueries({ queryKey: ["onboarding-state"] });
      void queryClient.invalidateQueries({ queryKey: ["refresh-jobs"] });
    },
  });

  const cancelJobMutation = useMutation({
    mutationFn: (id: string) => cancelRefresh(id),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["onboarding-refresh-job", jobId] });
    },
  });

  useEffect(() => {
    if (!isSuccess || completeMutation.isSuccess || completeMutation.isPending) return;
    void completeMutation.mutateAsync();
  }, [completeMutation, isSuccess]);

  const isFailure =
    isFailureRaw &&
    !hasEverSucceededRef.current &&
    !completeMutation.isPending &&
    !completeMutation.isSuccess;

  const topNSourceMissing = !initialState.market_cap_source_available && selectedPreset !== "all";
  const isStartingOrRunning = startMutation.isPending || isRunning;
  const cardsDisabled = isStartingOrRunning || completeMutation.isPending;

  const selectedMeta = useMemo(
    () => COMPANY_UNIVERSE_PRESETS.find((item) => item.value === selectedPreset),
    [selectedPreset],
  );

  const resultSummary = useMemo(() => extractResultSummary(job), [job]);
  const hasPartialFailures = isSuccess && (resultSummary?.error_count ?? 0) > 0;

  function handleStart() {
    startMutation.reset();
    setStartedSelection((prev) => ({ ...prev, warning: null }));
    startMutation.mutate(selectedPreset);
  }

  return (
    <main
      className={
        surface === "first-run"
          ? "min-h-full"
          : "min-h-full rounded-lg border border-border-subtle"
      }
      style={{
        background: "var(--color-surface-1)",
        color: "var(--color-text-primary)",
        padding: surface === "first-run" ? "48px 20px" : "24px",
      }}
    >
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-5">
        <header className="border-b border-border-subtle pb-5">
          <p className="font-mono text-xs uppercase tracking-wider text-action-primary">
            {surface === "first-run" ? "Initial Setup" : "Data Setup"}
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-text-primary">
            Choose your company universe
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            Select which B3 companies you want to download now. You can expand your
            coverage later.
          </p>
        </header>

        {!initialState.market_cap_source_available ? (
          <StateBanner
            variant="empty"
            title="Ranking source required"
            message="Top N presets require a market cap source. You can choose All Companies now or configure the source later."
            size="dense"
          />
        ) : null}

        {isSuccess ? (
          <SuccessState
            count={startedSelection.count}
            hasPartialFailures={hasPartialFailures}
            completing={completeMutation.isPending}
            onDone={onDone}
          />
        ) : (
          <>
            {!isStartingOrRunning ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {COMPANY_UNIVERSE_PRESETS.map((preset) => (
                  <PresetCard
                    key={preset.value}
                    preset={preset.value}
                    title={preset.title}
                    count={preset.count}
                    eta={preset.eta}
                    description={preset.description}
                    recommended={preset.recommended}
                    selected={selectedPreset === preset.value}
                    disabled={cardsDisabled}
                    sourceMissing={
                      !initialState.market_cap_source_available && preset.value !== "all"
                    }
                    onSelect={setSelectedPreset}
                  />
                ))}
              </div>
            ) : null}

            {startedSelection.warning ? (
              <StateBanner
                variant="empty"
                title="Coverage warning"
                message={startedSelection.warning}
                size="dense"
              />
            ) : null}

            {isStartingOrRunning ? (
              <ProgressState
                job={job}
                progress={progress}
                presetTitle={selectedMeta?.title ?? "Selected Universe"}
                selectedCount={startedSelection.count}
                onCancel={jobId ? () => cancelJobMutation.mutate(jobId) : undefined}
                cancelling={cancelJobMutation.isPending}
              />
            ) : null}

            {isFailure ? (
              <StateBanner
                variant="error"
                title="Setup not completed"
                message={
                  job?.error ||
                  "The download was interrupted. You can retry with the same preset."
                }
              />
            ) : null}

            {startMutation.isError ? (
              <StateBanner
                variant="error"
                title={
                  topNSourceMissing
                    ? "Ranking source unavailable"
                    : "Could not start"
                }
                message={
                  startMutation.error instanceof Error
                    ? startMutation.error.message
                    : String(startMutation.error)
                }
              />
            ) : null}

            {!isStartingOrRunning ? (
              <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-4">
                {onCancel ? (
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={cardsDisabled}
                    onClick={onCancel}
                  >
                    {cancelLabel}
                  </Button>
                ) : (
                  <div />
                )}
                <Button
                  type="button"
                  variant="primary"
                  disabled={cardsDisabled || topNSourceMissing}
                  loading={startMutation.isPending}
                  onClick={handleStart}
                >
                  {isFailure ? "Retry" : "Create local database"}
                </Button>
              </footer>
            ) : null}
          </>
        )}
      </section>
    </main>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function PresetCard({
  preset,
  title,
  count,
  eta,
  description,
  recommended,
  selected,
  disabled,
  sourceMissing,
  onSelect,
}: {
  preset: CompanyUniversePreset;
  title: string;
  count: string;
  eta: string;
  description: string;
  recommended?: boolean;
  selected: boolean;
  disabled: boolean;
  sourceMissing: boolean;
  onSelect: (preset: CompanyUniversePreset) => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled || sourceMissing}
      aria-pressed={selected}
      onClick={() => onSelect(preset)}
      className="min-h-[180px] text-left transition-colors"
      style={{
        background: selected ? "var(--color-surface-3)" : "var(--color-surface-2)",
        border: selected
          ? "1px solid var(--color-action-primary)"
          : "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "16px",
        opacity: disabled || sourceMissing ? 0.65 : 1,
        cursor: disabled || sourceMissing ? "not-allowed" : "pointer",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
        {recommended ? (
          <span
            className="font-mono text-[10px] uppercase"
            style={{
              color: "var(--color-text-inverse)",
              background: "var(--color-action-primary)",
              borderRadius: "var(--radius-sm)",
              padding: "2px 6px",
            }}
          >
            Default
          </span>
        ) : null}
      </div>
      <p className="mt-1 font-mono text-xs text-text-tertiary">
        {count} · {eta}
      </p>
      <p className="mt-3 text-sm leading-5 text-text-secondary">{description}</p>
      {sourceMissing ? (
        <p className="mt-3 text-xs text-state-warn">Requires a ranking source.</p>
      ) : null}
    </button>
  );
}

function ProgressState({
  job,
  progress,
  presetTitle,
  selectedCount,
  onCancel,
  cancelling,
}: {
  job: RefreshJobStatus | null | undefined;
  progress: number;
  presetTitle: string;
  selectedCount: number;
  onCancel?: () => void;
  cancelling: boolean;
}) {
  const queued = job?.queued ?? selectedCount;
  const processed = job?.processed ?? 0;
  const stageLabel = job?.stage ? formatStageLabel(job.stage) : null;

  return (
    <article
      role="status"
      aria-live="polite"
      className="border border-border-subtle bg-surface-2 p-4"
      style={{ borderRadius: "var(--radius-md)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-md font-semibold text-text-primary">
            Downloading {presetTitle}
          </h2>
          <p className="mt-1 text-xs text-text-tertiary">
            {processed.toLocaleString("en-US")} of {queued.toLocaleString("en-US")} companies
            processed
            {stageLabel ? ` · ${stageLabel}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-text-secondary">{progress}%</span>
          {onCancel ? (
            <button
              type="button"
              disabled={cancelling}
              onClick={onCancel}
              className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-rose-700 hover:text-rose-200 disabled:opacity-50"
            >
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          ) : null}
        </div>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-sm bg-surface-4">
        <div
          className="h-full bg-action-primary"
          style={{ width: `${Math.max(4, Math.min(100, progress))}%` }}
        />
      </div>
      {job?.log_lines?.length ? (
        <p className="mt-3 truncate font-mono text-xs text-text-tertiary">
          {job.log_lines[job.log_lines.length - 1]}
        </p>
      ) : null}
    </article>
  );
}

function SuccessState({
  count,
  hasPartialFailures,
  completing,
  onDone,
}: {
  count: number;
  hasPartialFailures: boolean;
  completing: boolean;
  onDone: () => void;
}) {
  return (
    <article
      className="border bg-surface-2 p-5"
      style={{
        borderColor: hasPartialFailures
          ? "var(--color-state-warn, #f59e0b)"
          : "var(--color-state-ok, #4ade80)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <p
        className="font-mono text-xs uppercase tracking-wider"
        style={{
          color: hasPartialFailures
            ? "var(--color-state-warn, #f59e0b)"
            : "var(--color-state-ok, #4ade80)",
        }}
      >
        {hasPartialFailures ? "Completed with warnings" : "Setup complete"}
      </p>
      <h2 className="mt-2 text-lg font-semibold text-text-primary">Done</h2>
      <p className="mt-2 text-sm text-text-secondary">
        {count > 0
          ? `${count.toLocaleString("en-US")} companies were queued for CVM data download.`
          : "Your local setup is ready."}
      </p>
      {hasPartialFailures ? (
        <p className="mt-3 text-sm" style={{ color: "var(--color-state-warn, #f59e0b)" }}>
          Some companies encountered errors during download.{" "}
          <Link
            to="/settings/coverage"
            style={{ textDecoration: "underline" }}
          >
            View Data Coverage →
          </Link>
        </p>
      ) : null}
      <div className="mt-5">
        <Button type="button" variant="primary" loading={completing} onClick={onDone}>
          Open app
        </Button>
      </div>
    </article>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function extractResultSummary(job: RefreshJobStatus | null | undefined): {
  success_count: number;
  no_data_count: number;
  error_count: number;
} | null {
  const result = job?.result as Record<string, unknown> | null | undefined;
  if (!result || typeof result !== "object") return null;
  const summary = (result as { summary?: unknown }).summary;
  if (!summary || typeof summary !== "object") return null;
  const s = summary as Record<string, unknown>;
  return {
    success_count: Number(s.success_count ?? 0),
    no_data_count: Number(s.no_data_count ?? 0),
    error_count: Number(s.error_count ?? 0),
  };
}

function formatStageLabel(stage: string): string {
  const map: Record<string, string> = {
    queued: "Queued",
    planning: "Planning",
    download_extract: "Downloading CVM files",
    process_data: "Processing data",
    persist_reports: "Saving to local database",
    finalizing: "Finalizing",
  };
  return map[stage] ?? stage.replace(/_/g, " ");
}
