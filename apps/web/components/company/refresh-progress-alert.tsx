"use client";

import { LoaderCircleIcon, RotateCcwIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { getRefreshViewModel } from "@/lib/company-refresh-state";
import { cn } from "@/lib/utils";

type RefreshViewModel = ReturnType<typeof getRefreshViewModel>;

type RefreshProgressAlertProps = {
  view: RefreshViewModel;
  progressLabel: string | null;
  isManualStatusRefreshing: boolean;
  onManualStatusRefresh: () => void;
  onRequestAgain: () => void;
};

export function RefreshProgressAlert({
  view,
  progressLabel,
  isManualStatusRefreshing,
  onManualStatusRefresh,
  onRequestAgain,
}: RefreshProgressAlertProps) {
  if (!view.showCard) {
    return null;
  }

  return (
    <Alert
      className={
        view.isDestructive
          ? "rounded-[1.5rem] border border-destructive/25 bg-destructive/6 px-4 py-4"
          : "rounded-[1.5rem] border border-border/70 bg-muted/28 px-4 py-4"
      }
    >
      <AlertTitle className="space-y-2">
        <Badge
          variant="outline"
          className={cn(
            "w-fit rounded-full border px-2.5 py-0.5 text-xs uppercase tracking-[0.18em]",
            view.stepClassName,
          )}
        >
          {view.stepLabel}
        </Badge>
        <span className="block">{view.title}</span>
      </AlertTitle>

      <AlertDescription
        className="space-y-3"
        aria-live="polite"
        aria-atomic="true"
      >
        <p>{view.message}</p>
        {view.detail ? <p>{view.detail}</p> : null}

        {view.estimate ? (
          <div className="rounded-[1.25rem] border border-border/65 bg-background/82 px-4 py-4 shadow-[0_1px_0_rgba(255,255,255,0.22)]">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.22em] text-muted-foreground">
                  Progresso do refresh
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Acompanhamento aproximado da atualizacao on-demand.
                </p>
              </div>
              {progressLabel ? (
                <p className="text-lg font-semibold tabular-nums text-foreground">
                  {progressLabel}
                </p>
              ) : null}
            </div>

            <Progress
              value={view.estimate.progress}
              aria-label="Progresso estimado da atualizacao on-demand"
              indicatorClassName={view.estimate.indicatorClassName}
            />

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>{view.estimate.etaLabel}</span>
              {view.estimate.completionLabel ? (
                <span>{view.estimate.completionLabel}</span>
              ) : null}
            </div>

            {view.estimate.confidenceLabel ? (
              <p className="mt-2 text-xs text-muted-foreground">
                {view.estimate.confidenceLabel}
              </p>
            ) : null}
          </div>
        ) : null}

        {view.showManualStatusButton || view.showRequestAgainButton ? (
          <div className="flex flex-wrap items-center gap-2">
            {view.showManualStatusButton ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="rounded-full px-3"
                onClick={onManualStatusRefresh}
                disabled={isManualStatusRefreshing}
              >
                {isManualStatusRefreshing ? (
                  <LoaderCircleIcon className="animate-spin" />
                ) : (
                  <RotateCcwIcon />
                )}
                {isManualStatusRefreshing
                  ? "Atualizando status..."
                  : "Atualizar status agora"}
              </Button>
            ) : null}

            {view.showRequestAgainButton ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="rounded-full px-3"
                onClick={onRequestAgain}
                disabled={isManualStatusRefreshing}
              >
                Solicitar novamente
              </Button>
            ) : null}
          </div>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
