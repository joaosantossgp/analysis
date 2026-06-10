import { useCallback, useEffect, useState } from "react";
import type { DragEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  fetchPlantParcelSourceStatuses,
  triggerPlantParcelRefresh,
  selectPlantParcelImportFile,
  importPlantParcelManualFile,
} from "@/lib/api/energyKpis";
import type {
  PlantParcelManualImportResult,
  PlantParcelSourceStatus,
  PlantParcelSourceStatusResponse,
} from "@/lib/bridge/types";
import { whenBridgeReady } from "@/lib/bridge/adapter";

const MAX_INLINE_DROP_BYTES = 50 * 1024 * 1024;
const CCEE_PLANT_SOURCE_ID_LIST = [
  "ccee_plant_parcel_monthly",
  "ccee_plant_generation_hourly",
] as const;
const CCEE_PLANT_SOURCE_IDS = new Set<string>(CCEE_PLANT_SOURCE_ID_LIST);

function shouldPollPlantJob(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;
  const payload = data as { mode?: string; response?: PlantParcelSourceStatusResponse | null };
  return payload.mode === "desktop" && Boolean(payload.response?.refresh_running);
}

function plantJobKey(status: PlantParcelSourceStatusResponse, fallbackStartedAt: number | null): string {
  return [
    status.refresh_import_id ?? status.refresh_id ?? "plant-job",
    status.refresh_source_id ?? "unknown-source",
    status.refresh_status ?? "unknown-status",
    status.refresh_finished_at ?? status.refresh_updated_at ?? String(fallbackStartedAt ?? ""),
  ].join(":");
}

export function UserImportsPage() {
  const qc = useQueryClient();
  const now = new Date();
  const [bridgeReady, setBridgeReady] = useState(false);
  const [refreshingSourceId, setRefreshingSourceId] = useState<string | null>(null);
  const [refreshStartedAt, setRefreshStartedAt] = useState<number | null>(null);
  const [manualImportingSourceId, setManualImportingSourceId] = useState<string | null>(null);
  const [manualImportStartedAt, setManualImportStartedAt] = useState<number | null>(null);
  const [handledPlantJobKey, setHandledPlantJobKey] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; severity: "success" | "warning" | "error" } | null>(null);
  const [monthlyYear, setMonthlyYear] = useState(String(now.getFullYear()));
  const [hourlyMonth, setHourlyMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const statusQuery = useQuery({
    queryKey: ["plant-parcel-source-statuses", [...CCEE_PLANT_SOURCE_ID_LIST]],
    queryFn: () => fetchPlantParcelSourceStatuses({ source_ids: [...CCEE_PLANT_SOURCE_ID_LIST] }),
    enabled: bridgeReady,
    staleTime: 10_000,
    refetchInterval: (query) =>
      refreshingSourceId || manualImportingSourceId || shouldPollPlantJob(query.state.data) ? 2_000 : false,
    refetchIntervalInBackground: true,
  });

  const statuses = statusQuery.data?.mode === "desktop"
    ? statusQuery.data.statuses.filter((source) => isCceePlantSource(source.source_id))
    : [];
  const statusResponse = statusQuery.data?.mode === "desktop" ? statusQuery.data.response : null;
  const runningBackendSourceId = statusResponse?.refresh_running ? statusResponse.refresh_source_id : null;
  const visibleBackendPlantJobRunning = Boolean(
    statusResponse?.refresh_running && (!runningBackendSourceId || isCceePlantSource(runningBackendSourceId)),
  );
  const effectiveManualImportingSourceId =
    manualImportingSourceId ??
    (statusResponse?.refresh_mode === "manual_file" && runningBackendSourceId && isCceePlantSource(runningBackendSourceId)
      ? runningBackendSourceId
      : null);
  const effectiveRefreshingSourceId =
    refreshingSourceId ??
    (statusResponse?.refresh_mode !== "manual_file" && runningBackendSourceId && isCceePlantSource(runningBackendSourceId)
      ? runningBackendSourceId
      : null);
  const bridgeReason = statusQuery.data?.mode === "browser" ? statusQuery.data.reason : null;

  const refreshVisiblePlantQueries = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["plant-parcel-source-statuses"] });
    void qc.refetchQueries({ queryKey: ["plant-parcel-source-statuses"], type: "active" });
  }, [qc]);

  useEffect(() => {
    if (!refreshingSourceId || !statusResponse) return;
    if (refreshStartedAt !== null && statusQuery.dataUpdatedAt < refreshStartedAt) return;
    if (statusResponse.refresh_source_id && statusResponse.refresh_source_id !== refreshingSourceId) return;
    if (!statusResponse.refresh_source_id && statusResponse.refresh_status === "idle") return;
    if (statusResponse.refresh_running) return;
    const completedKey = plantJobKey(statusResponse, null);
    if (handledPlantJobKey === completedKey) return;
    setHandledPlantJobKey(completedKey);
    setRefreshingSourceId(null);
    setRefreshStartedAt(null);
    if (statusResponse.refresh_error) {
      setMessage({ text: `Refresh finished with an error: ${statusResponse.refresh_error}`, severity: "error" });
    } else if (statusResponse.refresh_warning || statusResponse.refresh_status === "warning") {
      setMessage({
        text: statusResponse.refresh_warning ?? "Refresh completed with a warning. Check the source card for details.",
        severity: "warning",
      });
    } else {
      setMessage({ text: "Refresh finished. Local cache status has been updated.", severity: "success" });
      window.setTimeout(() => setMessage(null), 6000);
    }
    refreshVisiblePlantQueries();
  }, [
    refreshingSourceId,
    refreshStartedAt,
    statusResponse,
    statusQuery.dataUpdatedAt,
    handledPlantJobKey,
    refreshVisiblePlantQueries,
  ]);

  useEffect(() => {
    if (!manualImportingSourceId || !statusResponse || manualImportStartedAt === null) return;
    if (statusQuery.dataUpdatedAt < manualImportStartedAt) return;
    if (statusResponse.refresh_source_id && statusResponse.refresh_source_id !== manualImportingSourceId) return;
    if (statusResponse.refresh_running) {
      setMessage({ text: plantJobProgressText(statusResponse), severity: "success" });
      return;
    }

    const completedKey = plantJobKey(statusResponse, manualImportStartedAt);
    if (handledPlantJobKey === completedKey) return;
    setHandledPlantJobKey(completedKey);
    setManualImportingSourceId(null);
    setManualImportStartedAt(null);
    if (statusResponse.refresh_error) {
      setMessage({ text: `Manual import finished with an error: ${statusResponse.refresh_error}`, severity: "error" });
    } else if (statusResponse.refresh_warning || statusResponse.refresh_status === "warning") {
      setMessage({
        text: statusResponse.refresh_warning ?? "Manual import completed with a warning. Check the source card for details.",
        severity: "warning",
      });
    } else {
      setMessage({ text: "Manual import finished. Local cache status has been updated.", severity: "success" });
      window.setTimeout(() => setMessage(null), 7000);
    }
    refreshVisiblePlantQueries();
  }, [
    manualImportingSourceId,
    manualImportStartedAt,
    statusResponse,
    statusQuery.dataUpdatedAt,
    handledPlantJobKey,
    refreshVisiblePlantQueries,
  ]);

  const refreshSource = useCallback(
    async (source: PlantParcelSourceStatus) => {
      setRefreshingSourceId(source.source_id);
      setRefreshStartedAt(Date.now());
      setHandledPlantJobKey(null);
      setMessage({ text: `Starting refresh for ${source.source_name}...`, severity: "success" });
      try {
        const params =
          source.source_id === "ccee_plant_parcel_monthly"
            ? { source_id: source.source_id, year: Number(monthlyYear) }
            : source.source_id === "ccee_plant_generation_hourly"
              ? { source_id: source.source_id, year_month: hourlyMonth }
              : { source_id: source.source_id };
        const result = await triggerPlantParcelRefresh(params);
        if (result.mode === "browser") {
          setRefreshingSourceId(null);
          setRefreshStartedAt(null);
          setMessage({ text: result.reason, severity: "error" });
          return;
        }
        if (result.result.status === "error" || result.result.status === "failed") {
          setRefreshingSourceId(null);
          setRefreshStartedAt(null);
          setMessage({ text: result.result.error ?? "Refresh failed.", severity: "error" });
          return;
        }
        if (result.result.status === "warning") {
          setRefreshingSourceId(null);
          setRefreshStartedAt(null);
          setMessage({
            text: result.result.warning ?? "Refresh completed with no cached rows.",
            severity: "warning",
          });
          refreshVisiblePlantQueries();
          return;
        }
        if (result.result.status === "success" || result.result.status === "partial") {
          setRefreshingSourceId(null);
          setRefreshStartedAt(null);
          setMessage({
            text: `Refresh completed: ${result.result.rows_inserted ?? 0} rows cached.`,
            severity: "success",
          });
          refreshVisiblePlantQueries();
        } else {
          void statusQuery.refetch();
        }
      } catch (error) {
        setRefreshingSourceId(null);
        setRefreshStartedAt(null);
        setMessage({ text: `Refresh failed: ${String(error)}`, severity: "error" });
      }
    },
    [hourlyMonth, monthlyYear, refreshVisiblePlantQueries, statusQuery],
  );

  const importManualFiles = useCallback(
    async (source: PlantParcelSourceStatus, files: ManualImportFile[]) => {
      if (files.length === 0) return;
      setManualImportingSourceId(source.source_id);
      setMessage({
        text: files.length === 1
          ? `Importing ${files[0].fileName ?? source.dataset_name}...`
          : `Importing ${files.length} files for ${source.dataset_name}...`,
        severity: "success",
      });
      try {
        const startedAt = Date.now();
        setHandledPlantJobKey(null);
        setManualImportStartedAt(startedAt);
        const result = await importPlantParcelManualFile({
          source_id: source.source_id,
          expected_period: null,
          files: files.map((file) => ({
            file_path: file.filePath,
            file_content_base64: file.fileContentBase64,
            original_file_name: file.fileName,
          })),
        });
        if (result.mode === "browser") {
          setManualImportingSourceId(null);
          setManualImportStartedAt(null);
          setMessage({ text: result.reason, severity: "error" });
          return;
        }
        if (result.result.status === "started") {
          setMessage({
            text: files.length === 1
              ? `Manual import started for ${files[0].fileName ?? source.dataset_name}. You can keep using the app while it runs.`
              : `Manual import started for ${files.length} files. You can keep using the app while it runs.`,
            severity: "success",
          });
          void statusQuery.refetch();
          return;
        }
        if (result.result.status === "already_running") {
          setManualImportingSourceId(null);
          setManualImportStartedAt(null);
          setMessage({ text: "Another plant source refresh or import is already running.", severity: "warning" });
          void statusQuery.refetch();
          return;
        }
        setManualImportingSourceId(null);
        setManualImportStartedAt(null);
        const severity =
          result.result.status === "failed" || result.result.status === "error"
            ? "error"
            : result.result.status === "warning"
              ? "warning"
              : "success";
        setMessage({
          text: manualImportResultSummary(result.result, files.length),
          severity,
        });
        if (severity === "success") window.setTimeout(() => setMessage(null), 7000);
        refreshVisiblePlantQueries();
      } catch (error) {
        setManualImportingSourceId(null);
        setManualImportStartedAt(null);
        setMessage({ text: `Manual import failed: ${String(error)}`, severity: "error" });
      }
    },
    [refreshVisiblePlantQueries, statusQuery],
  );

  const chooseManualFile = useCallback(
    async (source: PlantParcelSourceStatus) => {
      try {
        const picked = await selectPlantParcelImportFile(source.source_id);
        if (picked.mode === "browser") {
          setMessage({ text: picked.reason, severity: "error" });
          return;
        }
        if (picked.result.canceled) return;
        const paths = picked.result.file_paths?.length
          ? picked.result.file_paths
          : picked.result.file_path
            ? [picked.result.file_path]
            : [];
        if (!picked.result.ok || paths.length === 0) {
          setMessage({ text: picked.result.error ?? "No file selected.", severity: "error" });
          return;
        }
        await importManualFiles(
          source,
          paths.map((filePath, index) => ({
            filePath,
            fileName: picked.result.file_names?.[index] ?? (paths.length === 1 ? picked.result.file_name ?? undefined : fileNameFromPath(filePath)),
          })),
        );
      } catch (error) {
        setMessage({ text: `File selection failed: ${String(error)}`, severity: "error" });
      }
    },
    [importManualFiles],
  );

  const dropManualFiles = useCallback(
    async (source: PlantParcelSourceStatus, files: File[]) => {
      if (files.length === 0) return;
      try {
        const importFiles: ManualImportFile[] = [];
        for (const file of files) {
          const fileWithPath = file as File & { path?: string; mozFullPath?: string };
          const path = fileWithPath.path || fileWithPath.mozFullPath;
          if (path) {
            importFiles.push({ filePath: path, fileName: file.name, fileSize: file.size });
            continue;
          }
          if (file.size > MAX_INLINE_DROP_BYTES) {
            setMessage({
              text: `${file.name} is too large for drag-and-drop transfer. Use Choose files so the backend can stream it from disk.`,
              severity: "warning",
            });
            return;
          }
          importFiles.push({
            fileContentBase64: await fileToBase64(file),
            fileName: file.name,
            fileSize: file.size,
          });
        }
        await importManualFiles(source, importFiles);
      } catch (error) {
        setMessage({ text: `Could not read dropped file: ${String(error)}`, severity: "error" });
      }
    },
    [importManualFiles],
  );

  if (bridgeReason) {
    return (
      <section className="space-y-5">
        <PageHeader
          title="User Imports"
          subtitle="Manual file imports and data refresh for external energy databases."
          breadcrumbs={[{ label: "Settings", to: "/settings" }, { label: "User Imports" }]}
        />
        <StateBanner variant="browser-only" message={bridgeReason} />
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <PageHeader
        title="User Imports"
        subtitle="Manual file imports and data refresh for CCEE Plant Parcels and energy databases."
        breadcrumbs={[{ label: "Settings", to: "/settings" }, { label: "User Imports" }]}
      />

      <div className="space-y-4">
        {message ? <RefreshMessage message={message} onDismiss={() => setMessage(null)} /> : null}
        {visibleBackendPlantJobRunning && statusResponse ? <PlantJobProgressBanner status={statusResponse} /> : null}

        <SourceStatusGrid
          statuses={statuses}
          loading={statusQuery.isLoading}
          error={statusQuery.error}
          onRetry={() => {
            void statusQuery.refetch();
          }}
          refreshingSourceId={effectiveRefreshingSourceId}
          monthlyYear={monthlyYear}
          onMonthlyYearChange={setMonthlyYear}
          hourlyMonth={hourlyMonth}
          onHourlyMonthChange={setHourlyMonth}
          onRefresh={refreshSource}
          manualImportingSourceId={effectiveManualImportingSourceId}
          onChooseManualFile={chooseManualFile}
          onDropManualFiles={dropManualFiles}
        />
      </div>
    </section>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

type ManualImportFile = {
  filePath?: string;
  fileContentBase64?: string;
  fileName?: string;
  fileSize?: number;
};

function SourceStatusGrid({
  statuses,
  loading,
  error,
  onRetry,
  refreshingSourceId,
  monthlyYear,
  onMonthlyYearChange,
  hourlyMonth,
  onHourlyMonthChange,
  onRefresh,
  manualImportingSourceId,
  onChooseManualFile,
  onDropManualFiles,
}: {
  statuses: PlantParcelSourceStatus[];
  loading: boolean;
  error: unknown;
  onRetry: () => void;
  refreshingSourceId: string | null;
  monthlyYear: string;
  onMonthlyYearChange: (value: string) => void;
  hourlyMonth: string;
  onHourlyMonthChange: (value: string) => void;
  onRefresh: (source: PlantParcelSourceStatus) => void;
  manualImportingSourceId: string | null;
  onChooseManualFile: (source: PlantParcelSourceStatus) => void;
  onDropManualFiles: (source: PlantParcelSourceStatus, files: File[]) => void;
}) {
  if (loading) {
    return <StateBanner variant="loading" title="Loading plant parcel source status..." />;
  }
  if (error) {
    return (
      <StateBanner
        variant="error"
        title="Could not load plant parcel source status"
        message={error instanceof Error ? error.message : String(error)}
        onRetry={onRetry}
      />
    );
  }
  if (statuses.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No CCEE plant source metadata"
        message="No CCEE plant source metadata is available in the local energy source catalog."
      />
    );
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {statuses.map((source) => (
        <div
          key={source.source_id}
          className="rounded-md border border-zinc-850 bg-zinc-900/40 p-4 space-y-4 shadow-lg"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-zinc-500">{source.provider}</p>
              <h3 className="text-sm font-semibold text-zinc-100">{source.source_name}</h3>
              <p className="mt-1 text-xs text-zinc-500">{source.granularity}</p>
            </div>
            <StatusPill status={source.cache_status} />
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Meta label="Rows" value={formatInteger(source.local_records_count)} />
            <Meta label="Latest ref" value={source.latest_reference ?? "—"} mono />
            <Meta label="Last refresh" value={formatDateTime(source.last_refresh_at)} mono />
            <Meta label="Dataset" value={source.dataset_name} mono />
            <Meta label="Last status" value={statusLabel(source.last_status ?? source.cache_status)} mono />
            <Meta label="Imported" value={formatNullableInteger(source.last_rows_inserted ?? source.local_records_count)} mono />
          </div>
          <RefreshDiagnostics source={source} />
          {source.source_id === "ccee_plant_parcel_monthly" ? (
            <label className="block text-[11px] text-zinc-500">
              Refresh Year
              <Input
                aria-label="CCEE monthly refresh year"
                mono
                value={monthlyYear}
                onChange={(event) => onMonthlyYearChange(event.target.value)}
                style={{ height: 28, fontSize: "var(--text-sm)", marginTop: 4 }}
              />
            </label>
          ) : null}
          {source.source_id === "ccee_plant_generation_hourly" ? (
            <label className="block text-[11px] text-zinc-500">
              Refresh Month
              <Input
                aria-label="CCEE hourly refresh month"
                type="month"
                mono
                value={hourlyMonth}
                onChange={(event) => onHourlyMonthChange(event.target.value)}
                style={{ height: 28, fontSize: "var(--text-sm)", marginTop: 4 }}
              />
            </label>
          ) : null}
          <Button
            size="sm"
            loading={refreshingSourceId === source.source_id}
            disabled={!!refreshingSourceId || !!manualImportingSourceId}
            onClick={() => onRefresh(source)}
            block
          >
            {refreshingSourceId === source.source_id ? "Refreshing" : "Refresh source"}
          </Button>
          {isCceeManualSource(source.source_id) ? (
            <ManualImportSection
              source={source}
              importing={manualImportingSourceId === source.source_id}
              disabled={!!refreshingSourceId || !!manualImportingSourceId}
              onChooseFile={() => onChooseManualFile(source)}
              onDropFiles={(files) => onDropManualFiles(source, files)}
            />
          ) : null}
          {source.last_error ? (
            <p className="text-xs text-red-300">{source.last_error}</p>
          ) : null}
          {source.last_warning ? (
            <p className="text-xs text-amber-300">{source.last_warning}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function PlantJobProgressBanner({ status }: { status: PlantParcelSourceStatusResponse }) {
  const label = status.refresh_mode === "manual_file" ? "Manual import" : "Source refresh";
  const progress =
    status.refresh_total_files && status.refresh_current_file_index
      ? `${status.refresh_current_file_index}/${status.refresh_total_files}`
      : "running";
  const fileName = status.refresh_current_file_name ? ` · ${status.refresh_current_file_name}` : "";
  return (
    <div className="rounded-md border border-sky-500/30 bg-sky-500/8 px-3 py-2 text-xs text-sky-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{label} in progress</span>
        <span className="font-mono text-sky-200">{progress}</span>
      </div>
      <p className="mt-1 truncate font-mono text-sky-200/80" title={status.refresh_current_file_name ?? undefined}>
        {status.refresh_source_id ?? "plant source"}{fileName}
      </p>
      <div className="mt-1 flex flex-wrap gap-3 font-mono text-[11px] text-sky-200/70">
        <span>cached {formatNullableInteger(status.refresh_rows_inserted)}</span>
        <span>skipped {formatNullableInteger(status.refresh_rows_skipped)}</span>
        <span>updated {formatDateTime(status.refresh_updated_at ?? status.refresh_started_at ?? null)}</span>
      </div>
    </div>
  );
}

function ManualImportSection({
  source,
  importing,
  disabled,
  onChooseFile,
  onDropFiles,
}: {
  source: PlantParcelSourceStatus;
  importing: boolean;
  disabled: boolean;
  onChooseFile: () => void;
  onDropFiles: (files: File[]) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const copyLink = async () => {
    const url = source.source_page_url ?? source.official_url;
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      window.prompt("Copy CCEE dataset link", url);
    }
  };
  const openPage = () => {
    const url = source.source_page_url ?? source.official_url;
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) onDropFiles(files);
  };
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/35 p-3 text-xs space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium text-zinc-200">Manual import fallback</p>
          <p className="mt-1 text-zinc-500">{manualImportDescription(source.source_id)}</p>
        </div>
        {source.last_import_mode === "manual_file" ? (
          <span className="rounded border border-zinc-800 px-1.5 py-0.5 font-mono text-[10px] text-emerald-300">
            manual
          </span>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Button size="xs" variant="ghost" onClick={openPage} disabled={!source.official_url || disabled}>
          Open CCEE dataset page
        </Button>
        <Button size="xs" variant="ghost" onClick={() => void copyLink()} disabled={!source.official_url || disabled}>
          Copy dataset link
        </Button>
      </div>
      <div
        role="button"
        tabIndex={0}
        className={`rounded border border-dashed px-3 py-4 text-center transition-colors ${
          dragging ? "border-amber-400 bg-amber-400/10" : "border-zinc-700 bg-zinc-950/40"
        }`}
        onDragEnter={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onKeyDown={(event) => {
          if ((event.key === "Enter" || event.key === " ") && !disabled) onChooseFile();
        }}
        aria-disabled={disabled}
      >
        <p className="font-mono text-[11px] text-zinc-300">
          {importing ? "Importing files..." : manualDropLabel(source.source_id)}
        </p>
        <p className="mt-1 text-[11px] text-zinc-655 text-zinc-500">{manualAcceptedTypes(source.source_id)}</p>
      </div>
      <Button
        size="xs"
        loading={importing}
        disabled={disabled}
        onClick={onChooseFile}
        block
      >
        {importing ? "Importing" : "Choose files"}
      </Button>
      <ManualImportDiagnostics source={source} />
    </div>
  );
}

function ManualImportDiagnostics({ source }: { source: PlantParcelSourceStatus }) {
  if (!source.last_manual_import_at && !source.last_manual_file_name) return null;
  const hash = source.last_manual_file_hash ? `${source.last_manual_file_hash.slice(0, 12)}...` : "—";
  return (
    <div className="mt-2 rounded border border-zinc-800 bg-zinc-950/45 px-2 py-1.5 text-[11px] text-zinc-500">
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
        <span>manual {statusLabel(source.last_manual_status)}</span>
        <span>{formatDateTime(source.last_manual_import_at ?? null)}</span>
        <span className="truncate" title={source.last_manual_file_name ?? undefined}>
          file {source.last_manual_file_name ?? "—"}
        </span>
        <span>type {source.last_manual_file_type ?? "—"}</span>
        <span>period {source.last_manual_detected_period ?? "—"}</span>
        <span>size {formatBytes(source.last_manual_file_size_bytes)}</span>
        <span>cached {formatNullableInteger(source.last_manual_rows_inserted)}</span>
        <span>skipped {formatNullableInteger(source.last_manual_rows_skipped)}</span>
      </div>
      <p className="mt-1 truncate font-mono text-zinc-600" title={source.last_manual_file_hash ?? undefined}>
        hash {hash}
      </p>
      {source.last_manual_error ? <p className="mt-1 text-red-300">{source.last_manual_error}</p> : null}
      {source.last_manual_warning ? <p className="mt-1 text-amber-300">{source.last_manual_warning}</p> : null}
    </div>
  );
}

function RefreshMessage({
  message,
  onDismiss,
}: {
  message: { text: string; severity: "success" | "warning" | "error" };
  onDismiss: () => void;
}) {
  const isError = message.severity === "error";
  const isWarning = message.severity === "warning";
  return (
    <div
      className="flex items-center gap-2 rounded-md border p-3 text-sm"
      style={{
        borderColor: isError
          ? "var(--color-state-err)"
          : isWarning
            ? "var(--color-state-warn)"
            : "var(--color-border-subtle)",
        background: "var(--color-surface-2)",
      }}
    >
      <span className={isError ? "text-red-300" : isWarning ? "text-amber-300" : "text-emerald-400"}>
        {isError ? "error" : isWarning ? "warning" : "ok"}
      </span>
      <span className="text-zinc-300">{message.text}</span>
      <button type="button" className="ml-auto text-xs text-zinc-500" onClick={onDismiss}>
        dismiss
      </button>
    </div>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-zinc-655 text-zinc-500">{label}</p>
      <p className={`truncate text-xs text-zinc-300 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const color = status === "failed" ? "text-red-355 text-red-400" : status === "missing" || status === "never_refreshed" || status === "warning" || status === "stale" ? "text-amber-333 text-amber-400" : "text-emerald-333 text-emerald-400";
  return (
    <span className={`rounded border border-zinc-800 px-2 py-1 font-mono text-[11px] ${color}`}>
      {statusLabel(status)}
    </span>
  );
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 2,
  }).format(value);
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatNullableInteger(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return formatInteger(value);
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${formatInteger(value)} B`;
  if (value < 1024 * 1024) return `${formatNumber(value / 1024)} KB`;
  return `${formatNumber(value / (1024 * 1024))} MB`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return status.replaceAll("_", " ");
}

function isCceePlantSource(sourceId: string): boolean {
  return CCEE_PLANT_SOURCE_IDS.has(sourceId);
}

function isCceeManualSource(sourceId: string): boolean {
  return isCceePlantSource(sourceId);
}

function manualImportDescription(sourceId: string): string {
  if (sourceId === "ccee_plant_generation_hourly") {
    return "Download monthly GZIP files from Dados Abertos CCEE and drop them here. Import only the months needed for analysis; hourly files can be large.";
  }
  return "If the CCEE API is unavailable, download annual CSV files from Dados Abertos CCEE and drop them here. The app will validate, parse, and cache each file locally.";
}

function manualDropLabel(sourceId: string): string {
  if (sourceId === "ccee_plant_generation_hourly") return "Drop one or more geracao_horaria_usina_YYYYMM GZIP files here";
  return "Drop one or more parcela_usina_montante_mensal_YYYY CSV files here";
}

function manualAcceptedTypes(sourceId: string): string {
  if (sourceId === "ccee_plant_generation_hourly") return "Accepted: .gz, .gzip, or .csv";
  return "Accepted: .csv";
}

function manualImportResultSummary(result: PlantParcelManualImportResult, fileCount: number): string {
  const periodText = result.detected_period ? ` (${result.detected_period})` : "";
  const fileText = fileCount === 1 ? "1 file" : `${fileCount} files`;
  const rowsText = `${formatInteger(result.rows_inserted ?? 0)} rows cached, ${formatInteger(result.rows_skipped ?? 0)} skipped`;
  if (result.status === "failed" || result.status === "error") {
    return `Manual import failed for ${fileText}${periodText}: ${result.error ?? "failed"}`;
  }
  if (result.status === "warning") {
    return `Manual import completed with warning for ${fileText}${periodText}: ${rowsText}. ${result.warning ?? ""}`.trim();
  }
  return `Manual import completed for ${fileText}${periodText}: ${rowsText}.`;
}

function plantJobProgressText(status: PlantParcelSourceStatusResponse): string {
  const label = status.refresh_current_file_name
    ? `Importing ${status.refresh_current_file_name}`
    : "Manual import is running";
  const progress =
    status.refresh_total_files && status.refresh_current_file_index
      ? ` (${status.refresh_current_file_index}/${status.refresh_total_files})`
      : "";
  const rows = status.refresh_rows_inserted ? ` · ${formatInteger(status.refresh_rows_inserted)} rows cached` : "";
  return `${label}${progress}${rows}. You can keep using the app.`;
}

function fileNameFromPath(filePath: string): string {
  return filePath.split(/[\\/]/).pop() || filePath;
}

async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return window.btoa(binary);
}

function RefreshDiagnostics({ source }: { source: PlantParcelSourceStatus }) {
  const hasDiagnostics =
    source.last_source_rows !== undefined ||
    source.last_parsed_rows !== undefined ||
    source.last_normalized_rows !== undefined ||
    source.last_rows_skipped !== undefined ||
    source.last_downloaded_bytes !== undefined ||
    source.last_requested_period;
  if (!hasDiagnostics) return null;
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/45 px-2 py-1.5 text-[11px] text-zinc-500">
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
        <span>period {source.last_requested_period ?? source.last_period_start ?? "—"}</span>
        <span>bytes {formatBytes(source.last_downloaded_bytes)}</span>
        <span>source {formatNullableInteger(source.last_source_rows)}</span>
        <span>parsed {formatNullableInteger(source.last_parsed_rows ?? source.last_normalized_rows)}</span>
        <span>cached {formatNullableInteger(source.last_rows_inserted)}</span>
        <span>skipped {formatNullableInteger(source.last_rows_skipped)}</span>
      </div>
      {source.last_detected_encoding ? (
        <p className="mt-1 font-mono text-zinc-655 text-zinc-600">encoding {source.last_detected_encoding}</p>
      ) : null}
    </div>
  );
}
