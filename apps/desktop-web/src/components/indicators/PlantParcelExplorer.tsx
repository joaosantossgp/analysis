import { useCallback, useEffect, useMemo, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  fetchPlantParcelCatalog,
  fetchPlantParcelDetail,
  fetchPlantParcelSourceStatuses,
  triggerPlantParcelRefresh,
  fetchPlantParcelChartData,
  selectPlantParcelImportFile,
  importPlantParcelManualFile,
} from "@/lib/api/energyKpis";
import type {
  PlantMetric,
  PlantParcelCatalogRecord,
  PlantParcelDetailResponse,
  PlantParcelManualImportResult,
  PlantParcelSourceStatus,
} from "@/lib/bridge/types";
import { IndicatorChart } from "./IndicatorChart";
import type { ChartAesthetics } from "@/lib/indicators/types";

const PAGE_SIZE = 100;
const MAX_INLINE_DROP_BYTES = 50 * 1024 * 1024;

type Filters = {
  entity_type: string;
  generation_source: string;
  submarket: string;
  uf: string;
};

type ManualImportFile = {
  filePath?: string;
  fileContentBase64?: string;
  fileName?: string;
  fileSize?: number;
};

const EMPTY_FILTERS: Filters = {
  entity_type: "",
  generation_source: "",
  submarket: "",
  uf: "",
};

export function PlantParcelExplorer({ bridgeReady }: { bridgeReady: boolean }) {
  const qc = useQueryClient();
  const now = new Date();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<PlantParcelCatalogRecord | null>(null);
  const [refreshingSourceId, setRefreshingSourceId] = useState<string | null>(null);
  const [manualImportingSourceId, setManualImportingSourceId] = useState<string | null>(null);
  const [manualImportStartedAt, setManualImportStartedAt] = useState<number | null>(null);
  const [message, setMessage] = useState<{ text: string; severity: "success" | "warning" | "error" } | null>(null);
  const [monthlyYear, setMonthlyYear] = useState(String(now.getFullYear()));
  const [hourlyMonth, setHourlyMonth] = useState(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
  );

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedSearch, filters.entity_type, filters.generation_source, filters.submarket, filters.uf]);

  const statusQuery = useQuery({
    queryKey: ["plant-parcel-source-statuses"],
    queryFn: fetchPlantParcelSourceStatuses,
    enabled: bridgeReady,
    staleTime: 10_000,
    refetchInterval: refreshingSourceId || manualImportingSourceId ? 2_000 : false,
  });

  const catalogQuery = useQuery({
    queryKey: ["plant-parcel-catalog", debouncedSearch, filters, offset],
    queryFn: () =>
      fetchPlantParcelCatalog({
        search: debouncedSearch || undefined,
        entity_type: filters.entity_type || undefined,
        generation_source: filters.generation_source || undefined,
        submarket: filters.submarket || undefined,
        uf: filters.uf || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    enabled: bridgeReady,
    staleTime: 30_000,
  });

  const records = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.records : [];
  const catalogResponse = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.response : null;
  const total = catalogResponse?.total ?? 0;
  const facets = catalogResponse?.facets ?? {};
  const statuses = statusQuery.data?.mode === "desktop" ? statusQuery.data.statuses : [];
  const statusResponse = statusQuery.data?.mode === "desktop" ? statusQuery.data.response : null;
  const bridgeReason =
    statusQuery.data?.mode === "browser"
      ? statusQuery.data.reason
      : catalogQuery.data?.mode === "browser"
        ? catalogQuery.data.reason
        : null;

  const invalidatePlantQueries = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["plant-parcel-source-statuses"] });
    void qc.invalidateQueries({ queryKey: ["plant-parcel-catalog"] });
    void qc.invalidateQueries({ queryKey: ["plant-parcel-detail"] });
    void qc.invalidateQueries({ queryKey: ["plant-parcel-chart-data"] });
  }, [qc]);

  useEffect(() => {
    if (records.length === 0) {
      setSelected(null);
      return;
    }
    const stillVisible = selected
      ? records.some((row) => row.entity_type === selected.entity_type && row.entity_id === selected.entity_id)
      : false;
    if (!stillVisible) setSelected(records[0]);
  }, [records, selected]);

  useEffect(() => {
    if (!refreshingSourceId || !statusResponse) return;
    if (statusResponse.refresh_running) return;
    setRefreshingSourceId(null);
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
    void qc.invalidateQueries({ queryKey: ["plant-parcel-source-statuses"] });
    void qc.invalidateQueries({ queryKey: ["plant-parcel-catalog"] });
  }, [refreshingSourceId, statusResponse, qc]);

  useEffect(() => {
    if (!manualImportingSourceId || !statusResponse || manualImportStartedAt === null) return;
    if (statusQuery.dataUpdatedAt < manualImportStartedAt) return;
    if (statusResponse.refresh_source_id && statusResponse.refresh_source_id !== manualImportingSourceId) return;
    if (statusResponse.refresh_running) return;

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
    invalidatePlantQueries();
  }, [manualImportingSourceId, manualImportStartedAt, statusResponse, statusQuery.dataUpdatedAt, invalidatePlantQueries]);

  const detailQuery = useQuery({
    queryKey: ["plant-parcel-detail", selected?.entity_type, selected?.entity_id],
    queryFn: () =>
      fetchPlantParcelDetail({
        entity_type: selected?.entity_type,
        entity_id: selected?.entity_id ?? "",
      }),
    enabled: bridgeReady && !!selected,
    staleTime: 30_000,
  });

  const detail = detailQuery.data?.mode === "desktop" ? detailQuery.data.detail : null;

  const refreshSource = useCallback(
    async (source: PlantParcelSourceStatus) => {
      setRefreshingSourceId(source.source_id);
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
          setMessage({ text: result.reason, severity: "error" });
          return;
        }
        if (result.result.status === "error" || result.result.status === "failed") {
          setRefreshingSourceId(null);
          setMessage({ text: result.result.error ?? "Refresh failed.", severity: "error" });
          return;
        }
        if (result.result.status === "warning") {
          setRefreshingSourceId(null);
          setMessage({
            text: result.result.warning ?? "Refresh completed with no cached rows.",
            severity: "warning",
          });
          void qc.invalidateQueries({ queryKey: ["plant-parcel-source-statuses"] });
          void qc.invalidateQueries({ queryKey: ["plant-parcel-catalog"] });
          return;
        }
        if (result.result.status === "success" || result.result.status === "partial") {
          setRefreshingSourceId(null);
          setMessage({
            text: `Refresh completed: ${result.result.rows_inserted ?? 0} rows cached.`,
            severity: "success",
          });
          void qc.invalidateQueries({ queryKey: ["plant-parcel-source-statuses"] });
          void qc.invalidateQueries({ queryKey: ["plant-parcel-catalog"] });
        } else {
          void statusQuery.refetch();
        }
      } catch (error) {
        setRefreshingSourceId(null);
        setMessage({ text: `Refresh failed: ${String(error)}`, severity: "error" });
      }
    },
    [hourlyMonth, monthlyYear, qc, statusQuery],
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
        invalidatePlantQueries();
      } catch (error) {
        setManualImportingSourceId(null);
        setManualImportStartedAt(null);
        setMessage({ text: `Manual import failed: ${String(error)}`, severity: "error" });
      }
    },
    [invalidatePlantQueries, statusQuery],
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

  if (!bridgeReady || statusQuery.isLoading || catalogQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading plant parcel cache..." />;
  }
  if (bridgeReason) {
    return <StateBanner variant="browser-only" message={bridgeReason} />;
  }
  if (statusQuery.isError || catalogQuery.isError) {
    const error = statusQuery.error ?? catalogQuery.error;
    return (
      <StateBanner
        variant="error"
        title="Could not load plant parcel indicators"
        message={error instanceof Error ? error.message : String(error)}
        onRetry={() => {
          void statusQuery.refetch();
          void catalogQuery.refetch();
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {message ? <RefreshMessage message={message} onDismiss={() => setMessage(null)} /> : null}

      <SourceStatusGrid
        statuses={statuses}
        refreshingSourceId={refreshingSourceId}
        monthlyYear={monthlyYear}
        onMonthlyYearChange={setMonthlyYear}
        hourlyMonth={hourlyMonth}
        onHourlyMonthChange={setHourlyMonth}
        onRefresh={refreshSource}
        manualImportingSourceId={manualImportingSourceId}
        onChooseManualFile={chooseManualFile}
        onDropManualFiles={dropManualFiles}
      />

      <div className="grid gap-4 xl:grid-cols-[1.55fr_1fr] items-start">
        <div className="space-y-3 min-w-0">
          <CatalogToolbar
            search={search}
            onSearchChange={setSearch}
            filters={filters}
            onFiltersChange={setFilters}
            facets={facets}
            total={total}
            visible={records.length}
            offset={offset}
          />

          {records.length === 0 ? (
            <StateBanner
              variant="empty"
              title="No plant or parcel matches"
              message={emptyCatalogMessage(statuses)}
            />
          ) : (
            <PlantCatalogTable records={records} selected={selected} onSelect={setSelected} />
          )}

          <Pagination
            total={total}
            offset={offset}
            pageSize={PAGE_SIZE}
            onPrev={() => setOffset((v) => Math.max(0, v - PAGE_SIZE))}
            onNext={() => setOffset((v) => v + PAGE_SIZE)}
          />
        </div>

        <div className="min-w-0 xl:sticky xl:top-4">
          <PlantDetailPanel selected={selected} detail={detail} loading={detailQuery.isLoading} />
        </div>
      </div>
    </div>
  );
}

function SourceStatusGrid({
  statuses,
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
  if (statuses.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No plant source metadata"
        message="The local energy source catalog has not been initialized yet."
      />
    );
  }
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {statuses.map((source) => (
        <div
          key={source.source_id}
          className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 space-y-3"
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
            <Input
              aria-label="CCEE monthly refresh year"
              mono
              value={monthlyYear}
              onChange={(event) => onMonthlyYearChange(event.target.value)}
              style={{ height: 28, fontSize: "var(--text-sm)" }}
            />
          ) : null}
          {source.source_id === "ccee_plant_generation_hourly" ? (
            <Input
              aria-label="CCEE hourly refresh month"
              type="month"
              mono
              value={hourlyMonth}
              onChange={(event) => onHourlyMonthChange(event.target.value)}
              style={{ height: 28, fontSize: "var(--text-sm)" }}
            />
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
    <div className="rounded border border-zinc-800 bg-zinc-900/35 p-2.5 text-xs">
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
      <div className="mt-2 grid grid-cols-2 gap-2">
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
        className={`mt-2 rounded border border-dashed px-3 py-3 text-center transition-colors ${
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
        <p className="mt-1 text-[11px] text-zinc-600">{manualAcceptedTypes(source.source_id)}</p>
      </div>
      <Button
        size="xs"
        loading={importing}
        disabled={disabled}
        onClick={onChooseFile}
        block
        style={{ marginTop: 8 }}
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

function CatalogToolbar({
  search,
  onSearchChange,
  filters,
  onFiltersChange,
  facets,
  total,
  visible,
  offset,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  filters: Filters;
  onFiltersChange: (filters: Filters) => void;
  facets: Record<string, string[]>;
  total: number;
  visible: number;
  offset: number;
}) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 space-y-3">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
        <Input
          aria-label="Search plant parcels"
          placeholder="Search by plant, CEG, parcel code, agent..."
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
        />
        <div className="text-xs text-zinc-500 whitespace-nowrap font-mono">
          {visible} shown · {total} total · offset {offset}
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-4">
        <SelectFilter
          label="Entity"
          value={filters.entity_type}
          options={facets.entity_type ?? []}
          onChange={(value) => onFiltersChange({ ...filters, entity_type: value })}
        />
        <SelectFilter
          label="Source"
          value={filters.generation_source}
          options={facets.generation_source ?? []}
          onChange={(value) => onFiltersChange({ ...filters, generation_source: value })}
        />
        <SelectFilter
          label="Submarket"
          value={filters.submarket}
          options={facets.submarket ?? []}
          onChange={(value) => onFiltersChange({ ...filters, submarket: value })}
        />
        <SelectFilter
          label="UF"
          value={filters.uf}
          options={facets.uf ?? []}
          onChange={(value) => onFiltersChange({ ...filters, uf: value })}
        />
      </div>
      <Button size="xs" variant="ghost" onClick={() => onFiltersChange(EMPTY_FILTERS)}>
        Clear filters
      </Button>
    </div>
  );
}

function PlantCatalogTable({
  records,
  selected,
  onSelect,
}: {
  records: PlantParcelCatalogRecord[];
  selected: PlantParcelCatalogRecord | null;
  onSelect: (record: PlantParcelCatalogRecord) => void;
}) {
  return (
    <div className="overflow-auto rounded-md border border-zinc-800">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-zinc-950 text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <Th>Entity</Th>
            <Th>Plant / Parcel</Th>
            <Th>CEG</Th>
            <Th>Source</Th>
            <Th>Submarket</Th>
            <Th align="right">Capacity</Th>
            <Th align="right">Latest generation</Th>
          </tr>
        </thead>
        <tbody>
          {records.map((row) => {
            const isSelected = selected?.entity_type === row.entity_type && selected?.entity_id === row.entity_id;
            return (
              <tr
                key={`${row.entity_type}:${row.entity_id}`}
                className={`cursor-pointer border-t border-zinc-800 hover:bg-zinc-800/40 ${isSelected ? "bg-zinc-800/60" : ""}`}
                onClick={() => onSelect(row)}
              >
                <Td mono>{entityLabel(row.entity_type)}</Td>
                <Td>
                  <div className="font-medium text-zinc-100">{row.plant_name ?? row.plant_parcel_acronym ?? row.entity_id}</div>
                  <div className="font-mono text-xs text-zinc-500">
                    {row.plant_parcel_code ? `parcel ${row.plant_parcel_code}` : "ANEEL plant"}
                    {row.plant_parcel_acronym ? ` · ${row.plant_parcel_acronym}` : ""}
                  </div>
                </Td>
                <Td mono>{row.ceg ?? "—"}</Td>
                <Td>{row.generation_source ?? "—"}</Td>
                <Td mono>{row.submarket ?? "—"}</Td>
                <Td align="right" mono>{formatMetric(row.capacity_mw ?? row.authorized_capacity_mw, "MW")}</Td>
                <Td align="right" mono>{formatMetric(row.latest_generation_mwmed, "MWmed")}</Td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const CHART_CONFIG: ChartAesthetics = {
  type: "line",
  smooth: true,
  markers: true,
  legend: false,
  grid: true,
  dataLabels: false,
  indexMode: false,
};

function PlantDetailPanel({
  selected,
  detail,
  loading,
}: {
  selected: PlantParcelCatalogRecord | null;
  detail: PlantParcelDetailResponse | null;
  loading: boolean;
}) {
  const [chartFreq, setChartFreq] = useState<"monthly" | "daily" | "hourly">("monthly");
  const [chartMonth, setChartMonth] = useState<string>("");
  const [selectedMetricId, setSelectedMetricId] = useState<string>("all");

  const months = useMemo(() => {
    if (!detail?.monthly_series) return [];
    return detail.monthly_series
      .map((row: any) => row.reference_month)
      .filter((v: string | null | undefined): v is string => typeof v === "string" && !!v)
      .sort()
      .reverse();
  }, [detail]);

  useEffect(() => {
    if (months.length > 0) {
      setChartMonth(months[0]);
    } else {
      setChartMonth("");
    }
  }, [detail?.entity_id, months]);

  const chartQuery = useQuery({
    queryKey: ["plant-parcel-chart-data", detail?.entity_type, detail?.entity_id, chartFreq, chartMonth],
    queryFn: () =>
      fetchPlantParcelChartData({
        entity_type: detail?.entity_type,
        entity_id: detail?.entity_id ?? "",
        frequency: chartFreq,
        year_month: chartFreq !== "monthly" ? chartMonth : undefined,
      }),
    enabled: !!detail?.entity_id && (chartFreq === "monthly" || !!chartMonth),
    staleTime: 30_000,
  });

  if (!selected) {
    return (
      <StateBanner
        variant="empty"
        title="Select a plant or parcel"
        message="The detail panel opens one selected entity at a time and does not render bulk charts."
      />
    );
  }
  if (loading || !detail) {
    return <StateBanner variant="loading" title="Loading selected entity..." />;
  }

  const parcel = detail.parcel ?? {};
  const aneel = detail.aneel_plant ?? {};
  const monthly = detail.monthly_series ?? [];
  const hourly = detail.hourly_preview ?? [];

  const displayedSeries = (() => {
    const rawSeries = chartQuery.data?.mode === "desktop" ? chartQuery.data.data.series : [];
    const colored = rawSeries.map((s, idx) => {
      let color = s.color || "#3B82F6";
      if (!s.color) {
        const colors = ["#22D3EE", "#34D399", "#818CF8", "#FBBF24", "#F87171", "#A78BFA"];
        color = colors[idx % colors.length];
      }
      
      let points = s.points;
      let latest = s.latest;
      const isPct = s.id.endsWith("pct") || s.unit === "pct";
      if (isPct) {
        points = s.points.map(v => v !== null ? v / 100 : null);
        latest = s.latest !== null ? s.latest / 100 : null;
      }
      
      return {
        id: s.id,
        label: s.label,
        unit: s.unit as "pct" | "ratio" | "number",
        color,
        type: (s.type || "line") as "line" | "bar" | "area",
        axis: (s.axis || "left") as "left" | "right",
        points,
        latest,
      };
    });

    if (selectedMetricId === "all") return colored;
    return colored.filter(s => s.id === selectedMetricId);
  })();

  const chartPeriods = chartQuery.data?.mode === "desktop" ? chartQuery.data.data.periods : [];

  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 space-y-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{entityLabel(detail.entity_type)}</p>
        <h3 className="text-base font-semibold text-zinc-100">
          {textValue(parcel, "plant_name") || textValue(aneel, "plant_name") || selected.plant_name || selected.entity_id}
        </h3>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-zinc-500">
          <span className="font-mono">entity {detail.entity_id}</span>
          {textValue(parcel, "plant_parcel_code") ? <span className="font-mono">parcel {textValue(parcel, "plant_parcel_code")}</span> : null}
          {textValue(parcel, "ceg") || textValue(aneel, "ceg") ? <span className="font-mono">CEG {textValue(parcel, "ceg") || textValue(aneel, "ceg")}</span> : null}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {(detail.metrics ?? []).slice(0, 6).map((metric: PlantMetric) => (
          <MetricTile key={metric.metric_id} metric={metric} />
        ))}
      </div>

      {/* Historical Charts */}
      <div className="border-t border-zinc-800 pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">Historical charts</h4>
          
          <div className="flex gap-2">
            <button
              onClick={() => { setChartFreq("monthly"); setSelectedMetricId("all"); }}
              className={`rounded px-2 py-0.5 text-xs font-medium border ${chartFreq === "monthly" ? "bg-zinc-850 text-zinc-100 border-zinc-700" : "bg-transparent text-zinc-500 border-transparent hover:text-zinc-300"}`}
            >
              Monthly
            </button>
            <button
              onClick={() => { setChartFreq("daily"); setSelectedMetricId("all"); }}
              className={`rounded px-2 py-0.5 text-xs font-medium border ${chartFreq === "daily" ? "bg-zinc-850 text-zinc-100 border-zinc-700" : "bg-transparent text-zinc-500 border-transparent hover:text-zinc-300"}`}
              disabled={months.length === 0}
            >
              Daily
            </button>
            <button
              onClick={() => { setChartFreq("hourly"); setSelectedMetricId("all"); }}
              className={`rounded px-2 py-0.5 text-xs font-medium border ${chartFreq === "hourly" ? "bg-zinc-850 text-zinc-100 border-zinc-700" : "bg-transparent text-zinc-500 border-transparent hover:text-zinc-300"}`}
              disabled={months.length === 0}
            >
              Hourly
            </button>
          </div>
        </div>

        {/* Chart Controls */}
        <div className="grid gap-2 grid-cols-2">
          {/* Metric Selector */}
          <label className="text-[11px] text-zinc-500">
            Metric
            <select
              value={selectedMetricId}
              onChange={(e) => setSelectedMetricId(e.target.value)}
              className="mt-1 h-8 w-full rounded border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none"
            >
              <option value="all">All Series</option>
              {(chartQuery.data?.mode === "desktop" ? chartQuery.data.data.series : []).map((s: any) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
          </label>

          {/* Period Selector (Only for daily/hourly) */}
          {chartFreq !== "monthly" ? (
            <label className="text-[11px] text-zinc-500">
              Period
              <select
                value={chartMonth}
                onChange={(e) => setChartMonth(e.target.value)}
                className="mt-1 h-8 w-full rounded border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-100 outline-none font-mono"
              >
                {months.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
          ) : (
            <div className="text-[11px] text-zinc-500 self-end pb-2">
              Showing full monthly history
            </div>
          )}
        </div>

        {/* Chart rendering */}
        <div className="relative border border-zinc-850 rounded-md bg-zinc-950/20 p-2 min-h-[240px] flex flex-col justify-center">
          {chartQuery.isLoading ? (
            <div className="text-center text-xs text-zinc-500 py-12">Loading chart data...</div>
          ) : chartQuery.isError ? (
            <div className="text-center text-xs text-red-400 py-12">
              Error: {chartQuery.error instanceof Error ? chartQuery.error.message : String(chartQuery.error)}
            </div>
          ) : displayedSeries.length === 0 ? (
            <div className="text-center text-xs text-zinc-500 py-12">No data to display. Please refresh the source.</div>
          ) : (
            <div className="space-y-2">
              <IndicatorChart
                series={displayedSeries}
                periods={chartPeriods}
                config={CHART_CONFIG}
                height={220}
              />
              
              {/* Legend */}
              <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center text-[10px] text-zinc-400 font-mono">
                {displayedSeries.map((s) => (
                  <div key={s.id} className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
                    <span>{s.label}:</span>
                    <span className="text-zinc-200">
                      {s.latest !== null ? (s.unit === "pct" ? `${(s.latest * 100).toFixed(1)}%` : s.latest.toLocaleString("en-US", { maximumFractionDigits: 1 })) : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <Meta label="ANEEL phase" value={textValue(aneel, "phase") ?? "—"} />
        <Meta label="Agent" value={textValue(parcel, "agent_name") ?? selected.agent_name ?? "—"} />
        <Meta label="Submarket" value={textValue(parcel, "submarket") ?? selected.submarket ?? "—"} mono />
        <Meta label="UF" value={textValue(parcel, "uf") ?? textValue(aneel, "uf") ?? selected.uf ?? "—"} mono />
      </div>

      <MethodologyList metrics={detail.metrics ?? []} />

      <SeriesPreview
        title="Monthly generation preview"
        rows={monthly.slice(-8)}
        columns={[
          ["reference_month", "Month"],
          ["generation_center_of_gravity_mwmed", "GCG (MWmed)"],
          ["capacity_mw", "Capacity (MW)"],
        ]}
      />

      <SeriesPreview
        title="Hourly preview"
        rows={hourly.slice(-8)}
        columns={[
          ["reference_datetime", "Datetime"],
          ["generation_center_of_gravity_mwh", "GCG (MWh)"],
          ["verified_generation_ons_mwh", "Verified ONS (MWh)"],
        ]}
      />

      <div className="space-y-1">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Caveats</p>
        {(detail.metadata?.caveats ?? []).map((item: string) => (
          <p key={item} className="text-xs text-zinc-400">- {item}</p>
        ))}
      </div>
    </div>
  );
}

function MethodologyList({ metrics }: { metrics: PlantMetric[] }) {
  const shown = metrics.slice(0, 5);
  if (shown.length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="text-xs uppercase tracking-wide text-zinc-500">Metric provenance</p>
      {shown.map((metric) => (
        <div key={`method-${metric.metric_id}`} className="rounded border border-zinc-800 bg-zinc-900/40 p-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-zinc-200">{metric.label}</span>
            <span className="font-mono text-[11px] text-zinc-500">{metric.raw_or_derived}</span>
          </div>
          <p className="mt-1 text-xs text-zinc-500">{metric.methodology}</p>
          <p className="mt-1 font-mono text-[11px] text-zinc-600">
            {metric.dataset} · ref {metric.reference_period ?? "—"} · refresh {formatDateTime(metric.local_refresh_timestamp)}
          </p>
        </div>
      ))}
    </div>
  );
}

function SeriesPreview({
  title,
  rows,
  columns,
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  columns: Array<[string, string]>;
}) {
  if (!rows.length) {
    return (
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <p className="text-xs text-zinc-500">No cached rows for this selected entity.</p>
      </div>
    );
  }
  return (
    <div className="overflow-auto">
      <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <table className="min-w-full text-xs">
        <thead className="text-zinc-500">
          <tr>{columns.map(([, label]) => <Th key={label}>{label}</Th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${title}-${idx}`} className="border-t border-zinc-800">
              {columns.map(([key]) => (
                <Td key={key} mono align={typeof row[key] === "number" ? "right" : "left"}>
                  {typeof row[key] === "number" ? formatNumber(row[key] as number) : String(row[key] ?? "—")}
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricTile({ metric }: { metric: PlantMetric }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3">
      <p className="text-xs text-zinc-500">{metric.label}</p>
      <p className="mt-1 font-mono text-lg text-zinc-100">
        {formatNumber(metric.value)} <span className="text-xs text-zinc-500">{metric.unit}</span>
      </p>
      <p className="mt-1 font-mono text-[11px] text-zinc-600">{metric.reference_period ?? "—"} · {metric.raw_or_derived}</p>
    </div>
  );
}

function SelectFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-xs text-zinc-500">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-8 w-full rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100 outline-none"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

function Pagination({
  total,
  offset,
  pageSize,
  onPrev,
  onNext,
}: {
  total: number;
  offset: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  if (total <= pageSize) return null;
  return (
    <div className="flex items-center justify-between text-xs text-zinc-500">
      <span className="font-mono">{offset + 1}-{Math.min(offset + pageSize, total)} of {total}</span>
      <div className="flex gap-2">
        <Button size="xs" onClick={onPrev} disabled={offset <= 0}>Previous</Button>
        <Button size="xs" onClick={onNext} disabled={offset + pageSize >= total}>Next</Button>
      </div>
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
      <p className="text-[11px] uppercase tracking-wide text-zinc-600">{label}</p>
      <p className={`truncate text-xs text-zinc-300 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const color = status === "failed" ? "text-red-300" : status === "missing" || status === "never_refreshed" || status === "warning" || status === "stale" ? "text-amber-300" : "text-emerald-300";
  return (
    <span className={`rounded border border-zinc-800 px-2 py-1 font-mono text-[11px] ${color}`}>
      {statusLabel(status)}
    </span>
  );
}

function Th({ children, align = "left" }: { children: ReactNode; align?: "left" | "right" }) {
  return <th className="px-3 py-2" style={{ textAlign: align }}>{children}</th>;
}

function Td({
  children,
  align = "left",
  mono = false,
}: {
  children: ReactNode;
  align?: "left" | "right";
  mono?: boolean;
}) {
  return <td className={`px-3 py-2 ${mono ? "font-mono tabular-nums" : ""}`} style={{ textAlign: align }}>{children}</td>;
}

function entityLabel(entityType: string): string {
  if (entityType === "ccee_plant_parcel") return "CCEE parcel";
  if (entityType === "aneel_plant") return "ANEEL plant";
  return entityType;
}

function formatMetric(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "—";
  return `${formatNumber(value)} ${unit}`;
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

function textValue(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (typeof value === "string" && value.trim()) return value;
  return null;
}

function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return status.replaceAll("_", " ");
}

function isCceeManualSource(sourceId: string): boolean {
  return sourceId === "ccee_plant_parcel_monthly" || sourceId === "ccee_plant_generation_hourly";
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
    <div className="rounded border border-zinc-800 bg-zinc-900/40 px-2 py-1.5 text-[11px] text-zinc-500">
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
        <span>period {source.last_requested_period ?? source.last_period_start ?? "—"}</span>
        <span>bytes {formatBytes(source.last_downloaded_bytes)}</span>
        <span>source {formatNullableInteger(source.last_source_rows)}</span>
        <span>parsed {formatNullableInteger(source.last_parsed_rows ?? source.last_normalized_rows)}</span>
        <span>cached {formatNullableInteger(source.last_rows_inserted)}</span>
        <span>skipped {formatNullableInteger(source.last_rows_skipped)}</span>
      </div>
      {source.last_detected_encoding ? (
        <p className="mt-1 font-mono text-zinc-600">encoding {source.last_detected_encoding}</p>
      ) : null}
    </div>
  );
}

function emptyCatalogMessage(statuses: PlantParcelSourceStatus[]): string {
  if (statuses.some((source) => source.last_error || source.cache_status === "failed")) {
    return "The latest source refresh failed. Check the source card error, then refresh again.";
  }
  if (statuses.some((source) => source.last_warning || source.cache_status === "warning")) {
    return "The latest refresh imported no rows. Check the source warning or choose another period.";
  }
  if (statuses.every((source) => source.cache_status === "never_refreshed")) {
    return "Refresh ANEEL SIGA or CCEE monthly data to populate the local plant catalog.";
  }
  return "Refresh ANEEL SIGA and CCEE monthly data, or clear the current search and filters.";
}
