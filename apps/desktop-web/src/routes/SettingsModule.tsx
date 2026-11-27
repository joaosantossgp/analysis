import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/PageHeader";
import { UpdateChannelPanel } from "@/components/settings/UpdateChannelPanel";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { fetchSettingsHealthSummary } from "@/lib/api/settingsHealth";
import { fetchStorageInventory, startStorageInventoryScan, type StorageInventoryResult } from "@/lib/api/storageInventory";
import { openStatusPath, type StatusPathKind } from "@/lib/api/appStatus";
import { describeB3Refresh, fetchB3ClassificationStatus, refreshB3Classification } from "@/lib/api/b3Classification";
import {
  fetchDataUpdateSettings,
  fetchMarketCapSnapshot,
  fetchMarketCapStatus,
  resetLocalDatabase,
  saveDataUpdateSettings,
} from "@/lib/api/updateBase";
import type {
  DataUpdateSettings,
  LocalPathInfo,
  SettingsHealthSegment,
  SettingsHealthStatus,
  SettingsHealthSummary,
  StorageAggregateRow,
  StorageInventory,
} from "@/lib/bridge/types";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { SETTINGS_NAV_ITEMS, type SettingsNavSection } from "@/lib/settingsNav";

import { DataCoveragePage } from "./DataCoveragePage";
import { StatusPage } from "./StatusPage";
import { UserImportsPage } from "./UserImportsPage";

// Lazy so the Indicators chunk loads only when its tab opens.
const IndicatorSourcesPage = lazy(() => import("./CountryKpisPage").then((m) => ({ default: m.IndicatorSourcesPage })));

type SettingsSection =
  | "overview"
  | "data"
  | "app"
  | "storage"
  | "sources"
  | "imports"
  | "indicator-sources"
  | "diagnostics";

type SettingsModuleProps = {
  section: SettingsSection;
};

export function getSettingsNavSection(section: SettingsSection): SettingsNavSection {
  if (section === "imports" || section === "indicator-sources") return "sources";
  if (section === "diagnostics") return "advanced";
  return section;
}

export function SettingsModule({ section }: SettingsModuleProps) {
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const summaryQuery = useQuery({
    queryKey: ["settings-health-summary"],
    queryFn: fetchSettingsHealthSummary,
    enabled: bridgeReady,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const result = summaryQuery.data;
  const summary = result?.summary ?? null;
  const browserReason = result?.mode === "browser" ? result.reason : null;
  const loading = !bridgeReady || summaryQuery.isLoading;
  const navSection = getSettingsNavSection(section);

  return (
    <section className="space-y-5">
      <PageHeader
        title="Settings"
        subtitle="Preferences and maintenance. Data updates run from the Data panel in the top bar."
        actions={
          <StatusBadge status={summary?.overall_status ?? "unknown"}>
            {loading ? "Connecting" : statusLabel(summary?.overall_status ?? "unknown")}
          </StatusBadge>
        }
      />

      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}
      {summaryQuery.isError ? (
        <StateBanner
          variant="error"
          title="Could not load Settings health"
          message={summaryQuery.error instanceof Error ? summaryQuery.error.message : String(summaryQuery.error)}
          onRetry={() => { void summaryQuery.refetch(); }}
        />
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[240px_minmax(0,1fr)]">
        <SettingsNav current={navSection} />
        <main className="min-w-0 space-y-5">
          {section === "overview" ? (
            <SettingsOverview loading={loading} summary={summary} />
          ) : section === "data" ? (
            <>
              <HistoryRangePanel bridgeReady={bridgeReady} />
              <DataCoveragePage />
            </>
          ) : section === "storage" ? (
            <SettingsStorage loading={loading} summary={summary} />
          ) : section === "sources" || section === "imports" || section === "indicator-sources" ? (
            <SettingsSources
              loading={loading}
              summary={summary}
              initialView={section === "imports" ? "imports" : section === "indicator-sources" ? "indicators" : "sources"}
            />
          ) : section === "app" ? (
            <>
              <UpdateChannelPanel bridgeReady={bridgeReady} />
              <SettingsApp loading={loading} summary={summary} />
            </>
          ) : (
            <SettingsNestedPage intro={<DiagnosticsIntro summary={summary} />}>
              <AdvancedEvidence summary={summary} />
              <StatusPage />
              <AdvancedReference />
            </SettingsNestedPage>
          )}
        </main>
      </div>
    </section>
  );
}

function SettingsNav({ current }: { current: SettingsNavSection }) {
  return (
    <aside className="min-w-0">
      <nav
        aria-label="Settings sections"
        className="grid gap-1 rounded-lg border border-zinc-800 bg-zinc-900/55 p-2 xl:sticky xl:top-4"
      >
        {SETTINGS_NAV_ITEMS.map((item) => {
          const active = current === item.id;
          return (
            <NavLink
              key={item.id}
              to={item.to}
              end={item.id === "overview"}
              className="rounded-md border px-3 py-2 text-left transition-colors"
              style={{
                background: active ? "var(--color-surface-3)" : "transparent",
                borderColor: active ? "var(--color-border-default)" : "transparent",
                color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
              }}
            >
              <span className="flex items-center justify-between gap-2 text-sm font-medium">
                {item.label}
                {active ? <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" aria-hidden="true" /> : null}
              </span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}

export function SettingsOverview({
  loading,
  summary,
}: {
  loading: boolean;
  summary: SettingsHealthSummary | null;
}) {
  const attention = useMemo(
    () => (summary?.segments ?? []).filter((segment) => ["critical", "degraded", "empty", "updating"].includes(segment.status)),
    [summary],
  );

  if (loading || !summary) {
    return <StateBanner variant="loading" title="Loading Settings overview..." />;
  }

  return (
    <>
      <Panel title="System status" subtitle={summary.summary.title}>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          <Metric label="Overall" value={statusLabel(summary.overall_status)} status={summary.overall_status} />
          <Metric label="Critical" value={formatNumber(summary.summary.critical_segments)} status={summary.summary.critical_segments ? "critical" : "healthy"} />
          <Metric label="Degraded" value={formatNumber(summary.summary.degraded_segments)} status={summary.summary.degraded_segments ? "degraded" : "healthy"} />
          <Metric label="Empty" value={formatNumber(summary.summary.empty_segments)} status={summary.summary.empty_segments ? "empty" : "healthy"} />
          <Metric label="Updating" value={formatNumber(summary.summary.updating_segments)} status={summary.summary.updating_segments ? "updating" : "healthy"} />
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <Panel
          title="Needs attention"
          subtitle="Each item links to where it is fixed."
        >
          {attention.length === 0 ? (
            <StateBanner
              variant="success"
              title="No required issues detected"
              size="dense"
            />
          ) : (
            <SegmentList segments={attention.slice(0, 5)} compact />
          )}
        </Panel>

        <OverviewStorageCard summary={summary} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SettingsIntentCard
          title="Data"
          status={worstStatus(summary.segments.filter((segment) => isDataSegment(segment)))}
          meta={`${formatNumber(summary.segments.filter((segment) => isDataSegment(segment)).length)} checks`}
          to="/settings/data"
          action="Data completeness"
        />
        <SettingsIntentCard
          title="Sources"
          status={worstStatus(summary.segments.filter((segment) => isSourceSegment(segment)))}
          meta="Managed sources and imports"
          to="/settings/sources"
          action="Open sources"
        />
        <SettingsIntentCard
          title="Storage"
          status={inventoryStatusForBadge(summary.storage_inventory?.status)}
          meta={summary.storage_inventory ? formatBytes(summary.storage_inventory.logical_bytes_total) : "No inventory"}
          to="/settings/storage"
          action="Open storage"
        />
        <SettingsIntentCard
          title="App"
          status={summary.runtime.bridge_status === "ready" ? "healthy" : "unavailable"}
          meta={`${runtimeModeLabel(summary.runtime.runtime_mode)} · ${summary.runtime.write_mode ?? "unknown"}`}
          to="/settings/app"
          action="View app state"
        />
        {summary.overall_status === "critical" || summary.errors.length > 0 ? (
          <SettingsIntentCard
            title="Advanced"
            status="critical"
            meta={`${formatNumber(summary.errors.length)} error(s)`}
            to="/settings/diagnostics"
            action="Open diagnostics"
          />
        ) : null}
      </div>
    </>
  );
}

type SourcesView = "sources" | "imports" | "indicators";

function SettingsSources({
  loading,
  summary,
  initialView,
}: {
  loading: boolean;
  summary: SettingsHealthSummary | null;
  initialView: SourcesView;
}) {
  const [view, setView] = useState<SourcesView>(initialView);

  useEffect(() => {
    setView(initialView);
  }, [initialView]);

  if (loading || !summary) {
    return <StateBanner variant="loading" title="Loading sources..." />;
  }

  const sourceSegments = summary.segments.filter((segment) => isSourceSegment(segment));

  return (
    <>
      <Panel
        title="Sources"
        subtitle="Managed local sources and user files."
        actions={<StatusBadge status={worstStatus(sourceSegments)}>{statusLabel(worstStatus(sourceSegments))}</StatusBadge>}
      >
        <div className="grid gap-3 md:grid-cols-3">
          <Metric label="Source checks" value={formatNumber(sourceSegments.length)} status={worstStatus(sourceSegments)} />
          <Metric label="Warnings" value={formatNumber(sourceSegments.reduce((total, segment) => total + segment.warnings.length, 0))} status={sourceSegments.some((segment) => segment.warnings.length > 0) ? "degraded" : "healthy"} />
          <Metric label="Errors" value={formatNumber(sourceSegments.reduce((total, segment) => total + segment.errors.length, 0))} status={sourceSegments.some((segment) => segment.errors.length > 0) ? "critical" : "healthy"} />
        </div>
      </Panel>

      <div className="flex flex-wrap gap-2 rounded-lg border border-zinc-800 bg-zinc-900/55 p-2">
        <TabButton active={view === "sources"} onClick={() => setView("sources")}>Data Sources</TabButton>
        <TabButton active={view === "imports"} onClick={() => setView("imports")}>Manual Imports</TabButton>
        <TabButton active={view === "indicators"} onClick={() => setView("indicators")}>Indicator sources</TabButton>
      </div>

      {view === "sources" ? (
        <>
          <Panel title="Data Sources" subtitle="Managed local sources and their current state.">
            <SegmentList segments={sourceSegments} />
          </Panel>
          <B3SectorSourcePanel />
          <MarketCapSourcePanel />
        </>
      ) : view === "imports" ? (
        <SettingsGroup
          title="Manual Imports"
          subtitle="CCEE source files, drag-and-drop import, status, and audit evidence."
        >
          <UserImportsPage />
        </SettingsGroup>
      ) : (
        <SettingsGroup
          title="Indicator sources"
          subtitle="Distribution source health for the Indicators module."
        >
          <Suspense fallback={<StateBanner variant="loading" title="Loading indicator sources..." />}>
            <IndicatorSourcesPage />
          </Suspense>
        </SettingsGroup>
      )}
    </>
  );
}

function B3SectorSourcePanel() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["b3-classification-status"], queryFn: fetchB3ClassificationStatus });
  const refresh = useMutation({
    mutationFn: refreshB3Classification,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["b3-classification-status"] });
      void queryClient.invalidateQueries({ queryKey: ["company-info"] });
    },
  });
  const errors = status.data?.last_run?.errors;
  const errorText = Array.isArray(errors) ? errors.join("\n") : errors;

  return (
    <Panel
      title="B3 sector classification"
      subtitle="Setor / subsetor / segmento as published by B3 for local companies. Shown as source metadata, never as the GICS classification. Fetched only when you refresh."
      actions={
        <Button size="sm" variant="secondary" loading={refresh.isPending} onClick={() => refresh.mutate()}>
          Refresh B3 sectors
        </Button>
      }
    >
      {status.isLoading ? <StateBanner variant="loading" title="Loading B3 sector status..." /> : null}
      {status.error ? <StateBanner variant="error" message={String((status.error as Error).message ?? status.error)} /> : null}
      {status.data ? (
        <div className="flex flex-col gap-2 text-sm">
          <span style={{ color: status.data.stale || status.data.last_run?.failed ? "var(--color-state-warn)" : undefined }}>
            {describeB3Refresh(status.data)}
          </span>
          <span className="text-xs text-zinc-500">{status.data.stored_companies} companies have stored B3 sectors.</span>
          {errorText ? <pre className="text-xs whitespace-pre-wrap text-zinc-400">{errorText}</pre> : null}
        </div>
      ) : null}
      {refresh.error ? <StateBanner variant="error" message={(refresh.error as Error).message} /> : null}
    </Panel>
  );
}

function MarketCapSourcePanel() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["market-cap-status"], queryFn: fetchMarketCapStatus, refetchOnWindowFocus: false });
  const fetchCaps = useMutation({
    mutationFn: fetchMarketCapSnapshot,
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["market-cap-status"] });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
  });
  const data = status.data;
  const notes = data ? [...(data.error ? [data.error] : []), ...(data.warnings ?? [])] : [];

  return (
    <Panel
      title="Market caps · Yahoo Finance (unofficial)"
      subtitle="Unofficial external market capitalizations, used for market-cap columns and sorting. Never part of CVM statements. Fetched only when you click."
      actions={
        <Button
          size="sm"
          variant="secondary"
          disabled={data === null}
          loading={fetchCaps.isPending}
          onClick={() => fetchCaps.mutate()}
        >
          Fetch market caps
        </Button>
      }
    >
      {status.isLoading ? <StateBanner variant="loading" title="Loading market-cap status..." size="dense" /> : null}
      {status.error ? (
        <StateBanner
          variant="error"
          title="Could not read market-cap status"
          message={status.error instanceof Error ? status.error.message : String(status.error)}
          size="dense"
          onRetry={() => { void status.refetch(); }}
        />
      ) : null}
      {data === null ? <StateBanner variant="browser-only" message="Market caps need the desktop bridge." size="dense" /> : null}
      {data ? (
        <div className="flex flex-col gap-1 text-sm">
          <span style={{ color: data.available ? undefined : "var(--color-state-warn)" }}>
            {data.available
              ? `Last fetch: ${formatNumber(data.row_count)} companies · as of ${data.as_of_date ?? "unknown date"}${
                  data.downloaded_at ? ` · fetched ${formatDate(data.downloaded_at)}` : ""
                }`
              : "No market caps stored locally."}
          </span>
          {notes.map((note) => <span key={note} className="text-xs text-zinc-500">{note}</span>)}
        </div>
      ) : null}
      {fetchCaps.error ? (
        <StateBanner
          variant="error"
          title="Could not fetch market caps"
          message={fetchCaps.error instanceof Error ? fetchCaps.error.message : String(fetchCaps.error)}
          size="dense"
        />
      ) : null}
    </Panel>
  );
}

type HistoryRange = "3" | "5" | "10" | "2010";

const HISTORY_RANGE_OPTIONS: Array<{ value: HistoryRange; label: string }> = [
  { value: "3", label: "Last 3 years" },
  { value: "5", label: "Last 5 years (default)" },
  { value: "10", label: "Last 10 years" },
  { value: "2010", label: "Since 2010" },
];

export function historyRangeYears(range: HistoryRange, endYear: number): Pick<DataUpdateSettings, "start_year" | "end_year"> {
  return { start_year: range === "2010" ? 2010 : endYear - Number(range) + 1, end_year: endYear };
}

export function historyRangeOf(
  years: Pick<DataUpdateSettings, "start_year" | "end_year">,
  endYear: number,
): HistoryRange | "custom" {
  const match = HISTORY_RANGE_OPTIONS.find(({ value }) => {
    const option = historyRangeYears(value, endYear);
    return option.start_year === years.start_year && option.end_year === years.end_year;
  });
  return match?.value ?? "custom";
}

function HistoryRangePanel({ bridgeReady }: { bridgeReady: boolean }) {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["data-update-settings"],
    queryFn: fetchDataUpdateSettings,
    enabled: bridgeReady,
    refetchOnWindowFocus: false,
  });
  const save = useMutation({
    mutationFn: saveDataUpdateSettings,
    onSuccess: (settings) => queryClient.setQueryData(["data-update-settings"], { mode: "desktop", settings }),
  });
  // The bridge rolls a saved range forward each year, so presets keep matching.
  const endYear = new Date().getFullYear();
  const result = settingsQuery.data;
  const settings = result?.settings ?? null;
  const current = settings ? historyRangeOf(settings, endYear) : null;

  return (
    <Panel
      title="History range"
      subtitle="How many past fiscal years a data update fetches from CVM. Applies to the next data update."
    >
      {!bridgeReady || settingsQuery.isLoading ? (
        <StateBanner variant="loading" title="Loading history range..." size="dense" />
      ) : null}
      {settingsQuery.isError ? (
        <StateBanner
          variant="error"
          title="Could not load the history range"
          message={settingsQuery.error instanceof Error ? settingsQuery.error.message : String(settingsQuery.error)}
          size="dense"
          onRetry={() => { void settingsQuery.refetch(); }}
        />
      ) : null}
      {result?.mode === "browser" ? <StateBanner variant="browser-only" message={result.reason} size="dense" /> : null}
      {settings && current ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <select
            aria-label="History range"
            value={current}
            disabled={result?.mode !== "desktop" || save.isPending}
            onChange={(event) => save.mutate({ ...settings, ...historyRangeYears(event.target.value as HistoryRange, endYear) })}
            className="rounded border px-2 py-1.5 text-sm focus:outline-none"
            style={{
              background: "var(--color-surface-2)",
              borderColor: "var(--color-border-default)",
              color: "var(--color-text-primary)",
            }}
          >
            {current === "custom" ? (
              <option value="custom" disabled>
                Custom ({settings.start_year}–{settings.end_year})
              </option>
            ) : null}
            {HISTORY_RANGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <span className="font-mono text-xs text-zinc-500">
            Fiscal years {settings.start_year}–{settings.end_year}
          </span>
          {save.isPending ? <span className="text-xs text-zinc-500">Saving...</span> : null}
          {save.isSuccess && !save.isPending ? <span className="text-xs text-emerald-200">Saved</span> : null}
        </div>
      ) : null}
      {save.error ? (
        <StateBanner
          variant="error"
          title="Could not save the history range"
          message={save.error instanceof Error ? save.error.message : String(save.error)}
          size="dense"
        />
      ) : null}
    </Panel>
  );
}

function SettingsApp({
  loading,
  summary,
}: {
  loading: boolean;
  summary: SettingsHealthSummary | null;
}) {
  const openMutation = useMutation({ mutationFn: openStatusPath });
  const [copied, setCopied] = useState<string | null>(null);

  if (loading || !summary) {
    return <StateBanner variant="loading" title="Loading app state..." />;
  }

  const paths = Object.values(summary.storage).filter(Boolean) as LocalPathInfo[];
  const desktopMode = summary.runtime.bridge_status === "ready";

  async function copyPath(item: LocalPathInfo) {
    try {
      await navigator.clipboard.writeText(item.path);
      setCopied(item.kind);
    } catch {
      setCopied(null);
    }
  }

  return (
    <>
      <Panel title="App" subtitle="User-facing runtime state for the local desktop app.">
        <dl className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <Field label="Version" value={summary.runtime.version} mono />
          <Field label="Runtime" value={runtimeModeLabel(summary.runtime.runtime_mode)} />
          <Field label="Bridge" value={summary.runtime.bridge_status || "unknown"} />
          <Field label="Write mode" value={summary.runtime.write_mode ?? "unknown"} tone={summary.runtime.write_mode === "read-only" ? "warn" : "neutral"} />
          <Field label="Data root mode" value={summary.runtime.using_release_data_dir ? "shared Documents data" : "app-managed data"} />
          <Field label="Desktop shell" value={summary.runtime.desktop_shell ?? "unknown"} mono />
          <Field label="Local-first" value={summary.runtime.local_first ? "yes" : "no"} />
          <Field label="Lock" value={summary.runtime.lock_status?.status ?? "unknown"} mono />
        </dl>
      </Panel>

      <Panel title="Local Files" subtitle="Common app locations. Diagnostics exposes the full technical view.">
        {paths.length === 0 ? (
          <StateBanner variant="empty" title="No local paths reported" message="Path diagnostics require the desktop bridge." />
        ) : (
          <div className="divide-y divide-zinc-800 rounded border border-zinc-800">
            {paths.map((item) => (
              <div key={item.kind} className="grid gap-3 p-3 lg:grid-cols-[10rem_minmax(0,1fr)_auto] lg:items-center">
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-500">{pathLabel(item.kind)}</p>
                  <StatusBadge status={item.exists ? "healthy" : "empty"}>{item.exists ? "Exists" : "Missing"}</StatusBadge>
                </div>
                <p className="break-all font-mono text-xs leading-5 text-zinc-200">{item.path}</p>
                <div className="flex flex-wrap gap-2">
                  <Button size="xs" variant="ghost" onClick={() => void copyPath(item)}>
                    {copied === item.kind ? "Copied" : "Copy"}
                  </Button>
                  <Button
                    size="xs"
                    variant="secondary"
                    disabled={!desktopMode || !canOpenPath(item.kind)}
                    loading={openMutation.isPending && openMutation.variables === item.kind}
                    onClick={() => openMutation.mutate(item.kind as StatusPathKind)}
                  >
                    Open
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
        {openMutation.error ? (
          <StateBanner
            variant="error"
            title="Could not open path"
            message={openMutation.error instanceof Error ? openMutation.error.message : String(openMutation.error)}
            size="dense"
          />
        ) : null}
      </Panel>
    </>
  );
}

export function SettingsStorage({
  loading,
  summary,
}: {
  loading: boolean;
  summary: SettingsHealthSummary | null;
}) {
  const queryClient = useQueryClient();
  const openMutation = useMutation({ mutationFn: openStatusPath });
  const inventoryQuery = useQuery({
    queryKey: ["storage-inventory"],
    queryFn: fetchStorageInventory,
    enabled: !loading,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const inventory = query.state.data?.inventory;
      return inventory?.scan_status?.status === "running" ? 1500 : false;
    },
  });
  const refreshMutation = useMutation({
    mutationFn: startStorageInventoryScan,
    onMutate: () => queryClient.cancelQueries({ queryKey: ["storage-inventory"] }),
    onSuccess: (result) => {
      // Keep one current status; the mutation's initial running response never advances.
      queryClient.setQueryData<StorageInventoryResult>(["storage-inventory"], (current) => current ? {
        ...current,
        inventory: { ...current.inventory, scan_status: result.scan_status },
      } : current);
      void queryClient.invalidateQueries({ queryKey: ["storage-inventory"] });
      void queryClient.invalidateQueries({ queryKey: ["settings-health-summary"] });
    },
  });
  const [copied, setCopied] = useState<string | null>(null);
  if (loading || !summary) {
    return <StateBanner variant="loading" title="Loading local storage..." />;
  }
  const paths = Object.values(summary.storage).filter(Boolean) as LocalPathInfo[];
  const desktopMode = summary.runtime.bridge_status === "ready";
  const inventory = inventoryQuery.data?.inventory ?? null;
  const browserReason = inventoryQuery.data?.mode === "browser" ? inventoryQuery.data.reason : null;
  const scanRunning = refreshMutation.isPending || inventory?.scan_status?.status === "running";
  async function copyPath(item: LocalPathInfo) {
    try {
      await navigator.clipboard.writeText(item.path);
      setCopied(item.kind);
    } catch {
      setCopied(null);
    }
  }
  return (
    <>
      {browserReason ? <StateBanner variant="browser-only" message={browserReason} /> : null}
      {inventoryQuery.isError ? (
        <StateBanner
          variant="error"
          title="Could not load storage inventory"
          message={inventoryQuery.error instanceof Error ? inventoryQuery.error.message : String(inventoryQuery.error)}
          onRetry={() => { void inventoryQuery.refetch(); }}
        />
      ) : null}

      <Panel
        title="Storage Summary"
        subtitle="Cached local data footprint. Manual refresh runs a background scan."
        actions={
          <Button
            size="sm"
            variant="secondary"
            disabled={!desktopMode || !inventory || scanRunning}
            loading={scanRunning}
            onClick={() => refreshMutation.mutate()}
          >
            {scanRunning ? "Scanning..." : "Refresh inventory"}
          </Button>
        }
      >
        {!inventory || inventoryQuery.isLoading ? (
          <StateBanner variant="loading" title="Loading cached storage inventory..." size="dense" />
        ) : inventory.scanned_at === null ? (
          <StateBanner
            variant="empty"
            title="No storage inventory yet"
            message="Refresh inventory to measure CVMAnalytics-owned local data. Settings does not start a recursive scan automatically."
            size="dense"
          />
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <Metric label="Local data" value={formatBytes(inventory.logical_bytes_total)} status={inventoryStatusForBadge(inventory.status)} />
              <Metric label="Files" value={formatNumber(inventory.file_count)} />
              <Metric label="Free space" value={formatBytes(inventory.volumes[0]?.free_bytes)} status={inventory.volumes[0]?.status ?? "unknown"} />
              <Metric label="Largest category" value={inventory.categories[0]?.label ?? "—"} />
              <Metric label="Measured" value={formatRelativeAge(inventory.scan_age_seconds)} status={inventory.is_stale ? "degraded" : "healthy"} />
            </div>
            <p className="mt-4 text-xs leading-5 text-zinc-500">
              Values are logical file sizes, not allocated disk usage. Full scan elapsed {formatNumber(inventory.elapsed_ms)} ms across {formatNumber(inventory.file_count)} files.
            </p>
          </>
        )}
        {inventoryQuery.data?.mode !== "browser" && inventory?.scan_status.status === "failed" ? (
          <StateBanner
            variant="error"
            title="Storage scan failed"
            message={`${inventory.scan_status.error || "The storage scan could not finish."}${inventory.scanned_at ? " The previous inventory is still shown." : ""}`}
            size="dense"
          />
        ) : null}
        {refreshMutation.error ? (
          <StateBanner
            variant="error"
            title="Could not start storage scan"
            message={refreshMutation.error instanceof Error ? refreshMutation.error.message : String(refreshMutation.error)}
            size="dense"
          />
        ) : null}
      </Panel>

      <Panel title="Managed Paths" subtitle="Resolved Settings paths and safe open-folder actions.">
        {paths.length === 0 ? (
          <StateBanner variant="empty" title="No local paths reported" message="Path diagnostics require the desktop bridge." />
        ) : (
          <div className="divide-y divide-zinc-800 rounded border border-zinc-800">
            {paths.map((item) => (
              <div key={item.kind} className="grid gap-3 p-3 lg:grid-cols-[10rem_minmax(0,1fr)_auto] lg:items-center">
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-500">{pathLabel(item.kind)}</p>
                  <StatusBadge status={item.exists ? "healthy" : "empty"}>{item.exists ? "Exists" : "Missing"}</StatusBadge>
                </div>
                <p className="break-all font-mono text-xs leading-5 text-zinc-200">{item.path}</p>
                <div className="flex flex-wrap gap-2">
                  <Button size="xs" variant="ghost" onClick={() => void copyPath(item)}>
                    {copied === item.kind ? "Copied" : "Copy"}
                  </Button>
                  <Button
                    size="xs"
                    variant="secondary"
                    disabled={!desktopMode || !canOpenPath(item.kind)}
                    loading={openMutation.isPending && openMutation.variables === item.kind}
                    onClick={() => openMutation.mutate(item.kind as StatusPathKind)}
                  >
                    Open
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
        {openMutation.error ? (
          <StateBanner
            variant="error"
            title="Could not open path"
            message={openMutation.error instanceof Error ? openMutation.error.message : String(openMutation.error)}
            size="dense"
          />
        ) : null}
      </Panel>

      <RebuildDatabasePanel desktopMode={desktopMode} />

      {inventory ? (
        <AdvancedDisclosure title="Advanced details">
          <StorageArchitectureSnapshot inventory={inventory} />
          <StorageInventoryDetails inventory={inventory} />
        </AdvancedDisclosure>
      ) : null}
    </>
  );
}

const REBUILD_CONFIRMATION = "REBUILD";

function RebuildDatabasePanel({ desktopMode }: { desktopMode: boolean }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const rebuild = useMutation({
    mutationFn: resetLocalDatabase,
    onSuccess: () => {
      setConfirming(false);
      setTyped("");
    },
    // Every screen reads the database that was just replaced.
    onSettled: () => { void queryClient.invalidateQueries(); },
  });
  const cancel = () => {
    setConfirming(false);
    setTyped("");
  };

  return (
    <Panel
      title="Rebuild local database"
      subtitle="Backs up the current database, then recreates it empty. Your ignore flags and History range are kept. Nothing downloads until you start a data update."
      actions={
        confirming ? null : (
          <Button size="sm" variant="danger" disabled={!desktopMode || rebuild.isPending} onClick={() => setConfirming(true)}>
            Rebuild local database
          </Button>
        )
      }
    >
      {confirming ? (
        <div className="space-y-3">
          <label className="block text-xs text-zinc-400">
            Statements stay out of the local database until the next data update. Type{" "}
            <span className="font-mono text-zinc-100">{REBUILD_CONFIRMATION}</span> to confirm.
            <input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              aria-label="Type REBUILD to confirm"
              autoFocus
              className="mt-2 block w-full max-w-xs rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 font-mono text-sm text-zinc-100 focus:border-amber-500 focus:outline-none"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="danger"
              disabled={typed !== REBUILD_CONFIRMATION}
              loading={rebuild.isPending}
              onClick={() => rebuild.mutate({ action: "recreate_local", confirm: typed })}
            >
              Back up and rebuild
            </Button>
            <Button size="sm" variant="ghost" disabled={rebuild.isPending} onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
      {!desktopMode ? (
        <StateBanner variant="browser-only" message="Rebuilding needs the desktop bridge." size="dense" />
      ) : null}
      {rebuild.data ? (
        <StateBanner
          variant="success"
          title="Local database rebuilt"
          message={`${rebuild.data.message ?? ""}${rebuild.data.backup_path ? ` Backup: ${rebuild.data.backup_path}` : ""}`}
          size="dense"
        />
      ) : null}
      {rebuild.error ? (
        <StateBanner
          variant="error"
          title="Could not rebuild the local database"
          message={rebuild.error instanceof Error ? rebuild.error.message : String(rebuild.error)}
          size="dense"
        />
      ) : null}
    </Panel>
  );
}

function StorageArchitectureSnapshot({ inventory }: { inventory: StorageInventory }) {
  const category = (id: string) => inventory.categories.find((row) => row.id === id);
  const databases = category("databases");
  const analytical = category("analytical_stores");
  const backups = category("backups");
  const raw = category("raw_sources");
  const backupBytes = backups?.logical_bytes ?? 0;
  return (
    <Panel
      title="Tiered Local Storage"
      subtitle="Main SQLite files, managed analytical stores, raw sources, and rollback backups are tracked separately."
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Metric label="Main databases" value={formatBytes(databases?.logical_bytes)} status="healthy" />
        <Metric label="Analytical stores" value={formatBytes(analytical?.logical_bytes)} status={analytical ? "healthy" : "unknown"} />
        <Metric label="Raw sources" value={formatBytes(raw?.logical_bytes)} />
        <Metric label="Rollback backups" value={formatBytes(backupBytes)} status={backupBytes > 0 ? "degraded" : "healthy"} />
      </div>
      <p className="mt-4 text-xs leading-5 text-zinc-500">
        Backups are retained for rollback and are not deleted automatically. Analytical stores hold externalized high-frequency facts used by bounded drill-down reads.
      </p>
    </Panel>
  );
}

function OverviewStorageCard({ summary }: { summary: SettingsHealthSummary }) {
  const storage = summary.storage_inventory;
  if (!storage) {
    return (
      <Panel title="Storage" subtitle="Local data footprint">
        <StateBanner
          variant="empty"
          title="No storage inventory summary"
          size="dense"
        />
        <div className="mt-3">
          <LinkButton to="/settings/storage">Open Storage</LinkButton>
        </div>
      </Panel>
    );
  }
  return (
    <Panel
      title="Storage"
      subtitle="Cached local data footprint"
      actions={<LinkButton to="/settings/storage">Open Storage</LinkButton>}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <Metric label="Local data" value={formatBytes(storage.logical_bytes_total)} status={inventoryStatusForBadge(storage.status)} />
        <Metric label="Free on volume" value={formatBytes(storage.main_volume?.free_bytes)} status={storage.main_volume?.status ?? "unknown"} />
        <Metric label="Largest category" value={storage.largest_category?.label ?? "—"} />
        <Metric label="Measured" value={formatRelativeAge(storage.scan_age_seconds)} status={storage.is_stale ? "degraded" : "healthy"} />
      </div>
    </Panel>
  );
}

function StorageInventoryDetails({ inventory }: { inventory: StorageInventory }) {
  return (
    <>
      {inventory.warnings.length || inventory.errors.length ? (
        <Panel title="Storage Warnings" subtitle="Skipped paths, partial scans, and diagnostic warnings." dense>
          <div className="space-y-2">
            {inventory.errors.map((message) => <StateBanner key={message} variant="error" message={message} size="dense" />)}
            {inventory.warnings.map((message) => <StateBanner key={message} variant="warning" message={message} size="dense" />)}
          </div>
        </Panel>
      ) : null}
      <RollbackBackupPlan inventory={inventory} />
      <ManagedSourceSnapshotPlan inventory={inventory} />
      <div className="grid gap-5 xl:grid-cols-2">
        <StorageAggregatePanel title="Storage by Category" rows={inventory.categories} />
        <StorageAggregatePanel title="Storage by Data Segment" rows={inventory.segments} />
      </div>
      <Panel title="Databases" subtitle="SQLite main files, sidecars, and internal free-page estimates.">
        <div className="overflow-auto">
          <table className="w-full min-w-[920px] border-collapse text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="border-b border-zinc-800 px-3 py-2">Database</th>
                <th className="border-b border-zinc-800 px-3 py-2 text-right">Main file</th>
                <th className="border-b border-zinc-800 px-3 py-2 text-right">WAL</th>
                <th className="border-b border-zinc-800 px-3 py-2 text-right">SHM</th>
                <th className="border-b border-zinc-800 px-3 py-2 text-right">Internal free estimate</th>
                <th className="border-b border-zinc-800 px-3 py-2">Journal</th>
                <th className="border-b border-zinc-800 px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {inventory.databases.map((db) => (
                <tr key={db.id} className="border-b border-zinc-900">
                  <td className="px-3 py-2">
                    <p className="font-medium text-zinc-100">{db.label}</p>
                    <p className="break-all font-mono text-[11px] text-zinc-500">{db.path}</p>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-200">{formatBytes(db.logical_bytes)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-200">{formatBytes(db.wal_bytes)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-200">{formatBytes(db.shm_bytes)}</td>
                  <td className="px-3 py-2 text-right font-mono text-zinc-200">{formatBytes(db.sqlite?.estimated_internal_free_bytes)}</td>
                  <td className="px-3 py-2 font-mono text-xs text-zinc-400">{db.sqlite?.journal_mode ?? "—"}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={db.readable ? "healthy" : db.exists ? "degraded" : "empty"}>{db.readable ? "Readable" : db.exists ? "Metadata unavailable" : "Missing"}</StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          Internal free-page bytes may be reused by SQLite later. They are not a cleanup amount and do not justify automatic VACUUM.
        </p>
      </Panel>
      <Panel title="Largest Managed Items" subtitle="Bounded top items from the latest scan.">
        <div className="divide-y divide-zinc-800 rounded border border-zinc-800">
          {inventory.largest_items.map((item) => (
            <div key={item.path} className="grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_10rem_12rem]">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-100">{item.name}</p>
                <p className="break-all font-mono text-[11px] text-zinc-500">{item.path}</p>
              </div>
              <p className="font-mono text-sm text-zinc-200 lg:text-right">{formatBytes(item.logical_bytes)}</p>
              <p className="text-xs text-zinc-500">{item.category_label} · {item.segment_label}</p>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Measurement Notes" subtitle="Inventory semantics and limitations." dense>
        <ul className="space-y-2 text-xs leading-5 text-zinc-400">
          {inventory.measurement_notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      </Panel>
    </>
  );
}

function ManagedSourceSnapshotPlan({ inventory }: { inventory: StorageInventory }) {
  const snapshots = inventory.managed_snapshot_history ?? [];
  if (snapshots.length === 0) {
    return null;
  }
  const current = snapshots.filter((item) => item.active_in_manifest);
  const retained = snapshots.filter((item) => !item.active_in_manifest);
  const retainedBytes = retained.reduce((total, item) => total + (item.logical_bytes ?? 0), 0);
  return (
    <Panel
      title="Managed Source Snapshots"
      subtitle="Raw source batches retained for auditability before any future cleanup policy."
    >
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="Current batches" value={formatNumber(current.length)} status="healthy" />
        <Metric label="Retained audit batches" value={formatNumber(retained.length)} status={retained.length ? "degraded" : "healthy"} />
        <Metric label="Retained bytes" value={formatBytes(retainedBytes)} />
      </div>
      <div className="mt-4 divide-y divide-zinc-800 rounded border border-zinc-800">
        {snapshots.slice(0, 8).map((item) => (
          <div key={item.path} className="grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_9rem_8rem] lg:items-start">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium text-zinc-100">{item.dataset_id}</p>
                <StatusBadge status={item.active_in_manifest ? "healthy" : "degraded"}>
                  {item.active_in_manifest ? "Current" : "Retained"}
                </StatusBadge>
              </div>
              <p className="mt-1 font-mono text-[11px] text-zinc-500">{item.domain} · {item.snapshot_id}</p>
              <p className="break-all font-mono text-[11px] text-zinc-500">{item.path}</p>
              <p className="mt-1 text-xs leading-5 text-zinc-500">{item.reason}</p>
            </div>
            <p className="font-mono text-sm text-zinc-200 lg:text-right">{formatBytes(item.logical_bytes)}</p>
            <p className="text-xs text-zinc-500 lg:text-right">{formatDate(item.modified_at)}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-zinc-500">
        This panel is diagnostic only. It does not delete or move source files; retention rules must be introduced as a separate audited maintenance step.
      </p>
    </Panel>
  );
}

function RollbackBackupPlan({ inventory }: { inventory: StorageInventory }) {
  const candidates = inventory.backup_candidates ?? [];
  if (candidates.length === 0) {
    return null;
  }
  const reclaimableBytes = candidates.reduce((total, item) => total + (item.reclaimable_bytes ?? item.logical_bytes ?? 0), 0);
  return (
    <Panel
      title="Rollback Backup Plan"
      subtitle="Migration backups that can reclaim disk space after validation."
    >
      <div className="grid gap-3 md:grid-cols-3">
        <Metric label="Reclaimable" value={formatBytes(reclaimableBytes)} status="degraded" />
        <Metric label="Backup sets" value={formatNumber(candidates.length)} />
        <Metric label="Files" value={formatNumber(candidates.reduce((total, item) => total + (item.file_count ?? 0), 0))} />
      </div>
      <div className="mt-4 divide-y divide-zinc-800 rounded border border-zinc-800">
        {candidates.slice(0, 5).map((item) => (
          <div key={item.path} className="grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_9rem_8rem] lg:items-start">
            <div className="min-w-0">
              <p className="text-sm font-medium text-zinc-100">{item.label}</p>
              <p className="break-all font-mono text-[11px] text-zinc-500">{item.path}</p>
              <p className="mt-1 text-xs leading-5 text-zinc-500">{item.reason}</p>
            </div>
            <p className="font-mono text-sm text-zinc-200 lg:text-right">{formatBytes(item.logical_bytes)}</p>
            <p className="text-xs text-zinc-500 lg:text-right">{formatDate(item.modified_at)}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-amber-100">
        Cleanup is intentionally manual for now. Delete or move these backups only after the compact database and analytical store have been validated.
      </p>
    </Panel>
  );
}

function StorageAggregatePanel({ title, rows }: { title: string; rows: StorageAggregateRow[] }) {
  return (
    <Panel title={title} subtitle="Logical bytes by confirmed ownership." dense>
      <div className="space-y-3">
        {rows.length === 0 ? (
          <StateBanner variant="empty" title="No rows in latest inventory" size="dense" />
        ) : rows.map((row) => (
          <div key={row.id}>
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate text-zinc-200">{row.label}</span>
              <span className="font-mono text-zinc-100">{formatBytes(row.logical_bytes)}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded bg-zinc-900">
              <div
                className="h-full bg-cyan-500/70"
                style={{ width: `${Math.max(1, Math.min(100, row.percentage_of_total ?? 0))}%` }}
              />
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">{formatNumber(row.file_count)} files · {formatPercent(row.percentage_of_total)}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SettingsIntentCard({
  title,
  status,
  meta,
  to,
  action,
}: {
  title: string;
  status: SettingsHealthStatus;
  meta: string;
  to: string;
  action: string;
}) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/55 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
          <p className="mt-1 text-xs text-zinc-500">{meta}</p>
        </div>
        <StatusBadge status={status}>{statusLabel(status)}</StatusBadge>
      </div>
      <div className="mt-4">
        <LinkButton to={to}>{action}</LinkButton>
      </div>
    </article>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border px-3 py-1.5 text-xs font-medium transition-colors"
      style={{
        background: active ? "var(--color-surface-3)" : "transparent",
        borderColor: active ? "var(--color-border-default)" : "transparent",
        color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
      }}
    >
      {children}
    </button>
  );
}

function AdvancedDisclosure({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <details className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <summary className="cursor-pointer text-sm font-semibold text-zinc-100">{title}</summary>
      <div className="mt-4 space-y-5">{children}</div>
    </details>
  );
}

function AdvancedEvidence({ summary }: { summary: SettingsHealthSummary | null }) {
  if (!summary) {
    return null;
  }
  return (
    <Panel title="Evidence" subtitle="Metric provenance for the Settings health summary." dense>
      <div className="overflow-auto">
        <table className="w-full min-w-[780px] border-collapse text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="border-b border-zinc-800 px-3 py-2">Metric</th>
              <th className="border-b border-zinc-800 px-3 py-2">Source</th>
              <th className="border-b border-zinc-800 px-3 py-2">Cost</th>
              <th className="border-b border-zinc-800 px-3 py-2">Failure behavior</th>
            </tr>
          </thead>
          <tbody>
            {summary.provenance.map((item) => (
              <tr key={`${item.metric}-${item.source}`} className="border-b border-zinc-900">
                <td className="px-3 py-2 font-mono text-xs text-zinc-200">{item.metric}</td>
                <td className="px-3 py-2 text-zinc-300">{item.source}</td>
                <td className="px-3 py-2 text-zinc-400">{item.cost}</td>
                <td className="px-3 py-2 text-zinc-500">{item.failure_behavior}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function AdvancedReference() {
  const statuses: SettingsHealthStatus[] = ["healthy", "degraded", "critical", "updating", "empty", "unavailable", "unknown"];
  return (
    <Panel title="Reference" subtitle="Status definitions used across Settings." dense>
      <div className="grid gap-2 md:grid-cols-2">
        {statuses.map((status) => (
          <div key={status} className="rounded border border-zinc-800 bg-zinc-950/45 p-3">
            <StatusBadge status={status}>{statusLabel(status)}</StatusBadge>
            <p className="mt-2 text-xs leading-5 text-zinc-500">{definition(status)}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function SettingsNestedPage({
  intro,
  children,
}: {
  intro: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {intro}
      {children}
    </>
  );
}

function SettingsGroup({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="border-b border-zinc-800 pb-2">
        <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
        <p className="mt-1 text-sm leading-5 text-zinc-500">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function DiagnosticsIntro({ summary }: { summary: SettingsHealthSummary | null }) {
  return (
    <SectionIntro
      title="Advanced Diagnostics"
      description="Runtime, software updater, logs, local paths, and detailed technical diagnostics for troubleshooting."
      segment={summary?.segments.find((segment) => segment.status === "critical") ?? null}
    />
  );
}

function SectionIntro({
  title,
  description,
  segment,
}: {
  title: string;
  description: string;
  segment?: SettingsHealthSegment | null;
}) {
  return (
    <Panel
      title={title}
      subtitle={description}
      dense
      actions={segment ? <StatusBadge status={segment.status}>{statusLabel(segment.status)}</StatusBadge> : null}
    >
      {segment ? (
        <p className="text-sm leading-6 text-zinc-300">{segment.reason}</p>
      ) : (
        <p className="text-sm leading-6 text-zinc-500">No immediate issue reported by the Settings health summary.</p>
      )}
    </Panel>
  );
}

function SegmentList({
  segments,
  compact,
}: {
  segments: SettingsHealthSegment[];
  compact?: boolean;
}) {
  if (segments.length === 0) {
    return <StateBanner variant="empty" title="No segment evidence reported" size="dense" />;
  }
  return (
    <div className="divide-y divide-zinc-800 rounded border border-zinc-800">
      {segments.map((segment) => (
        <div key={segment.id} className="grid gap-3 p-3 xl:grid-cols-[minmax(220px,0.75fr)_minmax(0,1.25fr)_auto] xl:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={segment.status}>{statusLabel(segment.status)}</StatusBadge>
              {segment.required ? <span className="font-mono text-[11px] uppercase text-zinc-500">required</span> : null}
            </div>
            <h3 className="mt-2 text-sm font-semibold text-zinc-100">{segment.name}</h3>
            <p className="mt-1 text-xs text-zinc-500">{segment.provider ?? "Unknown provider"} · {segment.owner ?? "Unknown owner"}</p>
          </div>
          <div className="min-w-0">
            <p className="text-sm leading-6 text-zinc-300">{segment.reason}</p>
            {!compact ? (
              <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-3">
                <Field label="Records" value={formatNumber(segment.record_count)} mono />
                <Field label="Latest ref" value={segment.latest_reference ?? "—"} mono />
                <Field label="Last success" value={formatDate(segment.last_successful_update)} mono />
              </dl>
            ) : null}
            {segment.warnings.length || segment.errors.length ? (
              <p className="mt-2 truncate text-xs text-amber-200">
                {[...segment.errors, ...segment.warnings].filter(Boolean).join(" · ")}
              </p>
            ) : null}
          </div>
          <div className="flex justify-start xl:justify-end">
            <LinkButton to={segment.action_route}>{actionLabel(segment.action_route)}</LinkButton>
          </div>
        </div>
      ))}
    </div>
  );
}

function Metric({
  label,
  value,
  status = "unknown",
}: {
  label: string;
  value: string;
  status?: SettingsHealthStatus | false | 0;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/45 p-3">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-1 font-mono text-base font-semibold ${statusTextClass(status || "unknown")}`}>{value}</p>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  tone = "neutral",
}: {
  label: string;
  value: string;
  mono?: boolean;
  tone?: "neutral" | "warn";
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className={`mt-1 break-words text-xs ${mono ? "font-mono" : ""} ${tone === "warn" ? "text-amber-200" : "text-zinc-200"}`}>{value}</dd>
    </div>
  );
}

function StatusBadge({
  status,
  children,
}: {
  status: SettingsHealthStatus;
  children: ReactNode;
}) {
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 font-mono text-[11px] uppercase ${statusClass(status)}`}>
      {children}
    </span>
  );
}

function LinkButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      to={to}
      className="inline-flex h-7 items-center rounded border border-zinc-700 bg-zinc-950/40 px-3 text-xs font-medium text-zinc-200 hover:border-cyan-700 hover:text-cyan-100"
    >
      {children}
    </Link>
  );
}

function statusClass(status: SettingsHealthStatus): string {
  if (status === "healthy") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
  if (status === "degraded" || status === "empty" || status === "updating") return "border-amber-500/30 bg-amber-500/10 text-amber-100";
  if (status === "critical") return "border-rose-500/30 bg-rose-500/10 text-rose-200";
  return "border-zinc-700 bg-zinc-950/70 text-zinc-300";
}

function statusTextClass(status: SettingsHealthStatus): string {
  if (status === "healthy") return "text-emerald-200";
  if (status === "degraded" || status === "empty" || status === "updating") return "text-amber-100";
  if (status === "critical") return "text-rose-200";
  return "text-zinc-100";
}

function statusLabel(status: SettingsHealthStatus): string {
  return status.replaceAll("_", " ");
}

function definition(status: SettingsHealthStatus): string {
  if (status === "healthy") return "Required checks pass with enough evidence for the segment.";
  if (status === "degraded") return "Local data remains usable, but freshness, coverage, quality, or last refresh needs attention.";
  if (status === "critical") return "A required dependency is unreadable, locked, or has a blocking error.";
  if (status === "updating") return "A valid update or import job is running.";
  if (status === "empty") return "The segment is configured but has no usable local data yet.";
  if (status === "unavailable") return "The bridge or optional contract could not report this segment.";
  return "The current evidence is insufficient to classify the segment.";
}

function runtimeModeLabel(mode: string): string {
  if (mode === "vite-dev-release-data") return "vite dev · shared data";
  if (mode === "vite-dev") return "vite dev";
  if (mode === "vite") return "desktop";
  return mode || "unknown";
}

function pathLabel(kind: string): string {
  if (kind === "data") return "Data root";
  if (kind === "database") return "CVM database";
  if (kind === "output") return "Exports";
  if (kind === "logs") return "Logs";
  if (kind === "cache") return "Cache";
  return kind;
}

function actionLabel(route: string): string {
  if (route === "/") return "Download CVM data on Home";
  if (route.startsWith("/settings/data")) return "Open Data completeness";
  if (route.startsWith("/settings/sources")) return "Open Sources";
  if (route.startsWith("/settings/storage")) return "Open Storage";
  if (route.startsWith("/settings/diagnostics")) return "Open Advanced";
  if (route.startsWith("/indicators")) return "Open Indicators";
  return "Open";
}

function canOpenPath(kind: string): boolean {
  return ["data", "database", "output", "logs", "cache"].includes(kind);
}

function isDataSegment(segment: SettingsHealthSegment): boolean {
  return ["cvm_registry", "cvm_financials", "market_data", "energy_macro", "plant_parcels", "distribution"].includes(segment.id);
}

function isSourceSegment(segment: SettingsHealthSegment): boolean {
  return ["plant_parcels", "distribution", "energy_macro", "user_imports", "manual_imports", "news"].includes(segment.id);
}

function worstStatus(segments: SettingsHealthSegment[]): SettingsHealthStatus {
  const order: SettingsHealthStatus[] = ["critical", "degraded", "empty", "updating", "unavailable", "unknown", "healthy"];
  for (const status of order) {
    if (segments.some((segment) => segment.status === status)) return status;
  }
  return "unknown";
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("en-US").format(Number(value));
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const absolute = Math.abs(Number(value));
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let size = absolute;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const formatted = unit === 0 ? String(Math.round(size)) : size.toFixed(size >= 10 ? 1 : 2);
  return `${Number(value) < 0 ? "-" : ""}${formatted} ${units[unit]}`;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function formatRelativeAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "Never";
  const value = Number(seconds);
  if (value < 60) return "Just now";
  if (value < 3600) return `${Math.round(value / 60)} min ago`;
  if (value < 86400) return `${Math.round(value / 3600)} h ago`;
  return `${Math.round(value / 86400)} d ago`;
}

function inventoryStatusForBadge(status: string | null | undefined): SettingsHealthStatus {
  if (status === "partial") return "degraded";
  if (status === "healthy" || status === "degraded" || status === "critical" || status === "updating" || status === "unavailable" || status === "unknown") {
    return status;
  }
  return "unknown";
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-US", { day: "2-digit", month: "2-digit", year: "2-digit" });
}
