import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  COMPANY_UNIVERSE_PRESETS,
  completeOnboardingSetup,
  skipOnboardingSetup,
  startOnboardingSetup,
} from "@/lib/api/onboarding";
import {
  fetchRefreshJob,
  isActiveRefreshJob,
  refreshProgress,
} from "@/lib/api/updateBase";
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
  cancelLabel = "Configure later",
  surface = "first-run",
}: Props) {
  const queryClient = useQueryClient();
  const [selectedPreset, setSelectedPreset] =
    useState<CompanyUniversePreset>("top_200");
  const [jobId, setJobId] = useState<string | null>(
    initialState.refresh_job_id ?? null,
  );
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

  const job = jobQuery.data?.mode === "desktop" ? jobQuery.data.job : initialState.refresh_job;
  const jobState = String(job?.state ?? "");
  const progress = refreshProgress(job);
  const isRunning = isActiveRefreshJob(job);
  const isSuccess = jobState === "success";
  const isFailure = ["error", "cancelled", "interrupted"].includes(jobState);

  const completeMutation = useMutation({
    mutationFn: completeOnboardingSetup,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["onboarding-state"] });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
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

  const skipMutation = useMutation({
    mutationFn: skipOnboardingSetup,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["onboarding-state"] });
      onDone();
    },
  });

  useEffect(() => {
    if (!isSuccess || completeMutation.isSuccess || completeMutation.isPending) {
      return;
    }
    void completeMutation.mutateAsync();
  }, [completeMutation, isSuccess]);

  const topNSourceMissing =
    !initialState.market_cap_source_available && selectedPreset !== "all";
  const cardsDisabled = startMutation.isPending || isRunning || completeMutation.isPending;
  const selectedMeta = useMemo(
    () => COMPANY_UNIVERSE_PRESETS.find((item) => item.value === selectedPreset),
    [selectedPreset],
  );

  function handleContinue() {
    startMutation.mutate(selectedPreset);
  }

  function handleDone() {
    onDone();
  }

  function handleSecondary() {
    if (onCancel) {
      onCancel();
      return;
    }
    skipMutation.mutate();
  }

  return (
    <main
      className={surface === "first-run" ? "min-h-full" : "min-h-full rounded-lg border border-border-subtle"}
      style={{
        background: "var(--color-surface-1)",
        color: "var(--color-text-primary)",
        padding: surface === "first-run" ? "48px 20px" : "24px",
      }}
    >
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-5">
        <header className="border-b border-border-subtle pb-5">
          <p className="font-mono text-xs uppercase tracking-wider text-action-primary">
            {surface === "first-run" ? "Initial setup" : "Data setup"}
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-text-primary">
            Set up your company universe
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-text-secondary">
            Choose how much B3 company data you want to download now. You can
            expand your coverage later.
          </p>
        </header>

        {initialState.market_cap_source_available ? null : (
          <StateBanner
            variant="empty"
            title="Market cap ranking source needed"
            message="Top company presets need a ranking source. You can choose All B3 companies now, or configure the ranking source and retry."
            size="dense"
          />
        )}

        {isSuccess ? (
          <SuccessState
            count={startedSelection.count}
            source={startedSelection.source}
            onDone={handleDone}
            completing={completeMutation.isPending}
          />
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {COMPANY_UNIVERSE_PRESETS.map((preset) => (
                <PresetCard
                  key={preset.value}
                  preset={preset.value}
                  title={preset.title}
                  label={preset.label}
                  description={preset.description}
                  recommended={preset.recommended}
                  selected={selectedPreset === preset.value}
                  disabled={cardsDisabled}
                  sourceMissing={!initialState.market_cap_source_available && preset.value !== "all"}
                  onSelect={setSelectedPreset}
                />
              ))}
            </div>

            <p className="text-xs text-text-tertiary">
              You can change or expand this later in Database &gt; Company universe.
            </p>

            {startedSelection.warning ? (
              <StateBanner
                variant="empty"
                title="Coverage note"
                message={startedSelection.warning}
                size="dense"
              />
            ) : null}

            {isRunning || startMutation.isPending ? (
              <ProgressState
                job={job}
                progress={progress}
                presetTitle={selectedMeta?.title ?? "Selected universe"}
                selectedCount={startedSelection.count}
              />
            ) : null}

            {isFailure ? (
              <StateBanner
                variant="error"
                title="Setup did not finish"
                message={job?.error || "The download stopped before it finished. You can retry with the same preset."}
                onRetry={handleContinue}
              />
            ) : null}

            {startMutation.isError ? (
              <StateBanner
                variant="error"
                title={topNSourceMissing ? "Ranking source unavailable" : "Could not start setup"}
                message={
                  startMutation.error instanceof Error
                    ? startMutation.error.message
                    : String(startMutation.error)
                }
                onRetry={handleContinue}
              />
            ) : null}

            <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle pt-4">
              <Button
                type="button"
                variant="ghost"
                disabled={cardsDisabled || (!onCancel && skipMutation.isPending)}
                loading={!onCancel && skipMutation.isPending}
                onClick={handleSecondary}
              >
                {cancelLabel}
              </Button>
              <Button
                type="button"
                variant="primary"
                disabled={cardsDisabled}
                loading={startMutation.isPending}
                onClick={handleContinue}
              >
                Continue
              </Button>
            </footer>
          </>
        )}
      </section>
    </main>
  );
}

function PresetCard({
  preset,
  title,
  label,
  description,
  recommended,
  selected,
  disabled,
  sourceMissing,
  onSelect,
}: {
  preset: CompanyUniversePreset;
  title: string;
  label: string;
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
      disabled={disabled}
      aria-pressed={selected}
      onClick={() => onSelect(preset)}
      className="min-h-[164px] text-left transition-colors"
      style={{
        background: selected ? "var(--color-surface-3)" : "var(--color-surface-2)",
        border: selected
          ? "1px solid var(--color-action-primary)"
          : "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        padding: "16px",
        opacity: disabled ? 0.65 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
          <p className="mt-1 font-mono text-xs uppercase tracking-wider text-text-tertiary">
            {label}
          </p>
        </div>
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
      <p className="mt-4 text-sm leading-5 text-text-secondary">{description}</p>
      {sourceMissing ? (
        <p className="mt-3 text-xs text-state-warn">
          Needs a ranking source.
        </p>
      ) : null}
    </button>
  );
}

function ProgressState({
  job,
  progress,
  presetTitle,
  selectedCount,
}: {
  job: RefreshJobStatus | null | undefined;
  progress: number;
  presetTitle: string;
  selectedCount: number;
}) {
  const queued = job?.queued ?? selectedCount;
  const processed = job?.processed ?? 0;
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
            {processed.toLocaleString("pt-BR")} of {queued.toLocaleString("pt-BR")} companies processed
          </p>
        </div>
        <span className="font-mono text-sm text-text-secondary">{progress}%</span>
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
  source,
  completing,
  onDone,
}: {
  count: number;
  source: string | null;
  completing: boolean;
  onDone: () => void;
}) {
  return (
    <article
      className="border border-state-ok bg-surface-2 p-5"
      style={{ borderRadius: "var(--radius-md)" }}
    >
      <p className="font-mono text-xs uppercase tracking-wider text-state-ok">
        Setup complete
      </p>
      <h2 className="mt-2 text-lg font-semibold text-text-primary">
        Company universe is ready
      </h2>
      <p className="mt-2 text-sm text-text-secondary">
        {count > 0
          ? `${count.toLocaleString("pt-BR")} companies were queued for local CVM data.`
          : "Your local setup is ready."}
        {source ? ` Source: ${source}.` : ""}
      </p>
      <div className="mt-5">
        <Button
          type="button"
          variant="primary"
          loading={completing}
          onClick={onDone}
        >
          Continue
        </Button>
      </div>
    </article>
  );
}
