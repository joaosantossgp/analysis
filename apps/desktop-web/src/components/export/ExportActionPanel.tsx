import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { Panel } from "@/components/surface/Panel";

import { ExportScopeBadge } from "./ExportScopeBadge";
import { ExportStatusLine } from "./ExportStatusLine";
import { useExportAction } from "./useExportAction";

type Props = {
  cdCvm: number;
  title?: string;
  description?: ReactNode;
  statementType?: string;
  scopeLabel?: string;
  scopeNote?: ReactNode;
  companyLabel?: ReactNode;
  variant?: "compact" | "full";
  framed?: boolean;
  className?: string;
};

const PERIOD_SCOPE_OPTIONS = [
  { value: "last_3_years",  label: "3 anos" },
  { value: "last_5_years",  label: "5 anos" },
  { value: "last_10_years", label: "10 anos" },
  { value: "full_history",  label: "Todo histórico" },
] as const;

export function ExportActionPanel({
  cdCvm,
  title = "Export workflow",
  description,
  statementType,
  scopeLabel,
  scopeNote,
  companyLabel,
  variant = "compact",
  framed = true,
  className,
}: Props) {
  const [periodScope, setPeriodScope] = useState("last_5_years");
  const action = useExportAction({ cdCvm, statementType, periodScope });
  const finalScopeLabel = scopeLabel ?? (statementType ? `Statement ${statementType}` : "Full Workbook");
  const defaultDescription =
    description ??
    (statementType
      ? "Gera um workbook Excel com capa, metadados e o demonstrativo selecionado."
      : "Gera um workbook Excel com demonstrativos, KPIs e metadados disponíveis.");

  const content = (
    <div className={variant === "full" ? "space-y-4" : "space-y-3"}>
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {companyLabel ? (
            <ExportScopeBadge label="CVM" tone="scope">
              {companyLabel}
            </ExportScopeBadge>
          ) : (
            <ExportScopeBadge label="CVM" tone="scope">
              {cdCvm}
            </ExportScopeBadge>
          )}
          <ExportScopeBadge tone={statementType ? "scope" : "muted"}>
            {finalScopeLabel}
          </ExportScopeBadge>
          <ExportScopeBadge tone="format">Excel</ExportScopeBadge>
          <ExportScopeBadge tone="path">local output</ExportScopeBadge>
        </div>
        <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", margin: 0 }}>
          {defaultDescription}
        </p>
        {scopeNote ? (
          <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)", margin: 0 }}>
            {scopeNote}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size={variant === "full" ? "sm" : "xs"}
          onClick={() => action.run()}
          disabled={!action.isDesktop || action.isRunning}
          loading={action.isRunning}
        >
          {action.isRunning ? "Exportando" : "Exportar Excel"}
        </Button>
        {!statementType && (
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-xs)",
            }}
          >
            <span>Histórico</span>
            <Select
              block={false}
              value={periodScope}
              onChange={(e) => setPeriodScope(e.target.value)}
              style={{ fontSize: "var(--text-xs)", padding: "2px 6px" }}
            >
              {PERIOD_SCOPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </label>
        )}
        <span
          className="font-mono"
          style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
        >
          {statementType ? `scope=${statementType}` : `scope=company period=${periodScope}`}
        </span>
      </div>

      <ExportStatusLine
        status={action.status}
        message={statusMessage(action.status, action.errorMessage, statementType)}
        result={action.result}
        outputDir={action.outputDir}
        outputDirMissing={action.outputDirMissing}
        timestamp={action.lastRunAt}
      />
    </div>
  );

  if (!framed) {
    return (
      <section className={className} aria-label={typeof title === "string" ? title : "Export workflow"}>
        {content}
      </section>
    );
  }

  return (
    <Panel
      dense={variant === "compact"}
      className={className}
      headingLevel={3}
      title={title}
      subtitle={statementType ? `Excel · ${statementType}` : "Excel workbook"}
    >
      {content}
    </Panel>
  );
}

function statusMessage(status: string, errorMessage: string | null | undefined, statementType?: string) {
  if (status === "unavailable") {
    return "Exportação disponível no app desktop com pywebview.";
  }
  if (status === "running") {
    return statementType
      ? `Gerando workbook para ${statementType}.`
      : "Gerando workbook com demonstrativos e KPIs.";
  }
  if (status === "error") {
    return errorMessage ? `Não foi possível gerar o workbook: ${errorMessage}` : "Não foi possível gerar o workbook.";
  }
  return undefined;
}
