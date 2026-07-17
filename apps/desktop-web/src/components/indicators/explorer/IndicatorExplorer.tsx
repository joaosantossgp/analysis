/**
 * IndicatorExplorer — the Indicator Library list and catalog explorer.
 *
 * Library mode renders one row per named indicator at general/sector/source
 * level. Catalog mode preserves the backend-driven
 * `kpi_catalog` workflow used by Energy > Matrix & Trends.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { keepPreviousData, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import {
  COUNTRY_COLORS,
  COUNTRY_ISO_CODES,
  COUNTRY_LABELS,
  isPctKpi,
} from "@/components/indicators/CountryKpiCharts";
import { IndicatorControls } from "@/components/indicators/IndicatorControls";
import { IndicatorLegend } from "@/components/indicators/IndicatorLegend";
import {
  exportCountryKPIsExcel,
  fetchCountryKPISeries,
  fetchEnergyKPIHealth,
  fetchKPICatalog,
  fetchSINKPIDashboard,
  fetchSINKPISeries,
  triggerEnergyKPIRefresh,
  triggerSINKPIRefresh,
} from "@/lib/api/energyKpis";
import { Checkbox } from "@/components/ui/Checkbox";
import {
  EMPTY_FILTERS,
  buildIndicatorRecords,
  collectFacets,
  filterRecords,
  hasActiveFilters,
  sortRecords,
  type ExplorerFilters,
  type IndicatorRecord,
  type IndicatorSourceGroup,
  type SortKey,
} from "@/lib/indicators/registry";
import {
  EMPTY_INDICATOR_LIBRARY_FILTERS,
  buildIndicatorLibraryRows,
  collectIndicatorLibraryFacets,
  filterIndicatorLibraryRows,
  hasActiveIndicatorLibraryFilters,
  indicatorLibraryFavoriteKey,
  resolveIndicatorLibrarySelection,
  type IndicatorLibraryFacetOption,
  type IndicatorLibraryFilterKey,
  type IndicatorLibraryFilters,
  type IndicatorLibraryRow,
} from "@/lib/indicators/indicatorLibrary";
import {
  DEFAULT_LIBRARY_PANEL_WIDTH,
  MAX_LIBRARY_PANEL_WIDTH,
  MIN_LIBRARY_PANEL_WIDTH,
  calculateLibraryPanelDragWidth,
  calculateLibraryPanelViewportBounds,
  clampLibraryPanelWidth,
} from "@/lib/indicators/libraryPanelLayout";
import type { CountryKPIValue, SINKPIObservation } from "@/lib/bridge/types";
import type {
  AxisSide,
  ChartAesthetics,
  ChartType,
  IndicatorDef,
  IndicatorSelection,
  ResolvedSeries,
} from "@/lib/indicators/types";
import { useFavorites } from "@/lib/indicators/useFavorites";

import { ExplorerStatusStrip } from "./ExplorerStatusStrip";
import { ExplorerToolbar, type FilterDimension } from "./ExplorerToolbar";
import { IndicatorCatalogTable } from "./IndicatorCatalogTable";
import { IndicatorDetailPanel } from "./IndicatorDetailPanel";

type Msg = { text: string; ok: boolean } | null;

type IndicatorExplorerMode = "library" | "catalog";
type LibraryCatalogIssue = {
  variant: "browser-only" | "warning" | "error";
  title: string;
  message?: string;
};
type CountrySeriesQueryResult = Awaited<ReturnType<typeof fetchCountryKPISeries>>;
type SinSeriesQueryResult = Awaited<ReturnType<typeof fetchSINKPISeries>>;

const LIBRARY_PREVIEW_CHART: ChartAesthetics = {
  type: "line",
  smooth: false,
  markers: true,
  legend: true,
  grid: true,
  dataLabels: false,
  indexMode: false,
};

const LIBRARY_SIN_SUBSYSTEMS = [
  { code: "S", label: "South / Sul", color: "#60A5FA" },
  { code: "SE_CO", label: "Southeast-Center West", color: "#22D3EE" },
  { code: "NE", label: "Northeast / Nordeste", color: "#FBBF24" },
  { code: "N", label: "North / Norte", color: "#4ADE80" },
] as const;

const LIBRARY_MAX_SELECTED = 6;
const INDICATOR_LIBRARY_HELP =
  "Central library of macro, sector, system, market, and benchmark indicators that can be opened directly without first selecting a company, asset, plant, parcel, ticker, or economic group.";

function prettyCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function IndicatorExplorer({
  bridgeReady,
  defaultFavoritesOnly = false,
  mode = "catalog",
}: {
  bridgeReady: boolean;
  defaultFavoritesOnly?: boolean;
  mode?: IndicatorExplorerMode;
}) {
  const qc = useQueryClient();

  // ── Explorer view state ───────────────────────────────────────────────────
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<ExplorerFilters>(EMPTY_FILTERS);
  const [favoritesOnly, setFavoritesOnly] = useState(defaultFavoritesOnly);
  const [sort, setSort] = useState<SortKey>("name");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const favorites = useFavorites();

  // ── Refresh state (local-first, explicit) ─────────────────────────────────
  const [refreshingGroup, setRefreshingGroup] = useState<IndicatorSourceGroup | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const seenRunning = useRef(false);
  const shouldLoadValues = mode === "catalog" || mode === "library";

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
    enabled: bridgeReady && shouldLoadValues,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const energyHealthQuery = useQuery({
    queryKey: ["energy-kpi-health"],
    queryFn: () => fetchEnergyKPIHealth(),
    enabled: bridgeReady && shouldLoadValues,
    staleTime: 10_000,
    refetchInterval: refreshingGroup === "energy_country" ? 2_000 : false,
  });
  const sinDashboardQuery = useQuery({
    queryKey: ["sin-kpi-dashboard"],
    queryFn: () => fetchSINKPIDashboard(),
    enabled: bridgeReady && shouldLoadValues,
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
    shouldLoadValues && (seriesQuery.isFetching || energyHealthQuery.isFetching || sinDashboardQuery.isFetching);

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
  if (mode === "library") {
    const catalogIssue: LibraryCatalogIssue | null =
      catalogQuery.data?.mode === "browser"
        ? {
            variant: "browser-only",
            title: "Live catalog unavailable in browser preview",
            message: catalogQuery.data.reason,
          }
        : catalogQuery.isError
          ? {
              variant: "error",
              title: "Live catalog unavailable",
              message:
                catalogQuery.error instanceof Error ? catalogQuery.error.message : String(catalogQuery.error),
            }
          : null;
    return (
      <IndicatorLibraryLanding
        records={records}
        catalogIssue={catalogIssue}
      />
    );
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

function IndicatorLibraryLanding({
  records,
  catalogIssue,
}: {
  records: IndicatorRecord[];
  catalogIssue?: LibraryCatalogIssue | null;
}) {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<IndicatorLibraryFilters>(EMPTY_INDICATOR_LIBRARY_FILTERS);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [panelWidth, setPanelWidth] = useState(DEFAULT_LIBRARY_PANEL_WIDTH);
  const [panelFullscreen, setPanelFullscreen] = useState(false);
  const [resizeDrag, setResizeDrag] = useState<{ startX: number; startWidth: number } | null>(null);
  const [panelViewportBounds, setPanelViewportBounds] = useState<{
    top: number;
    right: number;
    bottom: number;
  } | null>(null);
  const contentBoundsRef = useRef<HTMLDivElement | null>(null);
  const tableFrameRef = useRef<HTMLDivElement | null>(null);
  const favorites = useFavorites();
  const rows = useMemo(() => buildIndicatorLibraryRows(records), [records]);
  const facets = useMemo(() => collectIndicatorLibraryFacets(rows), [rows]);

  const filtered = useMemo(
    () =>
      filterIndicatorLibraryRows(rows, {
        search,
        filters,
        favoritesOnly,
        isFavorite: favorites.isFavorite,
      }),
    [favorites.isFavorite, favoritesOnly, filters, rows, search],
  );

  useEffect(() => {
    if (selectedId !== null && !filtered.some((row) => row.id === selectedId)) {
      setSelectedId(null);
    }
  }, [filtered, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (panelFullscreen) setPanelFullscreen(false);
        else setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [panelFullscreen, selectedId]);

  const selected = useMemo(
    () => (selectedId ? rows.find((row) => row.id === selectedId) ?? null : null),
    [rows, selectedId],
  );
  const panelLayoutStyle = useMemo(
    () => {
      if (!selected || panelFullscreen) return undefined;
      return {
        "--indicator-library-panel-width": `${panelWidth}px`,
        ...(panelViewportBounds
          ? {
              "--indicator-library-panel-top": `${panelViewportBounds.top}px`,
              "--indicator-library-panel-right": `${panelViewportBounds.right}px`,
              "--indicator-library-panel-bottom": `${panelViewportBounds.bottom}px`,
            }
          : null),
      } as CSSProperties;
    },
    [panelFullscreen, panelViewportBounds, panelWidth, selected],
  );

  const updatePanelViewportBounds = useCallback(() => {
    if (!selected || panelFullscreen) return;
    const contentRect = contentBoundsRef.current?.getBoundingClientRect();
    const tableRect = tableFrameRef.current?.getBoundingClientRect();
    const mainRect = tableFrameRef.current?.closest("main")?.getBoundingClientRect();
    if (!contentRect || !tableRect || !mainRect) return;

    const next = calculateLibraryPanelViewportBounds({
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      contentRect,
      mainRect,
      tableRect,
    });
    setPanelViewportBounds((current) =>
      current?.top === next.top && current.right === next.right && current.bottom === next.bottom
        ? current
        : next,
    );
  }, [panelFullscreen, selected]);

  useEffect(() => {
    if (!selected) {
      setPanelFullscreen(false);
      setPanelViewportBounds(null);
    }
  }, [selected]);

  useEffect(() => {
    if (!selected || panelFullscreen) {
      setPanelViewportBounds(null);
      return;
    }

    let frame = 0;
    const scheduleUpdate = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(updatePanelViewportBounds);
    };
    const main = tableFrameRef.current?.closest("main");

    scheduleUpdate();
    window.addEventListener("resize", scheduleUpdate);
    window.addEventListener("scroll", scheduleUpdate, true);
    main?.addEventListener("scroll", scheduleUpdate, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", scheduleUpdate);
      window.removeEventListener("scroll", scheduleUpdate, true);
      main?.removeEventListener("scroll", scheduleUpdate);
    };
  }, [filtered.length, panelFullscreen, panelWidth, selected, updatePanelViewportBounds]);

  useEffect(() => {
    if (!resizeDrag) return;

    const handlePointerMove = (event: PointerEvent) => {
      setPanelWidth(
        calculateLibraryPanelDragWidth({
          startWidth: resizeDrag.startWidth,
          startX: resizeDrag.startX,
          currentX: event.clientX,
        }),
      );
    };
    const handlePointerEnd = () => setResizeDrag(null);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerEnd);
    window.addEventListener("pointercancel", handlePointerEnd);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerEnd);
      window.removeEventListener("pointercancel", handlePointerEnd);
    };
  }, [resizeDrag]);

  const toggleFilter = useCallback((key: IndicatorLibraryFilterKey, value: string) => {
    setFilters((current) => {
      const values = current[key];
      return {
        ...current,
        [key]: values.includes(value) ? values.filter((item) => item !== value) : [...values, value],
      };
    });
  }, []);

  const clearFilters = useCallback(() => {
    setSearch("");
    setFilters(EMPTY_INDICATOR_LIBRARY_FILTERS);
    setFavoritesOnly(false);
  }, []);

  const hasFilters = hasActiveIndicatorLibraryFilters(filters) || favoritesOnly || search.trim().length > 0;

  return (
    <div ref={contentBoundsRef} className="indicator-library-root space-y-3">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-zinc-100">Indicator Library</h1>
            <IndicatorDefinitionHelp definition={INDICATOR_LIBRARY_HELP} name="Indicator Library" />
          </div>
        </div>
        <div className="font-mono text-[11px] text-zinc-500">
          {prettyCount(filtered.length)} / {prettyCount(rows.length)}
        </div>
      </header>

      <div className="space-y-2">
        <input
          aria-label="Search indicators"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search indicator, source, unit..."
          className="h-9 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none focus:border-amber-500"
        />
        <div className="flex flex-wrap items-center gap-2">
          {LIBRARY_FILTERS.map((item) => (
            <LibraryFacetDropdown
              key={item.key}
              label={item.label}
              options={facets[item.key]}
              selected={filters[item.key]}
              onToggle={(value) => toggleFilter(item.key, value)}
            />
          ))}
          <LibraryToggleButton active={favoritesOnly} onClick={() => setFavoritesOnly((value) => !value)}>
            ★ Favorites{favorites.count > 0 ? ` · ${favorites.count}` : ""}
          </LibraryToggleButton>
          {hasFilters ? (
            <button
              type="button"
              onClick={clearFilters}
              className="h-7 rounded-md border border-zinc-800 bg-transparent px-3 font-mono text-xs text-zinc-500 hover:text-zinc-200"
            >
              Clear
            </button>
          ) : null}
        </div>
      </div>

      {catalogIssue ? (
        <StateBanner
          variant={catalogIssue.variant}
          size="dense"
          title={catalogIssue.title}
          message={catalogIssue.message}
        />
      ) : null}

      <div
        className={
          selected && !panelFullscreen
            ? "grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_var(--indicator-library-panel-width)]"
            : "grid items-start gap-3"
        }
        style={panelLayoutStyle}
      >
        <section className="min-w-0">
          {filtered.length === 0 ? (
            <StateBanner
              variant="empty"
              title="No indicators match"
              message="Clear search and filters to return to the full library."
            />
          ) : (
            <div
              ref={tableFrameRef}
              className="indicator-library-table-frame overflow-auto rounded-md border border-zinc-800"
            >
              <table className="min-w-[760px] w-full text-left text-xs">
                <thead className="sticky top-0 bg-zinc-950 text-[10px] uppercase tracking-[0.08em] text-zinc-500">
                  <tr>
                    <th className="px-3 py-2 font-medium">Indicator</th>
                    <th className="px-3 py-2 font-medium">Unit</th>
                    <th className="px-3 py-2 font-medium">Period</th>
                    <th className="px-3 py-2 font-medium">Scope</th>
                    <th className="px-3 py-2 font-medium">Domain</th>
                    <th className="px-3 py-2 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <IndicatorLibraryTableRow
                      key={row.id}
                      row={row}
                      selected={row.id === selectedId}
                      isFavorite={favorites.isFavorite(indicatorLibraryFavoriteKey(row))}
                      onSelect={() =>
                        setSelectedId((current) => resolveIndicatorLibrarySelection(current, row.id))
                      }
                      onToggleFavorite={() => favorites.toggle(indicatorLibraryFavoriteKey(row))}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selected && panelFullscreen ? (
          <button
            type="button"
            aria-label="Exit fullscreen indicator detail backdrop"
            onClick={() => setPanelFullscreen(false)}
            className="fixed inset-0 z-40 cursor-default border-0 bg-black/70"
          />
        ) : null}

        {selected ? (
          <aside
            className={
              panelFullscreen
                ? "fixed inset-3 z-50 min-w-0"
                : "relative min-w-0"
            }
          >
            <div className={panelFullscreen ? "h-full" : "indicator-library-detail-shell"}>
              {!panelFullscreen ? (
                <div
                  role="separator"
                  aria-label="Resize indicator detail panel"
                  aria-orientation="vertical"
                  aria-valuemin={MIN_LIBRARY_PANEL_WIDTH}
                  aria-valuemax={MAX_LIBRARY_PANEL_WIDTH}
                  aria-valuenow={panelWidth}
                  tabIndex={0}
                  title="Drag to resize"
                  onDoubleClick={() => setPanelWidth(DEFAULT_LIBRARY_PANEL_WIDTH)}
                  onKeyDown={(event: ReactKeyboardEvent<HTMLDivElement>) => {
                    const step = event.shiftKey ? 80 : 40;
                    if (event.key === "ArrowLeft") {
                      event.preventDefault();
                      setPanelWidth((current) => clampLibraryPanelWidth(current + step));
                    } else if (event.key === "ArrowRight") {
                      event.preventDefault();
                      setPanelWidth((current) => clampLibraryPanelWidth(current - step));
                    } else if (event.key === "Home") {
                      event.preventDefault();
                      setPanelWidth(MIN_LIBRARY_PANEL_WIDTH);
                    } else if (event.key === "End") {
                      event.preventDefault();
                      setPanelWidth(MAX_LIBRARY_PANEL_WIDTH);
                    }
                  }}
                  onPointerDown={(event: ReactPointerEvent<HTMLDivElement>) => {
                    event.preventDefault();
                    setResizeDrag({ startX: event.clientX, startWidth: panelWidth });
                  }}
                  className="absolute -left-1.5 top-0 hidden h-full w-3 cursor-col-resize items-stretch justify-center rounded-sm outline-none xl:flex"
                >
                  <span
                    aria-hidden="true"
                    className={`my-2 w-px rounded-full ${
                      resizeDrag ? "bg-amber-400" : "bg-zinc-700"
                    }`}
                  />
                </div>
              ) : null}
              <IndicatorLibraryDetailPanel
                row={selected}
                isFavorite={favorites.isFavorite(indicatorLibraryFavoriteKey(selected))}
                onToggleFavorite={() => favorites.toggle(indicatorLibraryFavoriteKey(selected))}
                isFullscreen={panelFullscreen}
                isViewportDocked={!panelFullscreen}
                onToggleFullscreen={() => setPanelFullscreen((value) => !value)}
                onClose={() => {
                  setPanelFullscreen(false);
                  setSelectedId(null);
                }}
              />
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}

const LIBRARY_FILTERS: Array<{ key: IndicatorLibraryFilterKey; label: string }> = [
  { key: "domains", label: "Domain" },
  { key: "sources", label: "Source" },
  { key: "units", label: "Unit" },
  { key: "valueTypes", label: "Type" },
  { key: "statuses", label: "Status" },
];

function LibraryFacetDropdown({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: IndicatorLibraryFacetOption[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const count = selected.length;
  return (
    <div className="relative inline-block">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="h-7 rounded-md border px-3 font-mono text-xs"
        style={{
          background: count > 0 ? "var(--color-surface-3)" : "var(--color-surface-1)",
          borderColor: count > 0 ? "var(--color-action-primary)" : "var(--color-border-default)",
          color: count > 0 ? "var(--color-action-primary)" : "var(--color-text-secondary)",
        }}
      >
        {label}
        {count > 0 ? ` · ${count}` : ""}
        <span aria-hidden="true" className="ml-1 text-zinc-600">
          ▾
        </span>
      </button>
      {open ? (
        <>
          <button
            type="button"
            aria-label={`Close ${label} filter`}
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default border-0 bg-transparent"
          />
          <div
            role="listbox"
            aria-multiselectable="true"
            className="absolute left-0 top-[calc(100%+4px)] z-50 max-h-80 w-64 overflow-auto rounded-md border border-zinc-700 bg-zinc-950 p-2 shadow-lg"
          >
            {options.map((option) => (
              <label
                key={option.key}
                className="flex cursor-pointer items-center justify-between gap-2 rounded px-1 py-1 hover:bg-zinc-900"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <Checkbox checked={selected.includes(option.key)} onChange={() => onToggle(option.key)} />
                  <span className="truncate text-xs text-zinc-200" title={option.label}>
                    {option.label}
                  </span>
                </span>
                <span className="font-mono text-[10px] text-zinc-600">{option.count}</span>
              </label>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

function LibraryToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className="h-7 rounded-md border px-3 font-mono text-xs"
      style={{
        background: active ? "var(--color-surface-3)" : "var(--color-surface-1)",
        borderColor: active ? "var(--color-action-primary)" : "var(--color-border-default)",
        color: active ? "var(--color-action-primary)" : "var(--color-text-secondary)",
      }}
    >
      {children}
    </button>
  );
}

function IndicatorLibraryTableRow({
  row,
  selected,
  isFavorite,
  onSelect,
  onToggleFavorite,
}: {
  row: IndicatorLibraryRow;
  selected: boolean;
  isFavorite: boolean;
  onSelect: () => void;
  onToggleFavorite: () => void;
}) {
  return (
    <tr
      role="button"
      tabIndex={0}
      aria-selected={selected}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className={`border-t border-zinc-800/80 align-top hover:bg-zinc-900/50 ${
        selected ? "bg-zinc-900/80" : "bg-zinc-950/30"
      }`}
    >
      <td className="px-3 py-2">
        <div className="flex min-w-[180px] items-center gap-2">
          <div className="min-w-0 font-medium text-zinc-100">{row.name}</div>
          <IndicatorDefinitionHelp definition={row.description} name={row.name} />
          <button
            type="button"
            aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
            aria-pressed={isFavorite}
            onClick={(event) => {
              event.stopPropagation();
              onToggleFavorite();
            }}
            onKeyDown={(event) => event.stopPropagation()}
            className="text-base leading-none"
            style={{
              background: "transparent",
              border: "none",
              color: isFavorite ? "var(--color-action-primary)" : "var(--color-text-disabled)",
              cursor: "pointer",
              padding: 0,
            }}
          >
            {isFavorite ? "★" : "☆"}
          </button>
        </div>
      </td>
      <td className="px-3 py-2 font-mono text-zinc-300">{row.unit}</td>
      <td className="px-3 py-2 text-zinc-500">{row.period}</td>
      <td className="px-3 py-2 text-zinc-500">{row.scope}</td>
      <td className="px-3 py-2 text-zinc-300">{row.domain}</td>
      <td className="px-3 py-2 text-zinc-500">{row.source}</td>
    </tr>
  );
}

function IndicatorDefinitionHelp({ definition, name }: { definition: string; name: string }) {
  return (
    <button
      type="button"
      aria-label={`${name} definition: ${definition}`}
      title={definition}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-950 font-mono text-[10px] leading-none text-zinc-500 hover:border-zinc-500 hover:text-zinc-200 focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber-400"
    >
      ?
    </button>
  );
}

function IndicatorLibraryDetailPanel({
  row,
  isFavorite,
  onToggleFavorite,
  isFullscreen,
  isViewportDocked,
  onToggleFullscreen,
  onClose,
}: {
  row: IndicatorLibraryRow | null;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  isFullscreen: boolean;
  isViewportDocked: boolean;
  onToggleFullscreen: () => void;
  onClose: () => void;
}) {
  const sourceId = row?.sourceRecordId ?? "";
  const isCountry = row?.previewKind === "country-kpi" && Boolean(sourceId);
  const isSin = row?.previewKind === "sin-kpi" && Boolean(sourceId);

  const countryQuery = useQuery({
    queryKey: ["indicator-library-country-preview", sourceId],
    queryFn: () => fetchCountryKPISeries({ kpi_ids: [sourceId], iso_codes: [...COUNTRY_ISO_CODES] }),
    enabled: isCountry,
    staleTime: 60_000,
  });

  const sinQuery = useQuery({
    queryKey: ["indicator-library-sin-preview", sourceId],
    queryFn: () =>
      fetchSINKPISeries({
        kpi_ids: [sourceId],
        subsystem_codes: ["S", "SE_CO", "NE", "N"],
        limit: 50_000,
      }),
    enabled: isSin,
    staleTime: 60_000,
  });

  if (!row) {
    return (
      <div className="flex min-h-60 items-center justify-center rounded-md border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-600">
        Select an indicator to inspect its definition and chart.
      </div>
    );
  }

  return (
    <div
      className={`space-y-3 rounded-md border border-zinc-800 p-4 ${
        isFullscreen
          ? "h-full overflow-auto bg-zinc-950/95"
          : isViewportDocked
            ? "bg-zinc-950/40 xl:h-full xl:overflow-auto"
            : "bg-zinc-950/40 xl:max-h-[calc(100vh-180px)] xl:overflow-auto"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-base font-semibold text-zinc-100">{row.name}</h2>
          <button
            type="button"
            aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
            aria-pressed={isFavorite}
            onClick={onToggleFavorite}
            className="text-lg leading-none"
            style={{
              background: "transparent",
              border: "none",
              color: isFavorite ? "var(--color-action-primary)" : "var(--color-text-disabled)",
              cursor: "pointer",
              padding: 0,
            }}
          >
            {isFavorite ? "★" : "☆"}
          </button>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            aria-label={isFullscreen ? "Restore indicator detail panel" : "Fullscreen indicator detail panel"}
            aria-pressed={isFullscreen}
            onClick={onToggleFullscreen}
            className="inline-flex h-7 items-center justify-center rounded border border-zinc-800 bg-zinc-950 px-2 font-mono text-[10px] text-zinc-500 hover:border-zinc-600 hover:text-zinc-200"
          >
            {isFullscreen ? "Dock" : "Full"}
          </button>
          <button
            type="button"
            aria-label="Close indicator detail"
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded border border-zinc-800 bg-zinc-950 text-sm text-zinc-500 hover:border-zinc-600 hover:text-zinc-200"
          >
            ×
          </button>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-zinc-300">{row.description}</p>

      <div className="space-y-2">
        <LibraryDetailField label="Unit" value={row.unit} />
        <IndicatorLibraryPreview
          row={row}
          countryQuery={countryQuery}
          sinQuery={sinQuery}
          chartHeight={isFullscreen ? 460 : 300}
        />
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-zinc-800 pt-2">
          <LibraryDetailField label="Source" value={row.source} />
          <LibraryDetailField label="Domain" value={row.domain} />
        </div>
      </div>
    </div>
  );
}

function IndicatorLibraryPreview({
  row,
  countryQuery,
  sinQuery,
  chartHeight,
}: {
  row: IndicatorLibraryRow;
  countryQuery: UseQueryResult<CountrySeriesQueryResult, Error>;
  sinQuery: UseQueryResult<SinSeriesQueryResult, Error>;
  chartHeight: number;
}) {
  const sourceId = row.sourceRecordId ?? "";
  const countryValues = countryQuery.data?.mode === "desktop" ? countryQuery.data.values : [];
  const sinValues = sinQuery.data?.mode === "desktop" ? sinQuery.data.values : [];
  const isCountryPreview = row.sourceGroup === "energy_country";
  const isSinPreview = row.sourceGroup === "sin";
  const [chart, setChart] = useState<ChartAesthetics>(() => ({ ...LIBRARY_PREVIEW_CHART }));
  const [selected, setSelected] = useState<IndicatorSelection[]>([]);
  const seededRowRef = useRef<string | null>(null);

  const defs: IndicatorDef[] = useMemo(() => {
    if (isCountryPreview) {
      return COUNTRY_ISO_CODES.map((iso) => ({
        id: iso,
        label: COUNTRY_LABELS[iso] ?? iso,
        category: "Countries",
        unit: isPctKpi(sourceId) ? ("pct" as const) : ("number" as const),
        isPlaceholder: false,
        available: countryValues.some(
          (value) => value.kpi_id === sourceId && value.iso_code === iso && value.value !== null,
        ),
      }));
    }
    if (isSinPreview) {
      return LIBRARY_SIN_SUBSYSTEMS.map((subsystem) => ({
        id: subsystem.code,
        label: subsystem.label,
        category: "Subsystems",
        unit: isSinPctKpi(sourceId) ? ("pct" as const) : ("number" as const),
        isPlaceholder: false,
        available: sinValues.some(
          (value) =>
            value.kpi_id === sourceId &&
            value.subsystem_code === subsystem.code &&
            value.value !== null,
        ),
      }));
    }
    return [];
  }, [countryValues, isCountryPreview, isSinPreview, sinValues, sourceId]);

  const maxSelected = Math.min(LIBRARY_MAX_SELECTED, Math.max(defs.length, 1));
  const availableDefs = useMemo(() => defs.filter((def) => def.available), [defs]);
  const defsById = useMemo(() => new Map(defs.map((def) => [def.id, def])), [defs]);
  const selectionById = useMemo(() => new Map(selected.map((item) => [item.id, item] as const)), [selected]);
  const plottable = useMemo(
    () => selected.filter((item) => defsById.get(item.id)?.available),
    [defsById, selected],
  );
  const droppedCount = selected.filter((item) => defsById.has(item.id) && !defsById.get(item.id)?.available).length;
  const countryChart = useMemo(
    () => buildCountryPreviewChart(countryValues, sourceId, plottable, chart),
    [chart, countryValues, plottable, sourceId],
  );
  const sinChart = useMemo(
    () => buildSinPreviewChart(sinValues, sourceId, plottable, chart),
    [chart, plottable, sinValues, sourceId],
  );
  const activeChart = isCountryPreview ? countryChart : sinChart;
  const itemNoun = isCountryPreview ? "Countries" : "Subsystems";
  const showAxisControls = useMemo(
    () => new Set(activeChart.series.map((series) => series.unit)).size > 1,
    [activeChart.series],
  );

  useEffect(() => {
    seededRowRef.current = null;
    setSelected([]);
    setChart({ ...LIBRARY_PREVIEW_CHART });
  }, [row.id]);

  useEffect(() => {
    if (seededRowRef.current === row.id || availableDefs.length === 0) return;
    seededRowRef.current = row.id;
    setSelected(
      availableDefs.slice(0, maxSelected).map((def) => ({
        id: def.id,
        axis: "auto",
        type: "auto",
      })),
    );
  }, [availableDefs, maxSelected, row.id]);

  const handleChartChange = useCallback((patch: Partial<ChartAesthetics>) => {
    setChart((current) => ({ ...current, ...patch }));
  }, []);

  function toggleSelection(id: string) {
    const exists = selected.some((item) => item.id === id);
    if (exists) {
      setSelected(selected.filter((item) => item.id !== id));
    } else if (selected.length < maxSelected) {
      setSelected([...selected, { id, axis: "auto", type: "auto" }]);
    }
  }

  function setAxis(id: string, axis: "auto" | AxisSide) {
    setSelected(selected.map((item) => (item.id === id ? { ...item, axis } : item)));
  }

  function setType(id: string, type: "auto" | ChartType) {
    setSelected(selected.map((item) => (item.id === id ? { ...item, type } : item)));
  }

  if (row.previewKind === "none" || !row.sourceRecordId || !row.sourceGroup) {
    return (
      <StateBanner
        variant="empty"
        size="dense"
        title="No local time series available yet"
        message={row.exportUnavailableReason}
      />
    );
  }
  if (row.sourceGroup === "energy_country") {
    if (countryQuery.isLoading) return <StateBanner variant="loading" size="dense" title="Loading cached values…" />;
    if (countryQuery.isError) {
      return <StateBanner variant="error" size="dense" message={String(countryQuery.error)} />;
    }
    if (countryQuery.data?.mode === "browser") {
      return <StateBanner variant="browser-only" size="dense" message={countryQuery.data.reason} />;
    }
    if (countryValues.length === 0) {
      return (
        <StateBanner
          variant="empty"
          size="dense"
          title="No cached rows for this indicator"
          message="Refresh the source from Matrix & Trends before exporting this indicator."
        />
      );
    }
    return (
      <IndicatorLibraryPreviewChart
        chart={chart}
        defs={defs}
        droppedCount={droppedCount}
        itemNoun={itemNoun}
        maxSelected={maxSelected}
        onChartChange={handleChartChange}
        onSetAxis={setAxis}
        onSetType={setType}
        onToggleSelection={toggleSelection}
        chartHeight={chartHeight}
        periods={activeChart.periods}
        selected={selected}
        selectionById={selectionById}
        series={activeChart.series}
        showAxisControls={showAxisControls}
      />
    );
  }

  if (sinQuery.isLoading) return <StateBanner variant="loading" size="dense" title="Loading cached values…" />;
  if (sinQuery.isError) return <StateBanner variant="error" size="dense" message={String(sinQuery.error)} />;
  if (sinQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" size="dense" message={sinQuery.data.reason} />;
  }
  if (sinValues.length === 0) {
    return (
      <StateBanner
        variant="empty"
        size="dense"
        title="No cached rows for this indicator"
        message="Refresh the source from Power System before reviewing this series."
      />
    );
  }
  return (
    <IndicatorLibraryPreviewChart
      chart={chart}
      defs={defs}
      droppedCount={droppedCount}
      itemNoun={itemNoun}
      maxSelected={maxSelected}
      onChartChange={handleChartChange}
      onSetAxis={setAxis}
      onSetType={setType}
      onToggleSelection={toggleSelection}
      chartHeight={chartHeight}
      periods={activeChart.periods}
      selected={selected}
      selectionById={selectionById}
      series={activeChart.series}
      showAxisControls={showAxisControls}
      xTickFormatter={formatShortDateTick}
    />
  );
}

function IndicatorLibraryPreviewChart({
  chart,
  chartHeight,
  defs,
  droppedCount,
  itemNoun,
  maxSelected,
  onChartChange,
  onSetAxis,
  onSetType,
  onToggleSelection,
  series,
  periods,
  selected,
  selectionById,
  showAxisControls,
  xTickFormatter,
}: {
  chart: ChartAesthetics;
  chartHeight: number;
  defs: IndicatorDef[];
  droppedCount: number;
  itemNoun: string;
  maxSelected: number;
  onChartChange: (patch: Partial<ChartAesthetics>) => void;
  onSetAxis: (id: string, axis: "auto" | AxisSide) => void;
  onSetType: (id: string, type: "auto" | ChartType) => void;
  onToggleSelection: (id: string) => void;
  series: ResolvedSeries[];
  periods: string[];
  selected: IndicatorSelection[];
  selectionById: Map<string, IndicatorSelection>;
  showAxisControls: boolean;
  xTickFormatter?: (value: string) => string;
}) {
  return (
    <div className="space-y-2">
      <div className="indicator-library-chart-tools">
        <IndicatorControls
          frequency="annual"
          quarterlyAvailable={false}
          onFrequencyChange={() => undefined}
          showFrequency={false}
          itemNoun={itemNoun}
          defs={defs}
          selectedIds={selected.map((item) => item.id)}
          onToggleIndicator={onToggleSelection}
          maxSelected={maxSelected}
          chart={chart}
          onChartChange={onChartChange}
        />
      </div>

      {droppedCount > 0 ? (
        <p className="m-0 text-xs text-amber-400">
          {droppedCount} selected {droppedCount === 1 ? "series is" : "series are"} unavailable and hidden.
        </p>
      ) : null}

      {series.length === 0 || periods.length === 0 ? (
        <StateBanner
          variant="empty"
          size="dense"
          title="No chartable series"
          message={`Select at least one available ${itemNoun.toLowerCase().replace(/s$/, "")} above.`}
        />
      ) : (
        <IndicatorChart
          series={series}
          periods={periods}
          config={chart}
          height={chartHeight}
          xTickFormatter={xTickFormatter}
        />
      )}

      {chart.legend && series.length > 0 ? (
        <IndicatorLegend
          series={series}
          selectionById={selectionById}
          indexMode={chart.indexMode}
          showAxisControls={showAxisControls}
          onSetAxis={onSetAxis}
          onSetType={onSetType}
          onRemove={onToggleSelection}
        />
      ) : null}
    </div>
  );
}

function LibraryDetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-[0.08em] text-zinc-600">{label}</div>
      <div className="mt-1 break-words font-mono text-xs text-zinc-300">{value || "Unavailable"}</div>
    </div>
  );
}

function buildCountryPreviewChart(
  rows: CountryKPIValue[],
  kpiId: string,
  plottable: IndicatorSelection[],
  chart: ChartAesthetics,
): { series: ResolvedSeries[]; periods: string[] } {
  if (!kpiId) return { series: [], periods: [] };
  const asPct = isPctKpi(kpiId);
  const years = new Set<number>();
  for (const row of rows) {
    if (row.kpi_id === kpiId && row.value !== null) years.add(row.period);
  }
  const sortedYears = [...years].sort((a, b) => a - b);
  if (sortedYears.length === 0 || plottable.length === 0) return { series: [], periods: [] };

  const series: ResolvedSeries[] = plottable.map((selection) => {
    const yearValues = new Map(
      rows
        .filter((row) => row.iso_code === selection.id && row.kpi_id === kpiId)
        .map((row) => [row.period, row.value] as const),
    );
    let points = sortedYears.map((year) => yearValues.get(year) ?? null);
    if (asPct) points = points.map((value) => (value !== null ? value / 100 : null));
    if (chart.indexMode) points = rebaseToBase100(points);
    const finite = points.filter((value): value is number => value !== null);
    return {
      id: selection.id,
      label: COUNTRY_LABELS[selection.id] ?? selection.id,
      unit: chart.indexMode ? "number" : asPct ? "pct" : "number",
      color: COUNTRY_COLORS[selection.id] ?? "#94A3B8",
      type: selection.type === "auto" ? chart.type : selection.type,
      axis: chart.indexMode ? "left" : selection.axis === "auto" ? "left" : selection.axis,
      points,
      latest: finite.length > 0 ? finite[finite.length - 1] : null,
    };
  });

  return { series, periods: sortedYears.map(String) };
}

function buildSinPreviewChart(
  rows: SINKPIObservation[],
  kpiId: string,
  plottable: IndicatorSelection[],
  chart: ChartAesthetics,
): { series: ResolvedSeries[]; periods: string[] } {
  if (!kpiId) return { series: [], periods: [] };
  const isPct = isSinPctKpi(kpiId);
  const valuesBySubsystem = new Map<string, Map<string, { sum: number; count: number }>>();
  const dateSet = new Set<string>();

  for (const row of rows) {
    if (row.kpi_id !== kpiId || row.value === null) continue;
    const date = row.reference_datetime.slice(0, 10);
    dateSet.add(date);
    let subsystemValues = valuesBySubsystem.get(row.subsystem_code);
    if (!subsystemValues) {
      subsystemValues = new Map();
      valuesBySubsystem.set(row.subsystem_code, subsystemValues);
    }
    const current = subsystemValues.get(date);
    if (current) {
      current.sum += row.value;
      current.count += 1;
    } else {
      subsystemValues.set(date, { sum: row.value, count: 1 });
    }
  }

  const dates = [...dateSet].sort().slice(-366);
  if (dates.length === 0 || plottable.length === 0) return { series: [], periods: [] };
  const subsystemsByCode: Map<string, (typeof LIBRARY_SIN_SUBSYSTEMS)[number]> = new Map(
    LIBRARY_SIN_SUBSYSTEMS.map((subsystem) => [subsystem.code, subsystem]),
  );

  const series: ResolvedSeries[] = plottable.flatMap((selection) => {
    const subsystem = subsystemsByCode.get(selection.id);
    if (!subsystem || !valuesBySubsystem.has(subsystem.code)) return [];
    const subsystemValues = valuesBySubsystem.get(subsystem.code)!;
    let points = dates.map((date) => {
      const value = subsystemValues.get(date);
      if (!value) return null;
      const mean = value.sum / value.count;
      return isPct ? mean / 100 : mean;
    });
    if (chart.indexMode) points = rebaseToBase100(points);
    const finite = points.filter((value): value is number => value !== null);
    return [{
      id: subsystem.code,
      label: subsystem.label,
      unit: chart.indexMode ? "number" : isPct ? "pct" : "number",
      color: subsystem.color,
      type: selection.type === "auto" ? chart.type : selection.type,
      axis: chart.indexMode ? "left" : selection.axis === "auto" ? "left" : selection.axis,
      points,
      latest: finite.length > 0 ? finite[finite.length - 1] : null,
    }];
  });

  return { series, periods: dates };
}

function isSinPctKpi(kpiId: string): boolean {
  return kpiId.endsWith("pct") || kpiId.includes("share");
}

function rebaseToBase100(points: Array<number | null>): Array<number | null> {
  const base = points.find((value): value is number => value !== null);
  if (base === undefined || base === 0) return points;
  return points.map((value) => (value === null ? null : (value / base) * 100));
}

function formatShortDateTick(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return value;
  return `${match[3]}/${match[2]}/${match[1].slice(2)}`;
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
