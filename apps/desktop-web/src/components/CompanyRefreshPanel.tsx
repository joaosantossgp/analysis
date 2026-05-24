import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
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

type Props = {
  cdCvm: number;
  bridgeReady: boolean;
  className?: string;
};

export function CompanyRefreshPanel({ cdCvm, bridgeReady, className }: Props) {
  const queryClient = useQueryClient();
  const wasActiveRef = useRef(false);

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

  const refreshMutation = useMutation({
    mutationFn: () => requestCompanyRefresh(cdCvm),
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
  const disabled =
    !bridgeReady || Boolean(browserReason) || isActive || refreshMutation.isPending;

  return (
    <Panel
      className={className}
      dense
      headingLevel={3}
      title="Company refresh"
      subtitle="On-demand CVM ingest for this company only."
      actions={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <StatusPill status={status} loading={!bridgeReady || statusQuery.isLoading} />
          <Button
            variant="primary"
            size="xs"
            disabled={disabled}
            loading={refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
          >
            {buttonLabel({
              active: isActive,
              pending: refreshMutation.isPending,
              ready: bridgeReady,
            })}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        {browserReason ? <BrowserNotice reason={browserReason} /> : null}
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
}

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
      <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)", margin: 0 }}>
        Loading refresh status...
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
        No refresh status recorded yet. Starting a refresh will enqueue the
        standard 2010-current company ingest.
      </p>
    );
  }

  const progress = companyRefreshProgress(status);
  const summary =
    status.freshness_summary_message ||
    status.status_reason_message ||
    status.latest_attempt_reason_message ||
    status.read_availability_message ||
    "Refresh status available.";

  return (
    <div className="space-y-4">
      <p style={summaryStyle(status.freshness_summary_severity)}>
        {summary}
        {isFetching && isActiveCompanyRefresh(status) ? (
          <span className="ml-2" style={{ color: "var(--color-state-warn)" }}>
            Polling...
          </span>
        ) : null}
      </p>

      {progress != null ? (
        <div>
          <div
            className="mb-2 flex justify-between"
            style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}
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
        <Field label="Latest readable year" value={formatNullable(status.latest_readable_year)} />
        <Field label="Readable years" value={formatNullable(status.readable_years_count)} />
        <Field label="Last success" value={formatDateTime(status.last_success_at ?? null)} />
        <Field label="Last attempt" value={formatDateTime(status.last_attempt_at ?? null)} />
        <Field label="Rows inserted" value={formatNullable(status.last_rows_inserted)} />
        <Field label="Range" value={formatRange(status)} />
        <Field label="Source" value={status.source_label || status.source_scope || "n/d"} />
        <Field label="Job" value={shortJobId(status.job_id)} mono />
      </dl>

      {status.estimated_eta_seconds != null && isActiveCompanyRefresh(status) ? (
        <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}>
          ETA: {formatDuration(status.estimated_eta_seconds)}
          {status.estimate_confidence ? ` (${status.estimate_confidence})` : ""}
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

function BrowserNotice({ reason }: { reason: string }) {
  return <Notice tone="warning">{reason}</Notice>;
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

function buttonLabel({
  active,
  pending,
  ready,
}: {
  active: boolean;
  pending: boolean;
  ready: boolean;
}): string {
  if (!ready) return "Waiting for bridge";
  if (pending) return "Requesting...";
  if (active) return "Refresh active";
  return "Refresh company";
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
  return normalized.replace(/_/g, " ");
}

function formatStage(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ") : "Progress";
}

function formatNullable(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "n/d";
  if (typeof value === "number") return new Intl.NumberFormat("pt-BR").format(value);
  return value;
}

function formatRange(status: CompanyRefreshStatus): string {
  if (status.last_start_year == null && status.last_end_year == null) return "n/d";
  return `${status.last_start_year ?? "?"}-${status.last_end_year ?? "?"}`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "n/d";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pt-BR", {
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
  if (!value) return "n/d";
  return value.length > 12 ? `${value.slice(0, 8)}...` : value;
}
