import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { ExportStatusLine } from "@/components/export/ExportStatusLine";
import { useExportAction } from "@/components/export/useExportAction";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import {
  companyRefreshProgress,
  fetchCompanyRefreshStatus,
  isActiveCompanyRefresh,
  normalizedTrackingState,
  requestCompanyRefresh,
  type CompanyRefreshStatusResult,
} from "@/lib/api/companyRefresh";
import {
  fetchCompanyInfo,
  type CompanyInfoResult,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { CompanyRefreshStatus, RefreshDispatchResponse } from "@/lib/bridge/types";

const ACTIVE_POLL_MS = 2_000;
const CVM_MIN_YEAR = 2010;

const PERIOD_SCOPE_OPTIONS = [
  { value: "last_3_years", label: "3 years" },
  { value: "last_5_years", label: "5 years" },
  { value: "last_10_years", label: "10 years" },
  { value: "full_history", label: "Full history" },
] as const;

type RefreshAction =
  | { type: "incremental" }
  | { type: "history"; startYear: number; endYear: number };

type Props = {
  cdCvm: number;
  bridgeReady?: boolean;
  latestPeriod?: string | null;
  yearsAvailable?: number | null;
  lastModelUpdatedAt?: string | null;
  className?: string;
};

export function CompanyCommandBar({
  cdCvm,
  bridgeReady: bridgeReadyProp,
  latestPeriod,
  yearsAvailable,
  lastModelUpdatedAt,
  className,
}: Props) {
  const [localBridgeReady, setLocalBridgeReady] = useState(false);
  const bridgeReady = bridgeReadyProp ?? localBridgeReady;
  const queryClient = useQueryClient();
  const wasActiveRef = useRef(false);
  const currentYear = new Date().getFullYear();

  const [periodScope, setPeriodScope] = useState("last_5_years");
  const [showHistory, setShowHistory] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [showExportDetails, setShowExportDetails] = useState(false);
  const [startYear, setStartYear] = useState(currentYear - 4);
  const [endYear, setEndYear] = useState(currentYear);
  const [yearError, setYearError] = useState<string | null>(null);

  useEffect(() => {
    if (bridgeReadyProp !== undefined) return;
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setLocalBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [bridgeReadyProp]);

  const infoQuery = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled:
      bridgeReady &&
      Number.isFinite(cdCvm) &&
      cdCvm > 0 &&
      (latestPeriod === undefined ||
        yearsAvailable === undefined ||
        lastModelUpdatedAt === undefined),
  });

  const info = infoQuery.data?.mode === "desktop" ? infoQuery.data.info : null;
  const statusQuery = useQuery<CompanyRefreshStatusResult>({
    queryKey: ["company-refresh-status", cdCvm],
    queryFn: () => fetchCompanyRefreshStatus(cdCvm),
    enabled: bridgeReady,
    refetchInterval: (query) => {
      const status =
        query.state.data?.mode === "desktop" ? query.state.data.status : null;
      return isActiveCompanyRefresh(status) ? ACTIVE_POLL_MS : false;
    },
  });

  const status =
    statusQuery.data?.mode === "desktop" ? statusQuery.data.status : null;
  const isActive = isActiveCompanyRefresh(status);

  useEffect(() => {
    if (!bridgeReady) return;
    const wasActive = wasActiveRef.current;
    wasActiveRef.current = isActive;
    if (!wasActive || isActive || statusQuery.isFetching) return;
    invalidateCompanyData(queryClient, cdCvm);
  }, [bridgeReady, cdCvm, isActive, queryClient, statusQuery.isFetching]);

  const refreshMutation = useMutation<RefreshDispatchResponse, Error, RefreshAction>({
    mutationFn: (action) => {
      if (action.type === "incremental") {
        return requestCompanyRefresh(cdCvm, {
          startYear: currentYear - 1,
          endYear: currentYear,
        });
      }
      return requestCompanyRefresh(cdCvm, {
        startYear: action.startYear,
        endYear: action.endYear,
      });
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({
        queryKey: ["company-refresh-status", cdCvm],
      });
      if (!result.job_id || result.status === "already_current") {
        invalidateCompanyData(queryClient, cdCvm);
      }
    },
  });

  const exportAction = useExportAction({ cdCvm, periodScope });
  const browserReason =
    statusQuery.data?.mode === "browser" ? statusQuery.data.reason : null;
  const latestPeriodLabel =
    latestPeriod ??
    info?.latest_financial_period_display ??
    (status?.latest_readable_year != null ? `FY${status.latest_readable_year}` : null);
  const coverageYears =
    yearsAvailable ?? info?.readable_years_count ?? status?.readable_years_count ?? null;
  const lastRefreshAt =
    status?.last_success_at ??
    status?.read_model_updated_at ??
    lastModelUpdatedAt ??
    info?.read_model_updated_at ??
    null;
  const refreshState =
    !bridgeReady || statusQuery.isLoading ? "loading" : normalizedTrackingState(status);
  const hasRefreshError =
    statusQuery.isError ||
    refreshMutation.isError ||
    Boolean(status?.last_error) ||
    refreshState === "error" ||
    refreshState === "stalled";
  const needsAttention =
    Boolean(browserReason) ||
    hasRefreshError ||
    (!latestPeriodLabel && !status?.has_readable_current_data);
  const updateDisabled =
    !bridgeReady || Boolean(browserReason) || isActive || refreshMutation.isPending;
  const pendingIncremental =
    refreshMutation.isPending && refreshMutation.variables?.type === "incremental";
  const pendingHistory =
    refreshMutation.isPending && refreshMutation.variables?.type === "history";
  const progress = companyRefreshProgress(status);
  const historyId = `company-command-history-${cdCvm}`;
  const detailsId = `company-command-details-${cdCvm}`;
  const exportDetailsId = `company-command-export-${cdCvm}`;
  const statusText = buildStatusText({
    browserReason: Boolean(browserReason),
    hasRefreshError,
    isActive,
    latestPeriodLabel,
    loading: refreshState === "loading",
    lastRefreshAt,
    coverageYears,
    status,
  });

  function validateYears(): boolean {
    if (!Number.isFinite(startYear) || startYear < CVM_MIN_YEAR) {
      setYearError(`Minimum start year: ${CVM_MIN_YEAR}.`);
      return false;
    }
    if (!Number.isFinite(endYear) || endYear > currentYear) {
      setYearError(`Maximum end year: ${currentYear}.`);
      return false;
    }
    if (startYear > endYear) {
      setYearError("Start year must be less than or equal to end year.");
      return false;
    }
    setYearError(null);
    return true;
  }

  function applyPreset(preset: "3y" | "5y" | "10y" | "full") {
    const end = currentYear;
    const start =
      preset === "3y"
        ? end - 2
        : preset === "5y"
          ? end - 4
          : preset === "10y"
            ? end - 9
            : CVM_MIN_YEAR;
    setStartYear(start);
    setEndYear(end);
    setYearError(null);
  }

  return (
    <section className={className} aria-label="Company command bar" style={barStyle(needsAttention)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <StatusDot tone={hasRefreshError ? "error" : needsAttention ? "warn" : "ok"} />
          <p
            role={isActive ? "status" : undefined}
            className="min-w-0 truncate font-mono"
            style={{
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-xs)",
              margin: 0,
            }}
            title={statusText}
          >
            {statusText}
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            variant={hasRefreshError || !latestPeriodLabel ? "danger" : "secondary"}
            size="xs"
            disabled={updateDisabled}
            loading={pendingIncremental}
            onClick={() => refreshMutation.mutate({ type: "incremental" })}
          >
            {hasRefreshError ? "Retry update" : "Update data"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            aria-expanded={showHistory}
            aria-controls={historyId}
            onClick={() => setShowHistory((value) => !value)}
          >
            More
          </Button>
          <label
            className="flex items-center gap-1"
            style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)" }}
          >
            <span>History</span>
            <Select
              block={false}
              value={periodScope}
              onChange={(event) => setPeriodScope(event.target.value)}
              style={{ fontSize: "var(--text-xs)", height: 22, padding: "1px 22px 1px 7px" }}
            >
              {PERIOD_SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </label>
          <Button
            variant="primary"
            size="xs"
            disabled={!exportAction.isDesktop || exportAction.isRunning}
            loading={exportAction.isRunning}
            onClick={() => exportAction.run()}
          >
            {exportAction.isRunning ? "Exporting" : "Export Excel"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            aria-expanded={showExportDetails}
            aria-controls={exportDetailsId}
            onClick={() => setShowExportDetails((value) => !value)}
          >
            Export details
          </Button>
        </div>
      </div>

      {isActive ? <ActiveProgress status={status} progress={progress} isFetching={statusQuery.isFetching} /> : null}

      {browserReason || statusQuery.isError || refreshMutation.isError || refreshMutation.data ? (
        <div className="mt-2">
          {browserReason ? <Notice tone="warning">{browserReason}</Notice> : null}
          {statusQuery.isError ? <ErrorNotice error={statusQuery.error} /> : null}
          {refreshMutation.isError ? <ErrorNotice error={refreshMutation.error} /> : null}
          {refreshMutation.data ? <DispatchNotice result={refreshMutation.data} /> : null}
        </div>
      ) : null}

      {showHistory ? (
        <div id={historyId} className="mt-2" style={disclosureStyle}>
          <div className="flex flex-wrap items-end gap-2">
            {(["3y", "5y", "10y", "full"] as const).map((preset) => (
              <PresetButton key={preset} onSelect={() => applyPreset(preset)}>
                {preset === "full" ? "Full history" : `Last ${preset === "3y" ? 3 : preset === "5y" ? 5 : 10} years`}
              </PresetButton>
            ))}
            <YearInput
              id={`command-start-year-${cdCvm}`}
              label="Start year"
              value={startYear}
              min={CVM_MIN_YEAR}
              max={currentYear}
              hasError={Boolean(yearError)}
              onChange={(value) => {
                setStartYear(value);
                setYearError(null);
              }}
            />
            <YearInput
              id={`command-end-year-${cdCvm}`}
              label="End year"
              value={endYear}
              min={CVM_MIN_YEAR}
              max={currentYear}
              hasError={Boolean(yearError)}
              onChange={(value) => {
                setEndYear(value);
                setYearError(null);
              }}
            />
            <Button
              variant="secondary"
              size="xs"
              disabled={updateDisabled}
              loading={pendingHistory}
              onClick={() => {
                if (!validateYears()) return;
                refreshMutation.mutate({ type: "history", startYear, endYear });
              }}
            >
              {pendingHistory ? `Downloading ${startYear}-${endYear}...` : "Download selected history"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              aria-expanded={showDetails}
              aria-controls={detailsId}
              onClick={() => setShowDetails((value) => !value)}
            >
              Refresh details
            </Button>
          </div>
          {yearError ? <p role="alert" style={errorTextStyle}>{yearError}</p> : null}
          {showDetails ? (
            <div id={detailsId} className="mt-2">
              <StatusDetails status={status} loading={refreshState === "loading"} isFetching={statusQuery.isFetching} />
            </div>
          ) : null}
        </div>
      ) : null}

      {showExportDetails ? (
        <div id={exportDetailsId} className="mt-2" style={disclosureStyle}>
          <ExportStatusLine
            status={exportAction.status}
            message={exportStatusMessage(exportAction.status, exportAction.errorMessage)}
            result={exportAction.result}
            outputDir={exportAction.outputDir}
            outputDirMissing={exportAction.outputDirMissing}
            timestamp={exportAction.lastRunAt}
          />
        </div>
      ) : exportAction.status === "success" || exportAction.status === "error" ? (
        <div className="mt-2">
          <Notice tone={exportAction.status === "success" ? "success" : "error"} role={exportAction.status === "success" ? "status" : "alert"}>
            {exportAction.status === "success"
              ? `Workbook exported successfully${exportAction.result?.file_name ? `: ${exportAction.result.file_name}` : "."}`
              : exportAction.errorMessage ?? "Export failed."}
          </Notice>
        </div>
      ) : null}
    </section>
  );
}

function invalidateCompanyData(queryClient: QueryClient, cdCvm: number) {
  void queryClient.invalidateQueries({ queryKey: ["company-info", cdCvm] });
  void queryClient.invalidateQueries({ queryKey: ["company-years", cdCvm] });
  void queryClient.invalidateQueries({ queryKey: ["company-kpis"] });
  void queryClient.invalidateQueries({ queryKey: ["company-statement"] });
  void queryClient.invalidateQueries({ queryKey: ["companies"] });
  void queryClient.invalidateQueries({ queryKey: ["data-coverage"] });
  void queryClient.invalidateQueries({ queryKey: ["db-diagnostics"] });
  void queryClient.invalidateQueries({ queryKey: ["base-health"] });
  void queryClient.invalidateQueries({ queryKey: ["refresh-jobs"] });
  void queryClient.invalidateQueries({ queryKey: ["company-refresh-status"] });
}

function buildStatusText({
  browserReason,
  hasRefreshError,
  isActive,
  latestPeriodLabel,
  loading,
  lastRefreshAt,
  coverageYears,
  status,
}: {
  browserReason: boolean;
  hasRefreshError: boolean;
  isActive: boolean;
  latestPeriodLabel: string | null;
  loading: boolean;
  lastRefreshAt: string | null;
  coverageYears: number | null;
  status: CompanyRefreshStatus | null;
}) {
  if (browserReason) return "Desktop runtime required for local update and export actions";
  if (loading) return "Loading local data status";
  if (isActive) {
    return `Updating company data${status?.progress_message ? ` · ${status.progress_message}` : ""}`;
  }
  if (hasRefreshError) return "Update failed · Existing local data remains available";
  const parts = [latestPeriodLabel ? `Local data current · Through ${latestPeriodLabel}` : "Local data status unavailable"];
  const last = formatDateTime(lastRefreshAt);
  if (last !== "n/a") parts.push(`Refreshed ${last}`);
  if (coverageYears != null) parts.push(`${formatNullable(coverageYears)} years`);
  return parts.join(" · ");
}

function StatusDetails({
  status,
  loading,
  isFetching,
}: {
  status: CompanyRefreshStatus | null;
  loading: boolean;
  isFetching: boolean;
}) {
  if (loading) return <Notice tone="neutral">Loading refresh diagnostics...</Notice>;
  if (!status) return <Notice tone="neutral">No technical refresh details are available yet.</Notice>;
  const progress = companyRefreshProgress(status);
  return (
    <div className="space-y-2">
      <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Last refresh" value={formatDateTime(status.last_success_at ?? null)} />
        <Field label="Last attempt" value={formatDateTime(status.last_attempt_at ?? null)} />
        <Field label="Rows inserted" value={formatNullable(status.last_rows_inserted)} />
        <Field label="Range" value={formatRange(status)} />
        <Field label="Source" value={status.source_label || status.source_scope || "n/a"} />
        <Field label="Job" value={shortJobId(status.job_id)} mono />
        <Field label="State" value={formatStateLabel(normalizedTrackingState(status))} />
        <Field label="Progress" value={progress == null ? "n/a" : `${progress}%`} mono />
      </dl>
      {isFetching && isActiveCompanyRefresh(status) ? <Notice tone="warning">Polling active refresh status...</Notice> : null}
      {status.last_error ? <Notice tone="error">{status.last_error}</Notice> : null}
    </div>
  );
}

function ActiveProgress({
  status,
  progress,
  isFetching,
}: {
  status: CompanyRefreshStatus | null;
  progress: number | null;
  isFetching: boolean;
}) {
  return (
    <div className="mt-2">
      <div
        className="mb-1 flex justify-between gap-3 font-mono"
        style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
      >
        <span>{status?.progress_message || formatStage(status?.stage)}{isFetching ? " · polling" : ""}</span>
        <span>{progress == null ? "working" : `${progress}%`}</span>
      </div>
      <div className="h-1 overflow-hidden" style={{ background: "var(--color-surface-3)", borderRadius: "var(--radius-sm)" }}>
        <div className="h-full transition-all" style={{ background: "var(--color-id-ticker)", width: `${progress ?? 35}%` }} />
      </div>
    </div>
  );
}

function StatusDot({ tone }: { tone: "ok" | "warn" | "error" }) {
  const color =
    tone === "ok"
      ? "var(--color-state-ok)"
      : tone === "error"
        ? "var(--color-state-err)"
        : "var(--color-state-warn)";
  return <span aria-hidden="true" style={{ background: color, borderRadius: 999, height: 7, width: 7, flexShrink: 0 }} />;
}

function PresetButton({ children, onSelect }: { children: ReactNode; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} style={presetButtonStyle}>
      {children}
    </button>
  );
}

function YearInput({
  id,
  label,
  value,
  min,
  max,
  hasError,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  hasError: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div style={{ minWidth: 104 }}>
      <label htmlFor={id} style={{ color: "var(--color-text-tertiary)", display: "block", fontSize: "var(--text-2xs)", marginBottom: 2 }}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number.parseInt(event.target.value, 10))}
        style={{
          background: "var(--color-surface-2)",
          border: `1px solid ${hasError ? "var(--color-state-err)" : "var(--color-border-default)"}`,
          borderRadius: "var(--radius-sm)",
          color: "var(--color-text-primary)",
          fontSize: "var(--text-xs)",
          height: 22,
          padding: "2px 7px",
          width: "100%",
        }}
      />
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)", textTransform: "uppercase" }}>
        {label}
      </dt>
      <dd className={mono ? "mt-0.5 font-mono" : "mt-0.5"} style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", marginLeft: 0 }}>
        {value}
      </dd>
    </div>
  );
}

type NoticeTone = "neutral" | "success" | "warning" | "error";

function Notice({ tone, role, children }: { tone: NoticeTone; role?: "alert" | "status"; children: ReactNode }) {
  return <p role={role} style={noticeStyle(tone)}>{children}</p>;
}

function ErrorNotice({ error }: { error: unknown }) {
  return <Notice tone="error" role="alert">{error instanceof Error ? error.message : String(error)}</Notice>;
}

function DispatchNotice({ result }: { result: RefreshDispatchResponse }) {
  const ok = result.status !== "error";
  return (
    <Notice tone={ok ? "success" : "error"} role={ok ? "status" : "alert"}>
      {result.message || formatStateLabel(result.status)}
      {result.job_id ? <span className="ml-2 font-mono text-xs opacity-80">{shortJobId(result.job_id)}</span> : null}
    </Notice>
  );
}

function exportStatusMessage(status: string, errorMessage: string | null | undefined) {
  if (status === "unavailable") return "Excel export is available in the desktop app.";
  if (status === "running") return "Generating workbook.";
  if (status === "error") return errorMessage ? `Could not export workbook: ${errorMessage}` : "Could not export workbook.";
  return undefined;
}

function barStyle(needsAttention: boolean): CSSProperties {
  return {
    background: "var(--color-surface-2)",
    border: `1px solid ${needsAttention ? "var(--color-state-warn)" : "var(--color-border-subtle)"}`,
    borderRadius: "var(--radius-md)",
    padding: "13px 12px",
  };
}

const disclosureStyle: CSSProperties = {
  background: "var(--color-surface-1)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  padding: 8,
};

const presetButtonStyle: CSSProperties = {
  background: "var(--color-surface-2)",
  border: "1px solid var(--color-border-subtle)",
  borderRadius: "var(--radius-sm)",
  color: "var(--color-text-secondary)",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
  height: 22,
  padding: "2px 7px",
};

const errorTextStyle: CSSProperties = {
  color: "var(--color-state-err)",
  fontSize: "var(--text-xs)",
  margin: "7px 0 0",
};

function noticeStyle(tone: NoticeTone): CSSProperties {
  const color =
    tone === "success"
      ? "var(--color-state-ok)"
      : tone === "warning"
        ? "var(--color-state-warn)"
        : tone === "error"
          ? "var(--color-state-err)"
          : "var(--color-text-secondary)";
  return {
    background: "var(--color-surface-1)",
    border: `1px solid ${tone === "neutral" ? "var(--color-border-subtle)" : color}`,
    borderRadius: "var(--radius-sm)",
    color,
    fontSize: "var(--text-xs)",
    margin: 0,
    padding: "6px 8px",
  };
}

function formatStateLabel(value: string | null | undefined): string {
  const normalized = String(value || "idle");
  if (normalized === "no_data") return "No data";
  if (normalized === "already_current") return "Already current";
  if (normalized === "success") return "Up to date";
  return normalized.replace(/_/g, " ");
}

function formatStage(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ") : "Progress";
}

function formatNullable(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  return value;
}

function formatRange(status: CompanyRefreshStatus): string {
  if (status.last_start_year == null && status.last_end_year == null) return "n/a";
  return `${status.last_start_year ?? "?"}-${status.last_end_year ?? "?"}`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortJobId(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.length > 12 ? `${value.slice(0, 8)}...` : value;
}
