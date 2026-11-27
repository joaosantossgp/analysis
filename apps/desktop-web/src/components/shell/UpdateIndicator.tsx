import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { isUpdateApplying, updateProgressLabel, useUpdateApply } from "@/hooks/useUpdateApply";
import { fetchStoredUpdateCheck, triggerSnoozeUpdate, UPDATE_CHECK_KEY } from "@/lib/api/appStatus";
import type { UpdateCheckResult, UpdateProgressStatus } from "@/lib/bridge/types";

import { ShellPopover } from "./ShellPopover";

/**
 * Poll the stored check (a local read; GitHub is contacted only by the startup
 * check and explicit user actions): fast while the startup check runs, then
 * once a minute to follow checks started in Settings or Diagnostics.
 */
export function updateCheckPollInterval(check: UpdateCheckResult | null | undefined): number | false {
  if (check === null) return false; // browser preview: no bridge, nothing to announce
  if (check?.status === "managed_by_git") return false;
  if (!check || check.status === "not_checked" || check.status === "unknown") return 5_000;
  return 60_000;
}

/**
 * Top-bar Software update pill and its panel (#627). Shown only when the last
 * check offered an update for the user's channel; a failed, offline or
 * postponed check shows nothing here and keeps its detail in Diagnostics.
 * Nothing is downloaded until the user chooses Update now.
 */
export function UpdateIndicator() {
  const queryClient = useQueryClient();
  const { data: check } = useQuery({
    queryKey: UPDATE_CHECK_KEY,
    queryFn: fetchStoredUpdateCheck,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => updateCheckPollInterval(query.state.data),
  });
  const offered = Boolean(check?.available);
  const update = useUpdateApply(offered);
  const [open, setOpen] = useState(false);
  const later = useMutation({
    mutationFn: async () => {
      const result = await triggerSnoozeUpdate();
      if (!result.ok) throw new Error(result.error || "The update was not postponed.");
    },
    onSuccess: () => {
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: UPDATE_CHECK_KEY });
    },
  });

  if (!check || !offered) return null;

  const pill = updatePill(check, update.progress, update.error);
  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="update-panel"
        aria-label={`Software update: ${pill.headline}`}
        title={pill.headline}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex shrink-0 items-center gap-1 rounded-sm border px-2 py-0.5 font-mono text-2xs uppercase tracking-wider hover:bg-[var(--color-surface-3)]"
        style={{ borderColor: pill.color, color: pill.color, background: open ? "var(--color-surface-3)" : undefined }}
      >
        <span aria-hidden="true">↑</span>
        {pill.short}
      </button>
      {open ? (
        <ShellPopover id="update-panel" title="Software update" closeLabel="Close Software update panel" onClose={() => setOpen(false)}>
          <UpdatePanelBody
            check={check}
            progress={update.progress}
            error={update.error}
            postponing={later.isPending}
            postponeError={later.error ? later.error.message : null}
            onUpdate={update.start}
            onLater={() => later.mutate()}
          />
        </ShellPopover>
      ) : null}
    </>
  );
}

function updatePill(check: UpdateCheckResult, progress: UpdateProgressStatus | null, error: string | null) {
  const version = offeredVersion(check);
  const prerelease = check.publication_kind === "pre-release";
  if (isUpdateApplying(progress)) {
    return { short: `Updating ${progress?.percent ?? 0}%`, headline: `Updating to ${version}`, color: "var(--color-state-info)" };
  }
  if (error) {
    return { short: "Update failed", headline: `Update to ${version} failed`, color: "var(--color-state-err)" };
  }
  return {
    // Version strings keep their case (0.30.0-rc.1) inside the uppercase pill;
    // "pre-release" shortens below xl so the top bar fits the 800px minimum window.
    short: (
      <>
        Update <span className="normal-case">{version}</span>
        {prerelease ? (
          <>
            <span className="hidden xl:inline"> · pre-release</span>
            <span className="xl:hidden"> · pre</span>
          </>
        ) : null}
      </>
    ),
    headline: `${prerelease ? "Pre-release" : "Release"} ${version} available`,
    color: "var(--color-state-info)",
  };
}

function offeredVersion(check: UpdateCheckResult): string {
  return check.version ?? check.latest_version ?? "unknown";
}

export type UpdatePanelBodyProps = {
  check: UpdateCheckResult;
  progress: UpdateProgressStatus | null;
  error: string | null;
  postponing: boolean;
  postponeError: string | null;
  onUpdate: () => void;
  onLater: () => void;
};

export function UpdatePanelBody({ check, progress, error, postponing, postponeError, onUpdate, onLater }: UpdatePanelBodyProps) {
  const version = offeredVersion(check);
  const prerelease = check.publication_kind === "pre-release";
  const applying = isUpdateApplying(progress);
  const percent = progress?.percent ?? 0;
  const current = check.current_version ?? "unknown";

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-semibold" style={{ color: "var(--color-text-primary)" }}>
          <span className="font-mono">{version}</span> is available
        </p>
        <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>
          {prerelease ? "Pre-release" : "Release"} · installed <span className="font-mono">{current}</span>
        </p>
        {prerelease ? (
          <p className="mt-0.5 text-xs" style={{ color: "var(--color-text-tertiary)" }}>
            Pre-releases bring features sooner and may be less stable.
          </p>
        ) : null}
        {check.status === "available_cached" ? (
          <p className="mt-0.5 text-xs" style={{ color: "var(--color-state-warn)" }}>
            The last update check failed; this offer comes from an earlier check.
          </p>
        ) : null}
      </div>

      {applying ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs" style={{ color: "var(--color-text-primary)" }}>
            <span>{updateProgressLabel(progress)}</span>
            <span className="font-mono tabular-nums">{percent}%</span>
          </div>
          <div
            role="progressbar"
            aria-label="Update progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            style={{ height: 4, background: "var(--color-surface-4)", borderRadius: 2, overflow: "hidden" }}
          >
            <div style={{ width: `${percent}%`, height: "100%", background: "var(--color-state-info)", transition: "width 180ms ease" }} />
          </div>
          <p className="text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
            Keep the app open: it restarts into {version} when the files are ready.
          </p>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button variant="primary" size="xs" onClick={onUpdate}>
            {error ? "Try again" : "Update now"}
          </Button>
          <Button variant="secondary" size="xs" loading={postponing} onClick={onLater}>
            Later
          </Button>
        </div>
      )}

      {error ? (
        <p role="alert" className="text-xs [overflow-wrap:anywhere]" style={{ color: "var(--color-state-err)" }}>
          <span className="block">Update failed: {error}</span>
          <span className="block">
            Version <span className="font-mono">{current}</span> keeps running.
          </span>
        </p>
      ) : null}
      {postponeError ? (
        <p role="alert" className="text-xs [overflow-wrap:anywhere]" style={{ color: "var(--color-state-err)" }}>
          Could not postpone the update: {postponeError}
        </p>
      ) : null}

      <p className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
        GitHub Releases · Downloads only after Update now, then restarts the app. Your data is not touched.
      </p>
      <div className="flex items-center justify-between gap-2 text-xs">
        {check.release_url ? (
          <a href={check.release_url} target="_blank" rel="noreferrer" style={{ color: "var(--color-id-link)" }}>
            Publication page ↗
          </a>
        ) : (
          <span />
        )}
        <a href="#/settings/diagnostics" style={{ color: "var(--color-id-link)" }}>
          Update details →
        </a>
      </div>
    </div>
  );
}
