import { useEffect, useRef } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  companyRefreshProgress,
  fetchCompanyRefreshStatus,
  isActiveCompanyRefresh,
  normalizedTrackingState,
  requestCompanyRefresh,
  type CompanyRefreshStatusResult,
} from "@/lib/api/companyRefresh";
import type { CompanyRefreshStatus, RefreshDispatchResponse } from "@/lib/bridge/types";

const ACTIVE_POLL_MS = 2_000;

type Props = {
  cdCvm: number;
  bridgeReady: boolean;
};

export function CompanyRefreshPanel({ cdCvm, bridgeReady }: Props) {
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
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-zinc-100">Company refresh</h3>
          <p className="mt-1 text-xs text-zinc-500">
            On-demand CVM ingest for this company only.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={status} loading={!bridgeReady || statusQuery.isLoading} />
          <button
            type="button"
            disabled={disabled}
            onClick={() => refreshMutation.mutate()}
            className="rounded-md border border-cyan-800 bg-cyan-950/40 px-3 py-1.5 text-xs font-medium text-cyan-100 hover:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {buttonLabel({
              active: isActive,
              pending: refreshMutation.isPending,
              ready: bridgeReady,
            })}
          </button>
        </div>
      </header>

      <div className="mt-4 space-y-3">
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
    </article>
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
  const className =
    state === "success" || state === "already_current"
      ? "border-emerald-500/30 text-emerald-200"
      : state === "error" || state === "stalled"
        ? "border-rose-500/30 text-rose-200"
        : state === "queued" || state === "running" || state === "loading"
          ? "border-amber-500/30 text-amber-200"
          : "border-zinc-700 text-zinc-400";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs capitalize ${className}`}>
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
    return <p className="text-sm text-zinc-400">Loading refresh status...</p>;
  }
  if (!status) {
    return (
      <p className="rounded border border-zinc-800 bg-zinc-950/50 p-3 text-sm text-zinc-400">
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
      <p className={summaryClass(status.freshness_summary_severity)}>
        {summary}
        {isFetching && isActiveCompanyRefresh(status) ? (
          <span className="ml-2 text-amber-300">Polling...</span>
        ) : null}
      </p>

      {progress != null ? (
        <div>
          <div className="mb-2 flex justify-between text-xs text-zinc-500">
            <span>{status.progress_message || formatStage(status.stage)}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full bg-cyan-400 transition-all"
              style={{ width: `${progress}%` }}
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
        <p className="text-xs text-zinc-500">
          ETA: {formatDuration(status.estimated_eta_seconds)}
          {status.estimate_confidence ? ` (${status.estimate_confidence})` : ""}
        </p>
      ) : null}

      {status.last_error ? (
        <p className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
          {status.last_error}
        </p>
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
      <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className={mono ? "mt-1 font-mono text-sm text-zinc-100" : "mt-1 text-sm text-zinc-100"}>
        {value}
      </dd>
    </div>
  );
}

function BrowserNotice({ reason }: { reason: string }) {
  return (
    <p className="rounded border border-amber-900/60 bg-amber-950/30 p-3 text-sm text-amber-200">
      {reason}
    </p>
  );
}

function ErrorNotice({ error }: { error: unknown }) {
  return (
    <p role="alert" className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

function DispatchNotice({ result }: { result: RefreshDispatchResponse }) {
  const ok = result.status !== "error";
  return (
    <p
      className={
        ok
          ? "rounded border border-emerald-900/60 bg-emerald-950/30 p-3 text-sm text-emerald-200"
          : "rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300"
      }
    >
      {result.message || formatStateLabel(result.status)}
      {result.job_id ? (
        <span className="ml-2 font-mono text-xs opacity-80">
          {shortJobId(result.job_id)}
        </span>
      ) : null}
    </p>
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

function summaryClass(severity: string | null | undefined): string {
  const base = "rounded border p-3 text-sm";
  if (severity === "success") {
    return `${base} border-emerald-900/60 bg-emerald-950/30 text-emerald-200`;
  }
  if (severity === "warning") {
    return `${base} border-amber-900/60 bg-amber-950/30 text-amber-200`;
  }
  if (severity === "error") {
    return `${base} border-rose-900/60 bg-rose-950/40 text-rose-300`;
  }
  return `${base} border-zinc-800 bg-zinc-950/50 text-zinc-300`;
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
