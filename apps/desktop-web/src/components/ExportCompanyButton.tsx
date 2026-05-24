import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  exportCompanyWorkbook,
  fetchOutputDir,
  type ExportCompanyOutcome,
  type OutputDirOutcome,
} from "@/lib/api/exports";
import { getBridgeMode } from "@/lib/bridge/adapter";
import type { ExportCompanyResult } from "@/lib/bridge/types";
import { Button } from "@/components/ui/Button";

type Props = {
  cdCvm: number;
  statementType?: string;
  scopeLabel?: string;
  scopeNote?: string;
  className?: string;
};

const SUCCESS_DISPLAY_MS = 12_000;

export function ExportCompanyButton({
  cdCvm,
  statementType,
  scopeLabel,
  scopeNote,
  className,
}: Props) {
  const bridgeMode = getBridgeMode();
  const isDesktop = bridgeMode === "desktop";
  
  const finalScopeLabel = scopeLabel || (statementType ? `Demonstrativo ${statementType}` : "Full company workbook");

  const outputDirQuery = useQuery<OutputDirOutcome>({
    queryKey: ["output-dir"],
    queryFn: fetchOutputDir,
    enabled: isDesktop,
    staleTime: 60_000,
  });

  const [lastOutcome, setLastOutcome] = useState<ExportCompanyOutcome | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => exportCompanyWorkbook(cdCvm, { reveal: false, statementType }),
    onSuccess: (outcome) => {
      setLastOutcome(outcome);
      if (outcome.mode === "desktop" && outcome.result.error) {
        setLastError(outcome.result.error);
      } else {
        setLastError(null);
      }
    },
    onError: (err) => {
      setLastError(err instanceof Error ? err.message : String(err));
      setLastOutcome(null);
    },
  });

  // Auto-collapse the success banner so the header doesn't grow forever.
  useEffect(() => {
    if (!lastOutcome) return;
    const isSuccess =
      lastOutcome.mode === "desktop" && lastOutcome.result.ok === true;
    if (!isSuccess) return;
    const timer = setTimeout(() => setLastOutcome(null), SUCCESS_DISPLAY_MS);
    return () => clearTimeout(timer);
  }, [lastOutcome]);

  const outputDir =
    outputDirQuery.data?.mode === "desktop"
      ? outputDirQuery.data.info.path
      : null;
  const outputDirMissing =
    outputDirQuery.data?.mode === "desktop" &&
    outputDirQuery.data.info.exists === false;

  const isRunning = mutation.isPending;
  const isUnsupported = !isDesktop;

  const successResult =
    lastOutcome?.mode === "desktop" && lastOutcome.result.ok
      ? lastOutcome.result
      : null;
  const errorMessage =
    lastError ??
    (lastOutcome?.mode === "desktop"
      ? (lastOutcome.result.error ?? null)
      : null) ??
    (lastOutcome?.mode === "browser" ? lastOutcome.reason : null);

  return (
    <div className={className ?? "space-y-2"}>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size="xs"
          onClick={() => mutation.mutate()}
          disabled={isRunning || isUnsupported}
          loading={isRunning}
        >
          {isRunning ? "Exportando…" : "Exportar Excel"}
        </Button>
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          {finalScopeLabel}
        </span>
      </div>
      {scopeNote ? (
        <p className="text-[11px] text-zinc-500">{scopeNote}</p>
      ) : null}
      <StatusLine
        isUnsupported={isUnsupported}
        outputDir={outputDir}
        outputDirMissing={outputDirMissing}
        successResult={successResult}
        errorMessage={errorMessage}
        isRunning={isRunning}
        statementType={statementType}
      />
    </div>
  );
}

function StatusLine({
  isUnsupported,
  outputDir,
  outputDirMissing,
  successResult,
  errorMessage,
  isRunning,
  statementType,
}: {
  isUnsupported: boolean;
  outputDir: string | null;
  outputDirMissing: boolean;
  successResult: ExportCompanyResult | null;
  errorMessage: string | null;
  isRunning: boolean;
  statementType?: string;
}) {
  if (isUnsupported) {
    return (
      <p className="text-[11px] text-amber-300">
        Browser mode — Excel export is only available inside the packaged
        desktop app or via{" "}
        <code className="font-mono">python -m desktop.app --vite</code>.
      </p>
    );
  }
  if (errorMessage) {
    return (
      <p className="rounded border border-rose-900/60 bg-rose-950/40 px-2 py-1 text-[11px] text-rose-200">
        Não foi possível gerar o workbook. {errorMessage}
      </p>
    );
  }
  if (successResult) {
    return (
      <div className="space-y-0.5 rounded border border-emerald-900/60 bg-emerald-950/30 px-2 py-1 text-[11px] text-emerald-200">
        <p>
          Workbook salvo:{" "}
          <code className="font-mono text-emerald-100">
            {successResult.file_name}
          </code>
          {typeof successResult.size_bytes === "number" ? (
            <span className="text-emerald-300/70">
              {" "}
              · {formatBytes(successResult.size_bytes)}
            </span>
          ) : null}
        </p>
        {successResult.file_path ? (
          <p
            className="break-all text-emerald-300/70"
            title={successResult.file_path}
          >
            {successResult.file_path}
          </p>
        ) : null}
      </div>
    );
  }
  if (isRunning) {
    return (
      <p className="text-[11px] text-amber-300">
        {statementType
          ? `Generating workbook (${statementType} scope)…`
          : "Generating workbook (statements + KPIs)…"}
      </p>
    );
  }
  if (outputDirMissing) {
    return (
      <p className="text-[11px] text-amber-300">
        Output folder não encontrado em{" "}
        <code className="font-mono">{outputDir ?? "—"}</code>. Será criado no
        primeiro export.
      </p>
    );
  }
  if (outputDir) {
    return (
      <p className="text-[11px] text-zinc-500">
        Destino:{" "}
        <code className="break-all font-mono text-zinc-400">{outputDir}</code>
      </p>
    );
  }
  return null;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}
