import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { DEV_CONTEXT_QUERY_KEY, restartDevApp, setDevAutoRestart } from "@/lib/api/devPanel";
import type { DevContext } from "@/lib/bridge/types.dev";

import { SectionFrame } from "../SectionFrame";
import type { DevPanelSection } from "../sections";
import { useDevContext } from "../useDevContext";

function autoRestartNote(context: DevContext | undefined, applying: boolean): string {
  if (applying) return "Applying…";
  if (!context) return "Automatic restart: —";
  if (!context.supervised) return "No dev supervisor: restart controls are unavailable.";
  if (context.auto_restart === null) return "Automatic restart: —";
  return context.auto_restart
    ? "Automatic restart is on: the app restarts when a Python file under desktop/ or src/ changes."
    : "Automatic restart is off: the window stays as it is until you restart.";
}

function RestartSection() {
  const context = useDevContext().data;
  const queryClient = useQueryClient();
  const restart = useMutation({ mutationFn: restartDevApp });
  const autoRestart = useMutation({
    mutationFn: setDevAutoRestart,
    onSuccess: (enabled) =>
      queryClient.setQueryData<DevContext>(DEV_CONTEXT_QUERY_KEY, (current) =>
        current ? { ...current, auto_restart: enabled } : current,
      ),
  });
  const unsupervised = context?.supervised === false;
  const error = restart.error ?? autoRestart.error;
  const pending = context?.pending_changes ?? 0;

  return (
    <SectionFrame title="Restart">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          onClick={() => restart.mutate()}
          loading={restart.isPending}
          disabled={unsupervised || restart.isSuccess}
        >
          {restart.isSuccess ? "Restarting…" : "Restart app"}
        </Button>
        <Checkbox
          label="Restart automatically"
          checked={context?.auto_restart === true}
          disabled={typeof context?.auto_restart !== "boolean" || autoRestart.isPending}
          onChange={(event) => autoRestart.mutate(event.target.checked)}
        />
      </div>
      <p className="text-xs" role="status" style={{ color: "var(--color-text-secondary)", margin: 0 }}>
        {autoRestartNote(context, autoRestart.isPending)}
      </p>
      {pending > 0 ? (
        <p className="text-xs" style={{ color: "var(--color-state-warn)", margin: 0 }}>
          ● {pending} changed Python {pending === 1 ? "file" : "files"} not loaded yet.
        </p>
      ) : null}
      {error ? (
        <p className="text-xs" role="alert" style={{ color: "var(--color-state-err)", margin: 0 }}>
          ! {error.message}
        </p>
      ) : null}
    </SectionFrame>
  );
}

export const section: DevPanelSection = { id: "restart", order: 200, Component: RestartSection };
