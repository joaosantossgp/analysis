import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { LOCAL_DATABASE_STATE_KEY } from "@/lib/api/localDatabase";
import { cancelRefresh, startDataUpdate } from "@/lib/api/updateBase";
import type { LocalDatabaseState } from "@/lib/bridge/types.localDatabase";

type Props = {
  state: LocalDatabaseState;
  online: boolean;
  /** "panel" may cancel a run; "inline" (Home, empty states) only points to progress. */
  context: "panel" | "inline";
  size?: "xs" | "sm";
  onViewProgress?: () => void;
};

/**
 * The one data update action. Every surface renders this component so the
 * label and behavior never drift (ADR 0010).
 */
export function DataAction({ state, online, context, size = "sm", onViewProgress }: Props) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: LOCAL_DATABASE_STATE_KEY });
  const start = useMutation({ mutationFn: () => startDataUpdate({ mode: "missing" }), onSettled: refresh });
  const cancel = useMutation({
    mutationFn: (jobId: string) => cancelRefresh(jobId),
    onSettled: refresh,
  });

  const running = state.state === "files" || state.state === "updating";
  const error = (start.error ?? cancel.error) as Error | null;

  let button;
  if (running) {
    const jobId = state.run?.job_id;
    button =
      context === "panel" ? (
        <Button
          variant="secondary"
          size={size}
          loading={cancel.isPending}
          disabled={!jobId}
          onClick={() => jobId && cancel.mutate(jobId)}
        >
          Cancel update
        </Button>
      ) : (
        <Button variant="ghost" size={size} onClick={onViewProgress}>
          View progress
        </Button>
      );
  } else {
    const label = !state.has_statements
      ? state.state === "failed"
        ? "Try again"
        : "Download CVM data"
      : "Update data";
    const primary = !state.has_statements || state.state === "stale";
    button = (
      <Button
        variant={primary ? "primary" : "secondary"}
        size={size}
        disabled={!online}
        aria-describedby={!online ? "data-action-offline" : undefined}
        loading={start.isPending}
        onClick={() => start.mutate()}
      >
        {label}
      </Button>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {button}
      {!online && !running ? (
        <span id="data-action-offline" className="text-xs" style={{ color: "var(--color-state-warn)" }}>
          Offline — connect to download.
        </span>
      ) : null}
      {error ? (
        <span role="alert" className="text-xs" style={{ color: "var(--color-state-err)" }}>
          {error.message}
        </span>
      ) : null}
    </span>
  );
}
