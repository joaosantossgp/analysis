"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  type RefreshStatusItem,
  fetchRefreshStatus,
  fetchRequestRefresh,
  getUserFacingErrorMessage,
  isApiClientError,
} from "@/lib/api";
import { getReadableRefreshSuccessKey } from "@/lib/company-detail-handoff";
import { dispatchDesktopDataRefreshed } from "@/lib/desktop-data-events";
import {
  applyManualStatusFailure,
  applyRefreshPollFailure,
  applyRefreshStatusResult,
  createAlreadyCurrentRefreshState,
  createDelayedRefreshState,
  createDispatchFailureState,
  createDispatchedRefreshState,
  createIdleRefreshState,
  createSubmittingRefreshState,
  getNextPollingDelayMs,
  getRefreshViewModel,
  hasRefreshTimedOut,
  hydrateRefreshState,
  isAutoPollingPhase,
  RELOAD_DELAY_MS,
  type RefreshMachineState,
} from "@/lib/company-refresh-state";

type UseCompanyRefreshMachineOptions = {
  cdCvm: number;
  initialStatus?: RefreshStatusItem | null;
  range?: { startYear: number; endYear: number };
};

type UseCompanyRefreshMachineResult = {
  view: ReturnType<typeof getRefreshViewModel>;
  showButtonSpinner: boolean;
  progressLabel: string | null;
  isManualStatusRefreshing: boolean;
  handleRequestRefresh: () => void;
  handleManualStatusRefresh: () => void;
};

export function useCompanyRefreshMachine({
  cdCvm,
  initialStatus = null,
  range,
}: UseCompanyRefreshMachineOptions): UseCompanyRefreshMachineResult {
  const router = useRouter();
  const [state, setState] = useState<RefreshMachineState>(() =>
    createIdleRefreshState(),
  );
  const [isManualStatusRefreshing, setIsManualStatusRefreshing] =
    useState(false);
  const hydratedInitialStatusRef = useRef(false);
  const isMountedRef = useRef(true);
  const reloadTimerRef = useRef<number | null>(null);

  const view = getRefreshViewModel(state);
  const successHandoffKey =
    state.phase === "success"
      ? state.currentItem
        ? getReadableRefreshSuccessKey(state.currentItem)
        : "already-current"
      : null;

  const pollRefreshStatus = useCallback(
    async (source: "auto" | "manual") => {
      try {
        const items = await fetchRefreshStatus(cdCvm);

        if (!isMountedRef.current) {
          return;
        }

        setState((currentState) =>
          applyRefreshStatusResult(
            currentState,
            items[0] ?? null,
            Date.now(),
            { source },
          ),
        );
      } catch {
        if (!isMountedRef.current) {
          return;
        }

        setState((currentState) =>
          source === "manual"
            ? applyManualStatusFailure(currentState)
            : applyRefreshPollFailure(currentState),
        );
      } finally {
        if (isMountedRef.current && source === "manual") {
          setIsManualStatusRefreshing(false);
        }
      }
    },
    [cdCvm],
  );

  useEffect(() => {
    return () => {
      isMountedRef.current = false;

      if (reloadTimerRef.current !== null) {
        window.clearTimeout(reloadTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (hydratedInitialStatusRef.current || !initialStatus) {
      return;
    }

    hydratedInitialStatusRef.current = true;
    setState(hydrateRefreshState(initialStatus));
  }, [initialStatus]);

  useEffect(() => {
    if (!successHandoffKey) {
      return;
    }

    // Server path (web preview): invalida cache RSC e reexecuta a página.
    router.refresh();

    // Desktop path (.exe / pywebview): não há servidor, então
    // notificamos loaders client-side via event bus para refazerem
    // suas chamadas ao bridge.
    dispatchDesktopDataRefreshed({ cdCvm, scope: "company" });

    reloadTimerRef.current = window.setTimeout(() => {
      router.refresh();
      dispatchDesktopDataRefreshed({ cdCvm, scope: "company" });
    }, RELOAD_DELAY_MS);

    return () => {
      if (reloadTimerRef.current !== null) {
        window.clearTimeout(reloadTimerRef.current);
        reloadTimerRef.current = null;
      }
    };
  }, [cdCvm, router, successHandoffKey]);

  useEffect(() => {
    if (!isAutoPollingPhase(state.phase)) {
      return;
    }

    if (hasRefreshTimedOut(state, Date.now())) {
      setState((currentState) =>
        hasRefreshTimedOut(currentState, Date.now())
          ? createDelayedRefreshState(currentState)
          : currentState,
      );
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void pollRefreshStatus("auto");
    }, getNextPollingDelayMs(state));

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [pollRefreshStatus, state]);

  async function handleRequestRefresh() {
    if (view.requestButtonDisabled) {
      return;
    }

    setState(createSubmittingRefreshState());

    try {
      const payload = await fetchRequestRefresh(cdCvm, range);

      if (!isMountedRef.current) {
        return;
      }

      if (payload.status === "already_current") {
        setState(createAlreadyCurrentRefreshState(payload.message));
        return;
      }

      setState(createDispatchedRefreshState(Date.now()));
    } catch (error) {
      if (!isMountedRef.current) {
        return;
      }

      if (isApiClientError(error) && error.status === 429) {
        setState(createDispatchedRefreshState(Date.now()));
        return;
      }

      setState(createDispatchFailureState(getUserFacingErrorMessage(error)));
    }
  }

  function handleManualStatusRefresh() {
    if (state.phase !== "delayed" || isManualStatusRefreshing) {
      return;
    }

    setIsManualStatusRefreshing(true);
    void pollRefreshStatus("manual");
  }

  const showButtonSpinner =
    state.phase === "submitting" ||
    state.phase === "queued" ||
    state.phase === "running" ||
    state.phase === "reconnecting" ||
    state.phase === "success";
  const progressLabel = view.estimate
    ? `${Math.round(view.estimate.progress)}%`
    : null;

  return {
    view,
    showButtonSpinner,
    progressLabel,
    isManualStatusRefreshing,
    handleRequestRefresh,
    handleManualStatusRefresh,
  };
}
