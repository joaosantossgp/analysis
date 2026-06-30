import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { fetchSettingsHealthSummary } from "@/lib/api/settingsHealth";
import { fetchStorageInventory, startStorageInventoryScan } from "@/lib/api/storageInventory";
import { openStatusPath, type StatusPathKind } from "@/lib/api/appStatus";
import type {
  LocalPathInfo,
  SettingsHealthSegment,
  SettingsHealthStatus,
  SettingsHealthSummary,
  StorageAggregateRow,
  StorageInventory,
} from "@/lib/bridge/types";
import { whenBridgeReady } from "@/lib/bridge/adapter";

import { DataCoveragePage } from "./DataCoveragePage";
import { NewsSettingsPanel } from "./NewsPage";
import { StatusPage } from "./StatusPage";
import { UpdateBasePage } from "./UpdateBasePage";
import { UserImportsPage } from "./UserImportsPage";

type SettingsSection =
  | "overview"
  | "health"
  | "coverage"
  | "storage"
  | "sources"
  | "imports"
  | "updates"
  | "diagnostics";

type SettingsModuleProps = {
  section: SettingsSection;
};

const NAV_ITEMS: Array<{
  id: SettingsSection;
  label: string;
  to: string;
  description: string;
}> = [
  { id: "overview", label: "Overview", to: "/settings", description: "Status, warnings, and next actions" },
  { id: "health", label: "Data Health", to: "/settings/health", description: "Segment-level data health" },
  { id: "storage", label: "Storage", to: "/settings/storage", description: "Local paths and data files" },
  { id: "sources", label: "Sources & Imports", to: "/settings/sources", description: "Managed and manual data sources" },
  { id: "updates", label: "Updates", to: "/settings/updates", description: "Database update workflows" },
  { id: "diagnostics", label: "Diagnostics", to: "/settings/diagnostics", description: "Runtime and advanced details" },
];

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
  const navSection = section === "imports" ? "sources" : section === "coverage" ? "health" : section;

  return (
    <section className="space-y-5">
      <PageHeader
        title="Settings"
        subtitle="Local application configuration, data health, storage, sources, updates, and diagnostics."
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
          ) : section === "health" ? (
            <SettingsDataHealth loading={loading} summary={summary} />
          ) : section === "coverage" ? (
            <SettingsNestedPage intro={<CoverageIntro summary={summary} />}>
              <DataCoveragePage />
            </SettingsNestedPage>
          ) : section === "storage" ? (
            <SettingsStorage loading={loading} summary={summary} />
          ) : section === "sources" || section === "imports" ? (
            <SettingsNestedPage intro={<SourcesIntro summary={summary} />}>
              <SettingsGroup
                title="News Sources & Retention"
                subtitle="Local news feeds, RSS/Atom additions, source health, collection runs, and News database retention."
              >
                <NewsSettingsPanel />
              </SettingsGroup>
              <SettingsGroup
                title="Manual Imports"
                subtitle="User-managed import workflows and file-based source tools."
              >
                <UserImportsPage />
              </SettingsGroup>
            </SettingsNestedPage>
          ) : section === "updates" ? (
            <SettingsNestedPage intro={<UpdatesIntro summary={summary} />}>
              <UpdateBasePage />
            </SettingsNestedPage>
          ) : (
            <SettingsNestedPage intro={<DiagnosticsIntro summary={summary} />}>
              <StatusPage />
            </SettingsNestedPage>
          )}
        </main>
      </div>
    </section>
  );
}

function SettingsNav({ current }: { current: SettingsSection }) {
  return (
    <aside className="min-w-0">
      <nav
        aria-label="Settings sections"
        className="grid gap-1 rounded-lg border border-zinc-800 bg-zinc-900/55 p-2 xl:sticky xl:top-4"
      >
        {NAV_ITEMS.map((item) => {
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
              <span className="block text-sm font-medium">{item.label}</span>
              <span className="mt-0.5 block text-[11px] leading-4 text-zinc-500">{item.description}</span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}

function SettingsOverview({
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
      <Panel
        title={summary.summary.title}
        subtitle={summary.summary.message}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <LinkButton to="/settings/health">Open Data Health</LinkButton>
            <LinkButton to="/settings/updates">Update Data</LinkButton>
          </div>
        }
      >
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Metric label="Overall" value={statusLabel(summary.overall_status)} status={summary.overall_status} />
          <Metric label="Critical" value={formatNumber(summary.summary.critical_segments)} status={summary.summary.critical_segments ? "critical" : "healthy"} />
          <Metric label="Degraded" value={formatNumber(summary.summary.degraded_segments)} status={summary.summary.degraded_segments ? "degraded" : "healthy"} />
          <Metric label="Empty" value={formatNumber(summary.summary.empty_segments)} status={summary.summary.empty_segments ? "empty" : "healthy"} />
          <Metric label="Updating" value={formatNumber(summary.summary.updating_segments)} status={summary.summary.updating_segments ? "updating" : "healthy"} />
          <Metric label="Load" value={`${formatNumber(summary.summary.initial_load_duration_ms)} ms`} />
        </div>
        <p className="mt-4 text-xs leading-5 text-zinc-500">
          Initial Settings load uses {formatNumber(summary.summary.initial_bridge_calls)} bridge call. Full coverage and distribution diagnostics are deferred.
        </p>
      </Panel>

      <SettingsStorageOverview summary={summary} />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <Panel
          title="Needs Attention"
          subtitle="Most important data or runtime states first."
          actions={<LinkButton to="/settings/health">View all segments</LinkButton>}
        >
          {attention.length === 0 ? (
            <StateBanner
              variant="success"
              title="No required issues detected"
              message="Required CVM registry and financial statement checks are usable. Optional segment details may still be deferred."
              size="dense"
            />
          ) : (
            <SegmentList segments={attention.slice(0, 5)} compact />
          )}
        </Panel>

        <Panel title="Runtime" subtitle="Effective desktop configuration">
          <dl className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-1">
            <Field label="Version" value={summary.runtime.version} mono />
            <Field label="Mode" value={runtimeModeLabel(summary.runtime.runtime_mode)} />
            <Field label="Write mode" value={summary.runtime.write_mode ?? "unknown"} tone={summary.runtime.write_mode === "read-only" ? "warn" : "neutral"} />
            <Field label="Lock" value={summary.runtime.lock_status?.status ?? "unknown"} mono />
          </dl>
          {summary.runtime.write_mode === "read-only" ? (
            <p className="mt-3 rounded border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
              Write actions are disabled. Diagnostics and local data reads remain available.
            </p>
          ) : null}
        </Panel>
      </div>
    </>
  );
}

function SettingsDataHealth({
  loading,
  summary,
}: {
  loading: boolean;
  summary: SettingsHealthSummary | null;
}) {
  if (loading || !summary) {
    return <StateBanner variant="loading" title="Loading data health..." />;
  }
  return (
    <>
      <Panel
        title="Data Health"
        subtitle="Segment-level status using the fastest available evidence. Expensive coverage details are opened explicitly."
        actions={<LinkButton to="/settings/coverage">Open CVM Coverage</LinkButton>}
      >
        <SegmentList segments={summary.segments} />
      </Panel>
      <Panel title="Status Definitions" subtitle="Canonical vocabulary used in Settings." dense>
        <div className="grid gap-2 md:grid-cols-2">
          {(["healthy", "degraded", "critical", "updating", "empty", "unavailable", "unknown"] as SettingsHealthStatus[]).map((status) => (
            <div key={status} className="rounded border border-zinc-800 bg-zinc-950/45 p-3">
              <StatusBadge status={status}>{statusLabel(status)}</StatusBadge>
              <p className="mt-2 text-xs leading-5 text-zinc-500">{definition(status)}</p>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Metric Provenance" subtitle="Where the summary values come from." dense>
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
    </>
  );
}

function SettingsStorage({
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
    onSuccess: () => {
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
  const scanRunning = inventory?.scan_status?.status === "running" || refreshMutation.data?.scan_status?.status === "running";
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
            disabled={!desktopMode || scanRunning}
            loading={refreshMutation.isPending || scanRunning}
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
        {refreshMutation.error ? (
          <StateBanner
            variant="error"
            title="Could not start storage scan"
            message={refreshMutation.error instanceof Error ? refreshMutation.error.message : String(refreshMutation.error)}
            size="dense"
          />
        ) : null}
      </Panel>

      {inventory ? (
        <>
          <StorageArchitectureSnapshot inventory={inventory} />
          <StorageInventoryDetails inventory={inventory} />
        </>
      ) : null}

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
    </>
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

function SettingsStorageOverview({ summary }: { summary: SettingsHealthSummary }) {
  const storage = summary.storage_inventory;
  if (!storage) {
    return (
      <Panel title="Local Storage" subtitle="Cached inventory summary">
        <StateBanner
          variant="empty"
          title="No storage inventory summary"
          message="Open Storage and refresh inventory to measure local data footprint."
          size="dense"
        />
      </Panel>
    );
  }
  return (
    <Panel
      title="Local Storage"
      subtitle="Cached local data footprint and main data-volume free space."
      actions={<LinkButton to="/settings/storage">View storage details</LinkButton>}
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <Metric label="Local data" value={formatBytes(storage.logical_bytes_total)} status={inventoryStatusForBadge(storage.status)} />
        <Metric label="Free on volume" value={formatBytes(storage.main_volume?.free_bytes)} status={storage.main_volume?.status ?? "unknown"} />
        <Metric label="Largest category" value={storage.largest_category?.label ?? "—"} />
        <Metric label="Growth" value={formatGrowth(storage.growth.change_since_previous_bytes)} />
        <Metric label="Measured" value={formatRelativeAge(storage.scan_age_seconds)} status={storage.is_stale ? "degraded" : "healthy"} />
      </div>
      <p className="mt-4 text-xs leading-5 text-zinc-500">
        Overview reads the latest cached inventory only. It does not start a recursive filesystem scan.
      </p>
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

function CoverageIntro({ summary }: { summary: SettingsHealthSummary | null }) {
  const financial = summary?.segments.find((segment) => segment.id === "cvm_financials");
  return (
    <SectionIntro
      title="Data Health"
      description="CVM coverage details are loaded here only after opening the coverage section."
      segment={financial}
    />
  );
}

function SourcesIntro({ summary }: { summary: SettingsHealthSummary | null }) {
  const plant = summary?.segments.find((segment) => segment.id === "plant_parcels");
  return (
    <SectionIntro
      title="Sources and Imports"
      description="Manual imports and source refresh controls remain here, with bridge write policy enforced by the existing workflows."
      segment={plant}
    />
  );
}

function UpdatesIntro({ summary }: { summary: SettingsHealthSummary | null }) {
  const financial = summary?.segments.find((segment) => segment.id === "cvm_financials");
  return (
    <SectionIntro
      title="Updates"
      description="Database updates are separate from software updates. Write actions are disabled in read-only mode by the bridge."
      segment={financial}
    />
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
            <LinkButton to={segment.action_route}>Open</LinkButton>
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

function canOpenPath(kind: string): boolean {
  return ["data", "database", "output", "logs", "cache"].includes(kind);
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

function formatGrowth(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "No history";
  if (value === 0) return "No change";
  return `${value > 0 ? "+" : ""}${formatBytes(value)}`;
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
