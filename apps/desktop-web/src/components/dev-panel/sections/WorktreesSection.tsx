import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { DEV_WORKTREES_QUERY_KEY, fetchDevWorktrees, switchDevWorktree } from "@/lib/api/devPanel";
import type { DevInstallProgress, DevNoticeDetail, DevWorktree } from "@/lib/bridge/types.dev";

import { SectionFrame, Tag } from "../SectionFrame";
import type { DevPanelSection } from "../sections";

export const INSTALL_DURATION = "about 1-2 minutes";

/** The list scrolls past this height so the sections below stay in reach at laptop height (1366x768). */
const LIST_MAX_HEIGHT = 200;
/** How often the list is read again while an install runs, for its current step. */
const INSTALL_POLL_MS = 1000;

/** `m:ss`. */
export function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Whole seconds since `startedAt` (Unix seconds), counted every second. */
function useElapsedSeconds(startedAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return Math.max(0, Math.floor(now / 1000 - startedAt));
}

type RowProps = {
  worktree: DevWorktree;
  supervised: boolean;
  /** A switch or install is under way: no second one. */
  busy: boolean;
  onSwitch: (worktree: DevWorktree) => void;
};

function WorktreeRow({ worktree, supervised, busy, onSwitch }: RowProps) {
  const differences = worktree.dependency_differences;
  const installs = worktree.installs_needed;
  const installing = installs.length > 0;
  return (
    <li className="flex items-start gap-2 py-1" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
      <div className="min-w-0 flex-1">
        <div className="font-mono text-sm" style={{ color: "var(--color-text-primary)", overflowWrap: "anywhere" }}>
          {worktree.name}
          {worktree.is_main_checkout ? <Tag color="var(--color-text-secondary)">Main checkout</Tag> : null}
          {worktree.active ? <Tag color="var(--color-action-primary)">Active</Tag> : null}
          {worktree.isolated_data ? (
            <Tag color="var(--color-state-warn)">
              <span aria-hidden="true">▲</span>
              Isolated data
            </Tag>
          ) : null}
          {differences.length > 0 ? (
            <Tag color="var(--color-state-warn)">
              <span aria-hidden="true">●</span>
              Dependencies differ
            </Tag>
          ) : null}
        </div>
        <div className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)", overflowWrap: "anywhere" }}>
          {worktree.branch ?? "Detached HEAD"}
        </div>
        {differences.length > 0 ? (
          <div className="text-2xs" style={{ color: "var(--color-text-secondary)" }}>
            {installing
              ? `Switching installs its own dependencies first (${INSTALL_DURATION}).`
              : "Runs on its own installed dependencies."}{" "}
            Differs: {differences.join(", ")}.
          </div>
        ) : null}
      </div>
      {worktree.active ? null : (
        <Button
          size="xs"
          disabled={!supervised || busy}
          title={
            !supervised
              ? "No dev supervisor: switching is unavailable."
              : installing
                ? `Installs ${installs.join(" and ")} for ${worktree.name} (${INSTALL_DURATION}), then reopens the window on it`
                : `Reopen the window running ${worktree.name}`
          }
          aria-label={installing ? `Install dependencies and switch to ${worktree.name}` : `Switch to ${worktree.name}`}
          onClick={() => onSwitch(worktree)}
        >
          {installing ? "Install & switch" : "Switch"}
        </Button>
      )}
    </li>
  );
}

/** The install a switch is waiting for: its step and elapsed time, so the panel never looks frozen. */
function InstallProgress({ install, current }: { install: DevInstallProgress; current: string | undefined }) {
  const elapsed = useElapsedSeconds(install.started_at);
  return (
    <StateBanner variant="loading" size="dense" title={`Installing dependencies for ${install.name}`}>
      <p className="text-xs" style={{ margin: 0, color: "var(--color-text-primary)" }}>
        {install.step}…{" "}
        <span className="font-mono" aria-live="off" style={{ color: "var(--color-text-secondary)" }}>
          {formatElapsed(elapsed)} elapsed
        </span>
      </p>
      <p className="text-2xs" style={{ margin: 0, color: "var(--color-text-secondary)" }}>
        Usually {INSTALL_DURATION}. The window stays on {current ?? "this worktree"} and reopens on {install.name} once
        the install is done.
      </p>
    </StateBanner>
  );
}

/** The failed command of a failed install and the end of its output. */
function FailedCommand({ detail }: { detail: DevNoticeDetail }) {
  return (
    <>
      {detail.command ? (
        <p className="text-xs" style={{ margin: 0, color: "var(--color-text-secondary)" }}>
          Command:{" "}
          <code className="font-mono" style={{ color: "var(--color-text-primary)", overflowWrap: "anywhere" }}>
            {detail.command}
          </code>
          {detail.exit_code !== null ? ` (exit code ${detail.exit_code})` : null}
        </p>
      ) : null}
      <pre
        tabIndex={0}
        aria-label="Output of the failed install"
        className="font-mono text-2xs"
        style={{
          margin: 0,
          maxHeight: 160,
          overflow: "auto",
          whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
          color: "var(--color-text-secondary)",
          background: "var(--color-surface-1)",
          border: "1px solid var(--color-border-subtle)",
          borderRadius: "var(--radius-sm)",
          padding: "6px 8px",
        }}
      >
        {detail.output}
      </pre>
    </>
  );
}

function WorktreesSection() {
  const list = useQuery({
    queryKey: DEV_WORKTREES_QUERY_KEY,
    queryFn: fetchDevWorktrees,
    staleTime: 0,
    retry: false,
    refetchInterval: (query) => (query.state.data?.install ? INSTALL_POLL_MS : false),
  });
  const switching = useMutation({
    mutationFn: (worktree: DevWorktree) => switchDevWorktree(worktree.path),
    // Resolve only once the list shows the install, so the panel never claims the window is reopening.
    onSuccess: (result) => (result.installing ? list.refetch() : undefined),
  });
  const target = switching.variables?.name;
  const install = list.data?.install ?? null;
  // The window closes right away, or once the install it waited for is done (an install that failed leaves a detail).
  const reopening =
    switching.isSuccess && (!switching.data.installing || (install === null && !list.data?.notice_detail));
  const current = list.data?.worktrees.find((worktree) => worktree.active)?.name;

  return (
    <SectionFrame
      title="Worktrees"
      action={
        <Button variant="ghost" size="xs" onClick={() => void list.refetch()} disabled={list.isFetching || install !== null}>
          {list.isFetching && install === null ? "Refreshing…" : "Refresh"}
        </Button>
      }
    >
      {list.isPending ? (
        <StateBanner variant="loading" size="dense" title="Listing worktrees…" />
      ) : list.isError ? (
        <StateBanner
          variant="error"
          size="dense"
          title="Worktrees unavailable"
          message={list.error.message}
          onRetry={() => void list.refetch()}
        />
      ) : (
        <>
          {install ? <InstallProgress install={install} current={current} /> : null}
          {list.data.notice ? (
            <StateBanner
              variant={list.data.notice_detail ? "error" : "warning"}
              size="dense"
              title="Last worktree switch"
              message={list.data.notice}
            >
              {list.data.notice_detail ? <FailedCommand detail={list.data.notice_detail} /> : null}
            </StateBanner>
          ) : null}
          {list.data.worktrees.length === 0 ? (
            <StateBanner variant="empty" size="dense" title="Git listed no worktrees." />
          ) : (
            <ul className="flex flex-col" style={{ margin: 0, padding: 0, listStyle: "none", maxHeight: LIST_MAX_HEIGHT, overflowY: "auto" }}>
              {list.data.worktrees.map((worktree) => (
                <WorktreeRow
                  key={worktree.path}
                  worktree={worktree}
                  supervised={list.data.supervised}
                  busy={switching.isPending || install !== null || reopening}
                  onSwitch={(chosen) => switching.mutate(chosen)}
                />
              ))}
            </ul>
          )}
          {!list.data.supervised ? (
            <p className="text-xs" style={{ margin: 0, color: "var(--color-text-secondary)" }}>
              No dev supervisor: switching is unavailable.
            </p>
          ) : null}
        </>
      )}
      {switching.isPending || reopening ? (
        <p className="text-xs" role="status" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
          {switching.isPending ? `Switching to ${target}…` : `Switching to ${target}: the window reopens there.`}
        </p>
      ) : null}
      {switching.error ? (
        <p className="text-xs" role="alert" style={{ color: "var(--color-state-err)", margin: 0 }}>
          ! {switching.error.message}
        </p>
      ) : null}
    </SectionFrame>
  );
}

export const section: DevPanelSection = { id: "worktrees", order: 150, Component: WorktreesSection };
