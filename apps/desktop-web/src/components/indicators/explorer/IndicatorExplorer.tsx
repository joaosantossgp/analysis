/**
 * IndicatorExplorer — the scalable, metadata-driven surface of /indicators.
 *
 * Drives entirely off the backend `kpi_catalog` (via get_kpi_catalog), joined
 * with the cached country/SIN series + health snapshots, then normalised into
 * `IndicatorRecord[]` by the registry. Renders a status strip, a search/filter
 * toolbar, a catalog table (NO charts), and a detail panel that shows full
 * reproducibility metadata plus exactly one lazy preview chart for the selected
 * indicator. Source refreshes stay local-first and explicit.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { COUNTRY_ISO_CODES } from "@/components/indicators/CountryKpiCharts";
import {
  exportCountryKPIsExcel,
  fetchCountryKPISeries,
  fetchEnergyKPIHealth,
  fetchKPICatalog,
  fetchSINKPIDashboard,
  triggerEnergyKPIRefresh,
  triggerSINKPIRefresh,
} from "@/lib/api/energyKpis";
import {
  EMPTY_FILTERS,
  buildIndicatorRecords,
  collectFacets,
  filterRecords,
  hasActiveFilters,
  sortRecords,
  type ExplorerFilters,
  type IndicatorSourceGroup,
  type SortKey,
} from "@/lib/indicators/registry";
import { useFavorites } from "@/lib/indicators/useFavorites";

import { ExplorerStatusStrip } from "./ExplorerStatusStrip";
import { ExplorerToolbar, type FilterDimension } from "./ExplorerToolbar";
import { IndicatorCatalogTable } from "./IndicatorCatalogTable";
import { IndicatorDetailPanel } from "./IndicatorDetailPanel";

type Msg = { text: string; ok: boolean } | null;

export function IndicatorExplorer({ bridgeReady }: { bridgeReady: boolean }) {
  const qc = useQueryClient();

  // ── Explorer view state ───────────────────────────────────────────────────
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<ExplorerFilters>(EMPTY_FILTERS);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("name");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const favorites = useFavorites();

  // ── Refresh state (local-first, explicit) ─────────────────────────────────
  const [refreshingGroup, setRefreshingGroup] = useState<IndicatorSourceGroup | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const seenRunning = useRef(false);

  // ── Queries (all cached local reads) ──────────────────────────────────────
  const catalogQuery = useQuery({
    queryKey: ["energy-kpi-catalog-all"],
    queryFn: () => fetchKPICatalog(),
    enabled: bridgeReady,
    staleTime: 5 * 60_000,
  });
  const seriesQuery = useQuery({
    queryKey: ["country-kpi-all"],
    queryFn: () => fetchCountryKPISeries({ iso_codes: [...COUNTRY_ISO_CODES] }),
    enabled: bridgeReady,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const energyHealthQuery = useQuery({
    queryKey: ["energy-kpi-health"],
    queryFn: () => fetchEnergyKPIHealth(),
    enabled: bridgeReady,
    staleTime: 10_000,
    refetchInterval: refreshingGroup === "energy_country" ? 2_000 : false,
  });
  const sinDashboardQuery = useQuery({
    queryKey: ["sin-kpi-dashboard"],
    queryFn: () => fetchSINKPIDashboard(),
    enabled: bridgeReady,
    staleTime: 30_000,
    refetchInterval: refreshingGroup === "sin" ? 2_000 : false,
  });

  const catalogEntries = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.entries : [];
  const countrySeries = seriesQuery.data?.mode === "desktop" ? seriesQuery.data.values : [];
  const energyHealth = energyHealthQuery.data?.mode === "desktop" ? energyHealthQuery.data.health : null;
  const sinDashboard = sinDashboardQuery.data?.mode === "desktop" ? sinDashboardQuery.data.dashboard : null;
  const sinObservations = sinDashboard?.observations ?? [];

  // ── Build + derive ────────────────────────────────────────────────────────
  const records = useMemo(
    () => buildIndicatorRecords(catalogEntries, { countrySeries, sinObservations, energyHealth, sinDashboard }),
    [catalogEntries, countrySeries, sinObservations, energyHealth, sinDashboard],
  );
  const recordsById = useMemo(() => new Map(records.map((r) => [r.id, r])), [records]);
  const facets = useMemo(() => collectFacets(records), [records]);

  const filtered = useMemo(
    () =>
      filterRecords(records, {
        search,
        filters,
        favoritesOnly,
        isFavorite: favorites.isFavorite,
      }),
    [records, search, filters, favoritesOnly, favorites],
  );
  const sorted = useMemo(() => sortRecords(filtered, sort), [filtered, sort]);

  const selected = selectedId ? recordsById.get(selectedId) ?? null : null;
  const loadingValues =
    seriesQuery.isFetching || energyHealthQuery.isFetching || sinDashboardQuery.isFetching;

  // ── Refresh completion detection (running → idle transition) ──────────────
  useEffect(() => {
    if (!refreshingGroup) return;
    const running =
      refreshingGroup === "sin" ? sinDashboard?.refresh_running : energyHealth?.refresh_running;
    if (running) seenRunning.current = true;
    const done = seenRunning.current && !running;
    if (!done) return;

    seenRunning.current = false;
    const err = refreshingGroup === "sin" ? sinDashboard?.refresh_error : energyHealth?.refresh_error;
    setRefreshingGroup(null);
    if (err) {
      setMsg({ text: `Refresh finished with source issues: ${err}`, ok: false });
    } else {
      setMsg({ text: "Source refreshed — local cache updated.", ok: true });
      setTimeout(() => setMsg(null), 6_000);
    }
    void qc.invalidateQueries({ queryKey: ["country-kpi-all"] });
    void qc.invalidateQueries({ queryKey: ["sin-kpi-dashboard"] });
    void qc.invalidateQueries({ queryKey: ["energy-kpi-health"] });
  }, [energyHealth, sinDashboard, refreshingGroup, qc]);

  const handleRefresh = useCallback(async (group: IndicatorSourceGroup) => {
    setRefreshingGroup(group);
    seenRunning.current = false;
    setMsg({
      text:
        group === "sin"
          ? "Downloading ONS subsystem datasets and attempting CCEE PLD…"
          : "Downloading OWID energy dataset (~7 MB)…",
      ok: true,
    });
    try {
      if (group === "sin") {
        const r = await triggerSINKPIRefresh();
        if (r.mode === "browser") {
          setRefreshingGroup(null);
          setMsg({ text: r.reason, ok: false });
          return;
        }
        const st = r.result.status;
        if (st === "success" || st === "partial" || st === "error") {
          setRefreshingGroup(null);
          setMsg({
            text:
              st === "error"
                ? `Refresh failed: ${r.result.error ?? "unknown error"}`
                : `SIN refresh completed: ${r.result.rows_inserted ?? 0} rows inserted.`,
            ok: st !== "error",
          });
          void qc.invalidateQueries({ queryKey: ["sin-kpi-dashboard"] });
        }
        // started / already_running → completion effect handles it
      } else {
        const r = await triggerEnergyKPIRefresh();
        if (r.mode === "browser") {
          setRefreshingGroup(null);
          setMsg({ text: r.reason, ok: false });
        }
        // energy refresh runs threaded → completion effect handles it
      }
    } catch (e) {
      setRefreshingGroup(null);
      setMsg({ text: `Error: ${String(e)}`, ok: false });
    }
  }, [qc]);

  const handleExport = useCallback(async () => {
    setMsg({ text: "Exporting country KPIs to Excel…", ok: true });
    try {
      const r = await exportCountryKPIsExcel();
      setMsg(
        r.path
          ? { text: `Exported to ${r.path}`, ok: true }
          : { text: r.error ?? "Export failed.", ok: false },
      );
    } catch (e) {
      setMsg({ text: `Export failed: ${String(e)}`, ok: false });
    }
  }, []);

  const toggleFilter = useCallback((dimension: FilterDimension, key: string) => {
    setFilters((f) => {
      const arr = f[dimension];
      return { ...f, [dimension]: arr.includes(key) ? arr.filter((k) => k !== key) : [...arr, key] };
    });
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setFavoritesOnly(false);
  }, []);

  // ── Top-level states ──────────────────────────────────────────────────────
  if (!bridgeReady || catalogQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading indicator catalog…" />;
  }
  if (catalogQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={catalogQuery.data.reason} />;
  }
  if (catalogQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load the indicator catalog"
        message={catalogQuery.error instanceof Error ? catalogQuery.error.message : String(catalogQuery.error)}
        onRetry={() => void catalogQuery.refetch()}
      />
    );
  }
  if (records.length === 0) {
    return (
      <div className="space-y-3">
        {msg ? <RefreshMsg msg={msg} onDismiss={() => setMsg(null)} /> : null}
        <StateBanner
          variant="empty"
          title="Indicator catalog is empty"
          message="No indicators are cached locally yet. Refresh a source to download and populate the catalog. Reads stay offline after the first successful refresh."
        >
          <div className="flex flex-wrap gap-2" style={{ marginTop: 4 }}>
            <FetchButton onClick={() => handleRefresh("energy_country")} busy={refreshingGroup === "energy_country"}>
              Fetch country energy data
            </FetchButton>
            <FetchButton onClick={() => handleRefresh("sin")} busy={refreshingGroup === "sin"}>
              Fetch SIN data
            </FetchButton>
          </div>
        </StateBanner>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {msg ? <RefreshMsg msg={msg} onDismiss={() => setMsg(null)} /> : null}
      {loadingValues ? (
        <StateBanner variant="loading" size="dense" title="Loading cached values…">
          <p style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", margin: 0 }}>
            The catalog is available while local series and cache status finish loading.
          </p>
        </StateBanner>
      ) : null}
      {seriesQuery.isError ? (
        <StateBanner
          variant="warning"
          size="dense"
          title="Series values unavailable"
          message={seriesQuery.error instanceof Error ? seriesQuery.error.message : String(seriesQuery.error)}
        />
      ) : null}

      <ExplorerStatusStrip records={records} />

      <ExplorerToolbar
        search={search}
        onSearchChange={setSearch}
        facets={facets}
        filters={filters}
        onToggleFilter={toggleFilter}
        onClearFilters={clearFilters}
        hasActiveFilters={hasActiveFilters(filters)}
        sort={sort}
        onSortChange={setSort}
        favoritesOnly={favoritesOnly}
        onToggleFavoritesOnly={() => setFavoritesOnly((v) => !v)}
        favoritesCount={favorites.count}
        resultCount={sorted.length}
        totalCount={records.length}
      />

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr] items-start">
        <div className="min-w-0">
          {sorted.length === 0 ? (
            <StateBanner
              variant="empty"
              title="No indicators match"
              message="No indicators match the current search and filters. Clear filters to see the full catalog."
            />
          ) : (
            <IndicatorCatalogTable
              records={sorted}
              selectedId={selectedId}
              onSelect={setSelectedId}
              isFavorite={favorites.isFavorite}
              onToggleFavorite={favorites.toggle}
            />
          )}
        </div>

        <div className="min-w-0 xl:sticky xl:top-4">
          <IndicatorDetailPanel
            record={selected}
            recordsById={recordsById}
            countrySeries={countrySeries}
            sinObservations={sinObservations}
            bridgeReady={bridgeReady}
            isFavorite={favorites.isFavorite}
            onToggleFavorite={favorites.toggle}
            onSelectRelated={setSelectedId}
            onRefresh={handleRefresh}
            refreshingGroup={refreshingGroup}
            onExport={handleExport}
          />
        </div>
      </div>
    </div>
  );
}

function RefreshMsg({ msg, onDismiss }: { msg: NonNullable<Msg>; onDismiss: () => void }) {
  return (
    <div
      className="flex items-center gap-2"
      style={{
        background: msg.ok ? "var(--color-surface-2)" : "var(--color-surface-2)",
        border: `1px solid ${msg.ok ? "var(--color-border-subtle)" : "var(--color-state-err)"}`,
        borderRadius: "var(--radius-md)",
        color: msg.ok ? "var(--color-text-secondary)" : "var(--color-state-err)",
        fontSize: "var(--text-sm)",
        padding: "8px 12px",
      }}
    >
      <span className="min-w-0 flex-1">{msg.text}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss message"
        style={{
          background: "transparent",
          border: "none",
          color: "inherit",
          cursor: "pointer",
          fontSize: "var(--text-sm)",
          padding: "0 4px",
        }}
      >
        ✕
      </button>
    </div>
  );
}

function FetchButton({
  children,
  onClick,
  busy,
}: {
  children: React.ReactNode;
  onClick: () => void;
  busy: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="font-mono focus-visible:outline focus-visible:outline-1"
      style={{
        background: "var(--color-surface-1)",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-md)",
        color: "var(--color-text-secondary)",
        cursor: busy ? "not-allowed" : "pointer",
        fontSize: "var(--text-sm)",
        opacity: busy ? 0.6 : 1,
        outlineColor: "var(--color-border-focus)",
        padding: "6px 12px",
      }}
    >
      {busy ? "Working…" : children}
    </button>
  );
}
