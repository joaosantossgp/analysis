import { useState, useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import {
  companyRefreshProgress,
  fetchCompanyRefreshStatus,
  isActiveCompanyRefresh,
  normalizedTrackingState,
  requestCompanyRefresh,
  type CompanyRefreshStatusResult,
} from "@/lib/api/companyRefresh";
import type { CompanyRefreshStatus, RefreshDispatchResponse } from "@/lib/bridge/types";
import { Panel } from "@/components/surface/Panel";

const ACTIVE_POLL_MS = 2_000;
const CVM_MIN_YEAR = 2010;

type RefreshAction =
  | { type: "incremental" }
  | { type: "history"; startYear: number; endYear: number };

type Props = {
  cdCvm: number;
  bridgeReady: boolean;
  className?: string;
};

export function CompanyRefreshPanel({ cdCvm, bridgeReady, className }: Props) {
  const queryClient = useQueryClient();
  const wasActiveRef = useRef(false);
  const currentYear = new Date().getFullYear();

  const [showHistory, setShowHistory] = useState(false);
  const [startYear, setStartYear] = useState(currentYear - 4);
  const [endYear, setEndYear] = useState(currentYear);
  const [yearError, setYearError] = useState<string | null>(null);

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
    mutationFn: (action: RefreshAction) => {
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

  const browserReason =
    statusQuery.data?.mode === "browser" ? statusQuery.data.reason : null;
  const baseDisabled =
    !bridgeReady || Boolean(browserReason) || isActive || refreshMutation.isPending;

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
    let start: number;
    switch (preset) {
      case "3y":
        start = end - 2;
        break;
      case "5y":
        start = end - 4;
        break;
      case "10y":
        start = end - 9;
        break;
      default:
        start = CVM_MIN_YEAR;
    }
    setStartYear(start);
    setEndYear(end);
    setYearError(null);
  }

  const pendingIncremental =
    refreshMutation.isPending && refreshMutation.variables?.type === "incremental";
  const pendingHistory =
    refreshMutation.isPending && refreshMutation.variables?.type === "history";

  return (
    <Panel
      className={className}
      dense
      headingLevel={3}
      title="Company Update"
      subtitle="Download or update this company's data without updating the full database."
      actions={
        <StatusPill status={status} loading={!bridgeReady || statusQuery.isLoading} />
      }
    >
      <div className="space-y-4">
        {browserReason ? <Notice tone="warning">{browserReason}</Notice> : null}
        {statusQuery.isError ? <ErrorNotice error={statusQuery.error} /> : null}
        {refreshMutation.isError ? <ErrorNotice error={refreshMutation.error} /> : null}
        {refreshMutation.data ? (
          <DispatchNotice result={refreshMutation.data} />
        ) : null}

        <StatusBody
          status={status}
          loading={!bridgeReady || statusQuery.isLoading}
          isFetching={statusQuery.isFetching}
        />

        {/* Incremental ITR */}
        <ActionCard>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <ActionTitle>Update New ITRs</ActionTitle>
              <ActionDesc>
                Fetches new quarterly reports and missing recent periods.
              </ActionDesc>
            </div>
            <Button
              variant="primary"
              size="xs"
              disabled={baseDisabled}
              loading={pendingIncremental}
              onClick={() => refreshMutation.mutate({ type: "incremental" })}
            >
              {isActive
                ? "Updating…"
                : pendingIncremental
                  ? "Requesting…"
                  : "Update New ITRs"}
            </Button>
          </div>
        </ActionCard>

        {/* Historical download */}
        <ActionCard>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <ActionTitle>Download History</ActionTitle>
              <ActionDesc>
                Downloads or rebuilds the financial history for the selected range.
              </ActionDesc>
            </div>
            <ToggleButton
              expanded={showHistory}
              onToggle={() => setShowHistory((v) => !v)}
            />
          </div>

          {showHistory ? (
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap gap-1">
                {(["3y", "5y", "10y", "full"] as const).map((preset) => (
                  <PresetButton key={preset} onSelect={() => applyPreset(preset)}>
                    {preset === "full"
                      ? "Full History"
                      : `Last ${preset === "3y" ? 3 : preset === "5y" ? 5 : 10} years`}
                  </PresetButton>
                ))}
              </div>

              <div className="flex items-end gap-2">
                <YearInput
                  id={`start-year-${cdCvm}`}
                  label="Start year"
                  value={startYear}
                  min={CVM_MIN_YEAR}
                  max={currentYear}
                  hasError={Boolean(yearError)}
                  onChange={(v) => {
                    setStartYear(v);
                    setYearError(null);
                  }}
                />
                <span
                  style={{
                    color: "var(--color-text-tertiary)",
                    fontSize: "var(--text-sm)",
                    paddingBottom: 6,
                  }}
                >
                  –
                </span>
                <YearInput
                  id={`end-year-${cdCvm}`}
                  label="End year"
                  value={endYear}
                  min={CVM_MIN_YEAR}
                  max={currentYear}
                  hasError={Boolean(yearError)}
                  onChange={(v) => {
                    setEndYear(v);
                    setYearError(null);
                  }}
                />
              </div>

              {yearError ? (
                <p
                  role="alert"
                  style={{
                    color: "var(--color-state-err)",
                    fontSize: "var(--text-xs)",
                    margin: 0,
                  }}
                >
                  {yearError}
                </p>
              ) : null}

              <Button
                variant="secondary"
                size="xs"
                disabled={baseDisabled}
                loading={pendingHistory}
                onClick={() => {
                  if (!validateYears()) return;
                  refreshMutation.mutate({ type: "history", startYear, endYear });
                }}
              >
                {pendingHistory
                  ? `Downloading ${startYear}–${endYear}…`
                  : "Download selected history"}
              </Button>
            </div>
          ) : null}
        </ActionCard>
      </div>
    </Panel>
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

// ---- Layout helpers ----

function ActionCard({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        background: "var(--color-surface-1)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
        padding: 12,
      }}
    >
      {children}
    </div>
  );
}

function ActionTitle({ children }: { children: ReactNode }) {
  return (
    <p
      style={{
        color: "var(--color-text-primary)",
        fontSize: "var(--text-sm)",
        fontWeight: 500,
        margin: 0,
      }}
    >
      {children}
    </p>
  );
}

function ActionDesc({ children }: { children: ReactNode }) {
  return (
    <p
      style={{
        color: "var(--color-text-tertiary)",
        fontSize: "var(--text-xs)",
        margin: "4px 0 0",
      }}
    >
      {children}
    </p>
  );
}

function ToggleButton({
  expanded,
  onToggle,
}: {
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        background: "transparent",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-sm)",
        color: "var(--color-text-secondary)",
        cursor: "pointer",
        fontSize: "var(--text-xs)",
        flexShrink: 0,
        padding: "4px 10px",
        whiteSpace: "nowrap",
      }}
    >
      {expanded ? "▲ Close" : "▼ Select years"}
    </button>
  );
}

function PresetButton({
  children,
  onSelect,
}: {
  children: ReactNode;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
        color: "var(--color-text-secondary)",
        cursor: "pointer",
        fontSize: "var(--text-xs)",
        padding: "3px 8px",
      }}
    >
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
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex-1">
      <label
        htmlFor={id}
        style={{
          color: "var(--color-text-tertiary)",
          display: "block",
          fontSize: "var(--text-xs)",
          marginBottom: 3,
        }}
      >
        {label}
      </label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number.parseInt(e.target.value, 10))}
        style={{
          background: "var(--color-surface-2)",
          border: `1px solid ${hasError ? "var(--color-state-err)" : "var(--color-border-default)"}`,
          borderRadius: "var(--radius-sm)",
          color: "var(--color-text-primary)",
          fontSize: "var(--text-sm)",
          padding: "5px 8px",
          width: "100%",
        }}
      />
    </div>
  );
}

// ---- Status helpers (kept from original) ----

function StatusPill({
  status,
  loading,
}: {
  status: CompanyRefreshStatus | null;
  loading: boolean;
}) {
  const state = loading ? "loading" : normalizedTrackingState(status);
  const label = formatStateLabel(state);
  const color =
    state === "success" || state === "already_current"
      ? "var(--color-state-ok)"
      : state === "error" || state === "stalled"
        ? "var(--color-state-err)"
        : state === "queued" || state === "running" || state === "loading"
          ? "var(--color-state-warn)"
          : "var(--color-text-tertiary)";
  return (
    <span
      className="font-mono capitalize"
      style={{
        border: `1px solid ${color}`,
        borderRadius: "var(--radius-sm)",
        color,
        fontSize: "var(--text-xs)",
        padding: "2px 7px",
      }}
    >
      {label}
    </span>
  );
}

function StatusBody({
  status,
  loading,
  isFetching,
}: {
  status: CompanyRefreshStatus | null;
  loading: boolean;
  isFetching: boolean;
}) {
  if (loading) {
    return (
      <p
        style={{
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-sm)",
          margin: 0,
        }}
      >
        Loading status…
      </p>
    );
  }
  if (!status) {
    return (
      <p
        style={{
          background: "var(--color-surface-1)",
          border: "1px solid var(--color-border-subtle)",
          borderRadius: "var(--radius-sm)",
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-sm)",
          margin: 0,
          padding: 10,
        }}
      >
        No updates recorded yet. Start an update to fetch data for this company.
      </p>
    );
  }

  const progress = companyRefreshProgress(status);
  const summary =
    status.freshness_summary_message ||
    status.status_reason_message ||
    status.latest_attempt_reason_message ||
    status.read_availability_message ||
    "Update status available.";

  return (
    <div className="space-y-4">
      <p style={summaryStyle(status.freshness_summary_severity)}>
        {summary}
        {isFetching && isActiveCompanyRefresh(status) ? (
          <span className="ml-2" style={{ color: "var(--color-state-warn)" }}>
            Polling…
          </span>
        ) : null}
      </p>

      {progress != null ? (
        <div>
          <div
            className="mb-2 flex justify-between"
            style={{
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-xs)",
            }}
          >
            <span>{status.progress_message || formatStage(status.stage)}</span>
            <span>{progress}%</span>
          </div>
          <div
            className="h-2 overflow-hidden"
            style={{
              background: "var(--color-surface-3)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <div
              className="h-full transition-all"
              style={{
                background: "var(--color-id-ticker)",
                borderRadius: "var(--radius-sm)",
                width: `${progress}%`,
              }}
            />
          </div>
        </div>
      ) : null}

      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Field
          label="Latest year"
          value={formatNullable(status.latest_readable_year)}
        />
        <Field
          label="Readable years"
          value={formatNullable(status.readable_years_count)}
        />
        <Field
          label="Last success"
          value={formatDateTime(status.last_success_at ?? null)}
        />
        <Field
          label="Last attempt"
          value={formatDateTime(status.last_attempt_at ?? null)}
        />
        <Field
          label="Rows inserted"
          value={formatNullable(status.last_rows_inserted)}
        />
        <Field label="Range" value={formatRange(status)} />
        <Field
          label="Source"
          value={status.source_label || status.source_scope || "n/a"}
        />
        <Field label="Job" value={shortJobId(status.job_id)} mono />
      </dl>

      {status.estimated_eta_seconds != null && isActiveCompanyRefresh(status) ? (
        <p
          style={{
            color: "var(--color-text-tertiary)",
            fontSize: "var(--text-xs)",
          }}
        >
          ETA: {formatDuration(status.estimated_eta_seconds)}
          {status.estimate_confidence
            ? ` (${status.estimate_confidence})`
            : ""}
        </p>
      ) : null}

      {status.last_error ? (
        <Notice tone="error">{status.last_error}</Notice>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-xs)",
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </dt>
      <dd
        className={mono ? "mt-1 font-mono" : "mt-1"}
        style={{
          color: "var(--color-text-primary)",
          fontSize: "var(--text-sm)",
        }}
      >
        {value}
      </dd>
    </div>
  );
}

function ErrorNotice({ error }: { error: unknown }) {
  return (
    <Notice tone="error" role="alert">
      {error instanceof Error ? error.message : String(error)}
    </Notice>
  );
}

type NoticeTone = "neutral" | "success" | "warning" | "error";

function Notice({
  tone,
  role,
  children,
}: {
  tone: NoticeTone;
  role?: "alert" | "status";
  children: ReactNode;
}) {
  return (
    <p role={role} style={noticeStyle(tone)}>
      {children}
    </p>
  );
}

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
    fontSize: "var(--text-sm)",
    margin: 0,
    padding: 10,
  };
}

function DispatchNotice({ result }: { result: RefreshDispatchResponse }) {
  const ok = result.status !== "error";
  return (
    <Notice tone={ok ? "success" : "error"}>
      {result.message || formatStateLabel(result.status)}
      {result.job_id ? (
        <span className="ml-2 font-mono text-xs opacity-80">
          {shortJobId(result.job_id)}
        </span>
      ) : null}
    </Notice>
  );
}

function summaryStyle(severity: string | null | undefined): CSSProperties {
  if (severity === "success") return noticeStyle("success");
  if (severity === "warning") return noticeStyle("warning");
  if (severity === "error") return noticeStyle("error");
  return noticeStyle("neutral");
}

function formatStateLabel(value: string | null | undefined): string {
  const normalized = String(value || "idle");
  if (normalized === "no_data") return "No data";
  if (normalized === "already_current") return "Already current";
  if (normalized === "idle") return "Idle";
  if (normalized === "queued") return "Queued";
  if (normalized === "running") return "Running";
  if (normalized === "success") return "Completed";
  if (normalized === "error") return "Error";
  if (normalized === "stalled") return "Stalled";
  if (normalized === "loading") return "Loading";
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
  return `${status.last_start_year ?? "?"}–${status.last_end_year ?? "?"}`;
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

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function shortJobId(value: string | null | undefined): string {
  if (!value) return "n/a";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}
