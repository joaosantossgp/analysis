import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  exportCompanyWorkbook,
  fetchOutputDir,
  type ExportCompanyOutcome,
  type OutputDirOutcome,
} from "@/lib/api/exports";
import { getBridgeMode } from "@/lib/bridge/adapter";
import type { ExportCompanyResult } from "@/lib/bridge/types";

import type { ExportStatus } from "./ExportStatusLine";

type Options = {
  cdCvm: number;
  statementType?: string;
};

export function useExportAction({ cdCvm, statementType }: Options) {
  const bridgeMode = getBridgeMode();
  const isDesktop = bridgeMode === "desktop";
  const [lastOutcome, setLastOutcome] = useState<ExportCompanyOutcome | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null);

  const outputDirQuery = useQuery<OutputDirOutcome>({
    queryKey: ["output-dir"],
    queryFn: fetchOutputDir,
    enabled: isDesktop,
    staleTime: 60_000,
  });

  const mutation = useMutation({
    mutationFn: () => exportCompanyWorkbook(cdCvm, { reveal: false, statementType }),
    onSuccess: (outcome) => {
      setLastOutcome(outcome);
      setLastRunAt(new Date());
      if (outcome.mode === "desktop" && outcome.result.error) {
        setLastError(outcome.result.error);
      } else {
        setLastError(null);
      }
    },
    onError: (err) => {
      setLastOutcome(null);
      setLastRunAt(new Date());
      setLastError(err instanceof Error ? err.message : String(err));
    },
  });

  return useMemo(() => {
    const result: ExportCompanyResult | null =
      lastOutcome?.mode === "desktop" ? lastOutcome.result : null;
    const browserReason = lastOutcome?.mode === "browser" ? lastOutcome.reason : null;
    const errorMessage = lastError ?? result?.error ?? browserReason;
    const outputDir =
      outputDirQuery.data?.mode === "desktop" ? outputDirQuery.data.info.path : null;
    const outputDirMissing =
      outputDirQuery.data?.mode === "desktop" &&
      outputDirQuery.data.info.exists === false;

    let status: ExportStatus = "idle";
    if (!isDesktop) status = "unavailable";
    else if (mutation.isPending) status = "running";
    else if (errorMessage) status = "error";
    else if (result?.ok) status = "success";

    return {
      errorMessage,
      isDesktop,
      isRunning: mutation.isPending,
      lastRunAt,
      outputDir,
      outputDirMissing,
      result: result?.ok ? result : null,
      run: mutation.mutate,
      status,
    };
  }, [
    isDesktop,
    lastError,
    lastOutcome,
    lastRunAt,
    mutation.isPending,
    mutation.mutate,
    outputDirQuery.data,
  ]);
}
