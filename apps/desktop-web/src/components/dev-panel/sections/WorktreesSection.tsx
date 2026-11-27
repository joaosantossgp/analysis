import { useMutation, useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { DEV_WORKTREES_QUERY_KEY, fetchDevWorktrees, switchDevWorktree } from "@/lib/api/devPanel";
import type { DevWorktree } from "@/lib/bridge/types.dev";

import { SectionFrame, Tag } from "../SectionFrame";
import type { DevPanelSection } from "../sections";

export const NEEDS_OWN_DEPENDENCIES = "Needs its own dependencies; supported in a later version.";

/** The list scrolls past this height so the sections below stay in reach at laptop height (1366x768). */
const LIST_MAX_HEIGHT = 200;

function switchBlocker(worktree: DevWorktree, supervised: boolean): string | null {
  if (!supervised) return "No dev supervisor: switching is unavailable.";
  if (worktree.dependency_differences.length > 0) return NEEDS_OWN_DEPENDENCIES;
  return null;
}

type RowProps = {
  worktree: DevWorktree;
  supervised: boolean;
  /** A switch is under way: no second one. */
  busy: boolean;
  onSwitch: (worktree: DevWorktree) => void;
};

function WorktreeRow({ worktree, supervised, busy, onSwitch }: RowProps) {
  const blocker = switchBlocker(worktree, supervised);
  const differences = worktree.dependency_differences;
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
            {NEEDS_OWN_DEPENDENCIES} Differs: {differences.join(", ")}.
          </div>
        ) : null}
      </div>
      {worktree.active ? null : (
        <Button
          size="xs"
          disabled={blocker !== null || busy}
          title={blocker ?? `Reopen the window running ${worktree.name}`}
          aria-label={`Switch to ${worktree.name}`}
          onClick={() => onSwitch(worktree)}
        >
          Switch
        </Button>
      )}
    </li>
  );
}

function WorktreesSection() {
  const list = useQuery({ queryKey: DEV_WORKTREES_QUERY_KEY, queryFn: fetchDevWorktrees, staleTime: 0, retry: false });
  const switching = useMutation({ mutationFn: (worktree: DevWorktree) => switchDevWorktree(worktree.path) });
  const target = switching.variables?.name;

  return (
    <SectionFrame
      title="Worktrees"
      action={
        <Button variant="ghost" size="xs" onClick={() => void list.refetch()} disabled={list.isFetching}>
          {list.isFetching ? "Refreshing…" : "Refresh"}
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
          {list.data.notice ? (
            <StateBanner variant="warning" size="dense" title="Last worktree switch" message={list.data.notice} />
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
                  busy={switching.isPending || switching.isSuccess}
                  onSwitch={(chosen) => switching.mutate(chosen)}
                />
              ))}
            </ul>
          )}
          {!list.data.supervised ? (
            <p className="text-xs" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
              No dev supervisor: switching is unavailable.
            </p>
          ) : null}
        </>
      )}
      {switching.isPending || switching.isSuccess ? (
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
