import type { ExportCompanyResult } from "@/lib/bridge/types";

import { OutputPathDisplay } from "./OutputPathDisplay";

export type ExportStatus = "idle" | "running" | "success" | "error" | "unavailable";

type Props = {
  status: ExportStatus;
  message?: string | null;
  result?: ExportCompanyResult | null;
  outputDir?: string | null;
  outputDirMissing?: boolean;
  timestamp?: Date | null;
};

const STATUS_META: Record<
  ExportStatus,
  { code: string; label: string; color: string; role: "status" | "alert" }
> = {
  idle: {
    code: "RDY",
    label: "Pronto para exportar",
    color: "var(--color-text-tertiary)",
    role: "status",
  },
  running: {
    code: "RUN",
    label: "Gerando workbook",
    color: "var(--color-state-warn)",
    role: "status",
  },
  success: {
    code: "OK",
    label: "Export concluído",
    color: "var(--color-state-ok)",
    role: "status",
  },
  error: {
    code: "ERR",
    label: "Falha no export",
    color: "var(--color-state-err)",
    role: "alert",
  },
  unavailable: {
    code: "N/A",
    label: "Disponível no desktop",
    color: "var(--color-state-warn)",
    role: "status",
  },
};

export function ExportStatusLine({
  status,
  message,
  result,
  outputDir,
  outputDirMissing = false,
  timestamp,
}: Props) {
  const meta = STATUS_META[status];
  const resultPath = result?.file_path ?? result?.output_dir ?? null;

  return (
    <div
      role={meta.role}
      aria-live={meta.role === "status" ? "polite" : undefined}
      className="space-y-2"
      style={{
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
        padding: "8px",
      }}
    >
      <div className="flex min-w-0 items-center gap-2">
        <span
          className="font-mono"
          style={{
            color: meta.color,
            fontSize: "var(--text-2xs)",
            minWidth: 26,
          }}
        >
          {meta.code}
        </span>
        <span
          className="truncate"
          style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}
        >
          {message || meta.label}
        </span>
        {timestamp ? (
          <span
            className="ml-auto shrink-0 font-mono"
            style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
          >
            {timestamp.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
          </span>
        ) : null}
      </div>

      {status === "success" && result ? (
        <div className="space-y-1">
          <p style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", margin: 0 }}>
            Arquivo:{" "}
            <code className="font-mono" title={result.file_name}>
              {result.file_name ?? "workbook.xlsx"}
            </code>
            {typeof result.size_bytes === "number" ? (
              <span style={{ color: "var(--color-text-tertiary)" }}>
                {" "}({formatBytes(result.size_bytes)})
              </span>
            ) : null}
          </p>
          {resultPath ? <OutputPathDisplay path={resultPath} label="Arquivo gerado" /> : null}
        </div>
      ) : null}

      {status === "idle" ? (
        <OutputPathDisplay path={outputDir} missing={outputDirMissing} />
      ) : null}
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}
