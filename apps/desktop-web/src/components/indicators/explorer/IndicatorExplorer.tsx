/**
 * IndicatorExplorer — the Indicator Library list and catalog explorer.
 *
 * Library mode renders one row per named indicator at general/sector/source
 * level. Catalog mode preserves the backend-driven
 * `kpi_catalog` workflow used by Energy > Matrix & Trends.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { COUNTRY_ISO_CODES } from "@/components/indicators/CountryKpiCharts";
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
  formatLatestValue,
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
  isCountryKpiLibraryRow,
  resolveIndicatorLibrarySelection,
  type IndicatorLibraryAction,
  type IndicatorLibraryEnergySub,
  type IndicatorLibraryFacetOption,
  type IndicatorLibraryFilterKey,
  type IndicatorLibraryFilters,
  type IndicatorLibraryRow,
  type IndicatorLibrarySection,
} from "@/lib/indicators/indicatorLibrary";
import type { CountryKPIValue, SINKPIObservation } from "@/lib/bridge/types";
import { useFavorites } from "@/lib/indicators/useFavorites";

import { ExplorerStatusStrip } from "./ExplorerStatusStrip";
import { ExplorerToolbar, type FilterDimension } from "./ExplorerToolbar";
import { IndicatorCatalogTable } from "./IndicatorCatalogTable";
import { IndicatorDetailPanel } from "./IndicatorDetailPanel";
import { Tag } from "./StatusBadge";

type Msg = { text: string; ok: boolean } | null;

type IndicatorExplorerMode = "library" | "catalog";
type LibraryCatalogIssue = {
  variant: "browser-only" | "warning" | "error";
  title: string;
  message?: string;
};
type CountrySeriesQueryResult = Awaited<ReturnType<typeof fetchCountryKPISeries>>;
type SinSeriesQueryResult = Awaited<ReturnType<typeof fetchSINKPISeries>>;

function prettyCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function IndicatorExplorer({
  bridgeReady,
  defaultFavoritesOnly = false,
  mode = "catalog",
  onOpenSection,
  onOpenEnergySub,
}: {
  bridgeReady: boolean;
  defaultFavoritesOnly?: boolean;
  mode?: IndicatorExplorerMode;
  onOpenSection?: (section: IndicatorLibrarySection) => void;
  onOpenEnergySub?: (sub: IndicatorLibraryEnergySub) => void;
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
  const shouldLoadValues = mode === "catalog";

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
        onOpenSection={onOpenSection}
        onOpenEnergySub={onOpenEnergySub}
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
  onOpenSection,
  onOpenEnergySub,
}: {
  records: IndicatorRecord[];
  catalogIssue?: LibraryCatalogIssue | null;
  onOpenSection?: (section: IndicatorLibrarySection) => void;
  onOpenEnergySub?: (sub: IndicatorLibraryEnergySub) => void;
}) {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<IndicatorLibraryFilters>(EMPTY_INDICATOR_LIBRARY_FILTERS);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
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
      if (event.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedId]);

  const selected = useMemo(
    () => (selectedId ? rows.find((row) => row.id === selectedId) ?? null : null),
    [rows, selectedId],
  );

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
    <div className="space-y-3">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Indicator Library</h1>
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

      {selected ? (
        <IndicatorLibraryDetailPanel
          row={selected}
          isFavorite={favorites.isFavorite(indicatorLibraryFavoriteKey(selected))}
          onToggleFavorite={() => favorites.toggle(indicatorLibraryFavoriteKey(selected))}
          onClose={() => setSelectedId(null)}
          onOpenSection={onOpenSection}
          onOpenEnergySub={onOpenEnergySub}
        />
      ) : null}

      <section className="min-w-0">
        {filtered.length === 0 ? (
          <StateBanner
            variant="empty"
            title="No indicators match"
            message="Clear search and filters to return to the full library."
          />
        ) : (
          <div className="overflow-auto rounded-md border border-zinc-800">
            <table className="min-w-[980px] w-full text-left text-xs">
              <thead className="sticky top-0 bg-zinc-950 text-[10px] uppercase tracking-[0.08em] text-zinc-500">
                <tr>
                  <th className="w-8 px-3 py-2 font-medium" aria-label="Favorite" />
                  <th className="px-3 py-2 font-medium">Indicator</th>
                  <th className="px-3 py-2 font-medium">Definition</th>
                  <th className="px-3 py-2 font-medium">Domain</th>
                  <th className="px-3 py-2 font-medium">Scope</th>
                  <th className="px-3 py-2 font-medium">Unit / period</th>
                  <th className="px-3 py-2 font-medium">Source</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 text-right font-medium">Open</th>
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
                    onOpenSection={onOpenSection}
                    onOpenEnergySub={onOpenEnergySub}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
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
  onOpenSection,
  onOpenEnergySub,
}: {
  row: IndicatorLibraryRow;
  selected: boolean;
  isFavorite: boolean;
  onSelect: () => void;
  onToggleFavorite: () => void;
  onOpenSection?: (section: IndicatorLibrarySection) => void;
  onOpenEnergySub?: (sub: IndicatorLibraryEnergySub) => void;
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
        <button
          type="button"
          aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
          aria-pressed={isFavorite}
          onClick={(event) => {
            event.stopPropagation();
            onToggleFavorite();
          }}
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
      </td>
      <td className="px-3 py-2">
        <div className="font-medium text-zinc-100">{row.name}</div>
        <div className="mt-1 font-mono text-[10px] text-zinc-600">{row.id}</div>
      </td>
      <td className="max-w-[360px] px-3 py-2 text-zinc-400">
        <div
          title={row.description}
          style={{
            display: "-webkit-box",
            overflow: "hidden",
            WebkitBoxOrient: "vertical",
            WebkitLineClamp: 2,
          }}
        >
          {row.description}
        </div>
      </td>
      <td className="px-3 py-2 text-zinc-300">{row.domain}</td>
      <td className="px-3 py-2 text-zinc-500">{row.scope}</td>
      <td className="px-3 py-2">
        <div className="font-mono text-zinc-300">{row.unit}</div>
        <div className="mt-1 text-[11px] text-zinc-600">{row.period}</div>
      </td>
      <td className="px-3 py-2 text-zinc-500">{row.source}</td>
      <td className="px-3 py-2">
        <div className="text-zinc-300">{row.valueType}</div>
        <div className="mt-1 text-[11px] text-zinc-600">{row.status}</div>
      </td>
      <td className="px-3 py-2 text-right">
        <LibraryActionButton
          action={row.action}
          onClickCapture={(event) => event.stopPropagation()}
          onOpenSection={onOpenSection}
          onOpenEnergySub={onOpenEnergySub}
        />
      </td>
    </tr>
  );
}

function LibraryActionButton({
  action,
  onClickCapture,
  onOpenSection,
  onOpenEnergySub,
}: {
  action: IndicatorLibraryAction;
  onClickCapture?: (event: React.MouseEvent<HTMLElement>) => void;
  onOpenSection?: (section: IndicatorLibrarySection) => void;
  onOpenEnergySub?: (sub: IndicatorLibraryEnergySub) => void;
}) {
  const className =
    "inline-flex items-center justify-center rounded border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-800 focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber-400";

  if (action.type === "hash") {
    return (
      <a
        href={action.href}
        className={className}
        aria-label={action.label}
        title={action.label}
        onClick={onClickCapture}
      >
        Open
      </a>
    );
  }

  const disabled = action.type === "energy" ? !onOpenEnergySub : !onOpenSection;
  const handleClick = () => {
    if (action.type === "energy") onOpenEnergySub?.(action.sub);
    else onOpenSection?.(action.section);
  };

  return (
    <button
      type="button"
      className={className}
      disabled={disabled}
      onClick={(event) => {
        onClickCapture?.(event);
        handleClick();
      }}
      aria-label={action.label}
      title={action.label}
      style={{ cursor: disabled ? "not-allowed" : undefined, opacity: disabled ? 0.55 : undefined }}
    >
      Open
    </button>
  );
}

function IndicatorLibraryDetailPanel({
  row,
  isFavorite,
  onToggleFavorite,
  onClose,
  onOpenSection,
  onOpenEnergySub,
}: {
  row: IndicatorLibraryRow | null;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  onClose: () => void;
  onOpenSection?: (section: IndicatorLibrarySection) => void;
  onOpenEnergySub?: (sub: IndicatorLibraryEnergySub) => void;
}) {
  const [exportMsg, setExportMsg] = useState<Msg>(null);
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

  const countryRows = useMemo(() => {
    const values = countryQuery.data?.mode === "desktop" ? countryQuery.data.values : [];
    return latestCountryRows(values, sourceId);
  }, [countryQuery.data, sourceId]);

  const sinRows = useMemo(() => {
    const values = sinQuery.data?.mode === "desktop" ? sinQuery.data.values : [];
    return latestSinRows(values, sourceId);
  }, [sinQuery.data, sourceId]);

  if (!row) {
    return (
      <div className="flex min-h-60 items-center justify-center rounded-md border border-dashed border-zinc-800 p-6 text-center text-sm text-zinc-600">
        Select an indicator to inspect metadata, availability, preview data, and export options.
      </div>
    );
  }

  const exportDisabledReason = exportReason(row, {
    countryLoading: countryQuery.isLoading,
    countryError: countryQuery.isError,
    countryRows: countryRows.length,
  });

  const handleExport = async () => {
    if (exportDisabledReason) return;
    setExportMsg({ text: "Exporting indicator to Excel…", ok: true });
    try {
      const result =
        isCountryKpiLibraryRow(row) && row.sourceRecordId
          ? await exportCountryKPIsExcel({ kpi_ids: [row.sourceRecordId] })
          : { path: null, error: row.exportUnavailableReason ?? "Export is unavailable." };
      setExportMsg(
        result.path
          ? { text: `Exported to ${result.path}`, ok: true }
          : { text: result.error ?? "Export failed.", ok: false },
      );
    } catch (error) {
      setExportMsg({ text: `Export failed: ${String(error)}`, ok: false });
    }
  };

  return (
    <div className="space-y-3 rounded-md border border-zinc-800 bg-zinc-950/40 p-4">
      {exportMsg ? <RefreshMsg msg={exportMsg} onDismiss={() => setExportMsg(null)} /> : null}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-zinc-100">{row.name}</h2>
          <div className="mt-1 font-mono text-[10px] text-zinc-600">{row.id}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
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

      <div className="flex flex-wrap gap-1.5">
        <Tag>{row.domain}</Tag>
        <Tag>{row.source}</Tag>
        <Tag>{row.unit}</Tag>
        <Tag tone="info">{row.valueType}</Tag>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
        <LibraryMeta label="Scope" value={row.scope} />
        <LibraryMeta label="Period" value={row.period} />
        <LibraryMeta label="Status" value={row.status} />
        <LibraryMeta label="Data quality" value={row.dataQuality ?? "Unavailable"} />
        <LibraryMeta label="Coverage" value={coverageLabel(row.coverageStart, row.coverageEnd)} />
        <LibraryMeta label="Last update" value={shortDateTime(row.lastRefreshAt)} />
        <LibraryMeta label="Latest" value={formatLatestValue(row.latestValue ?? null, row.unit)} />
        <LibraryMeta label="Reference" value={row.latestReferenceDate ?? "Unavailable"} />
      </dl>

      <div className="space-y-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-zinc-500">
          Data preview
        </div>
        <IndicatorLibraryPreview
          row={row}
          countryQuery={countryQuery}
          sinQuery={sinQuery}
          countryRows={countryRows}
          sinRows={sinRows}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <LibraryActionButton
          action={row.action}
          onOpenSection={onOpenSection}
          onOpenEnergySub={onOpenEnergySub}
        />
        <button
          type="button"
          disabled={Boolean(exportDisabledReason)}
          onClick={handleExport}
          title={exportDisabledReason ?? "Export this indicator from the local country KPI cache."}
          className="inline-flex h-7 items-center justify-center rounded border px-3 font-mono text-xs"
          style={{
            background: "var(--color-surface-1)",
            borderColor: "var(--color-border-default)",
            color: exportDisabledReason ? "var(--color-text-disabled)" : "var(--color-text-secondary)",
            cursor: exportDisabledReason ? "not-allowed" : "pointer",
            opacity: exportDisabledReason ? 0.65 : 1,
          }}
        >
          Export
        </button>
      </div>
      {exportDisabledReason ? <p className="m-0 text-xs text-zinc-600">{exportDisabledReason}</p> : null}
    </div>
  );
}

function IndicatorLibraryPreview({
  row,
  countryQuery,
  sinQuery,
  countryRows,
  sinRows,
}: {
  row: IndicatorLibraryRow;
  countryQuery: UseQueryResult<CountrySeriesQueryResult, Error>;
  sinQuery: UseQueryResult<SinSeriesQueryResult, Error>;
  countryRows: CountryKPIValue[];
  sinRows: SINKPIObservation[];
}) {
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
    if (countryRows.length === 0) {
      return (
        <StateBanner
          variant="empty"
          size="dense"
          title="No cached rows for this indicator"
          message="Refresh the source from Matrix & Trends before exporting this indicator."
        />
      );
    }
    return <CountryPreviewTable rows={countryRows} />;
  }

  if (sinQuery.isLoading) return <StateBanner variant="loading" size="dense" title="Loading cached values…" />;
  if (sinQuery.isError) return <StateBanner variant="error" size="dense" message={String(sinQuery.error)} />;
  if (sinQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" size="dense" message={sinQuery.data.reason} />;
  }
  if (sinRows.length === 0) {
    return (
      <StateBanner
        variant="empty"
        size="dense"
        title="No cached rows for this indicator"
        message="Refresh the source from Power System before reviewing this series."
      />
    );
  }
  return <SinPreviewTable rows={sinRows} />;
}

function CountryPreviewTable({ rows }: { rows: CountryKPIValue[] }) {
  return (
    <div className="overflow-auto rounded border border-zinc-800">
      <table className="w-full text-left text-xs">
        <thead className="bg-zinc-950 text-[10px] uppercase tracking-[0.08em] text-zinc-500">
          <tr>
            <th className="px-2 py-1.5 font-medium">Country</th>
            <th className="px-2 py-1.5 text-right font-medium">Period</th>
            <th className="px-2 py-1.5 text-right font-medium">Value</th>
            <th className="px-2 py-1.5 font-medium">Quality</th>
            <th className="px-2 py-1.5 font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={`${item.iso_code}-${item.period}`} className="border-t border-zinc-800">
              <td className="px-2 py-1.5 text-zinc-300">{item.country_name || item.iso_code}</td>
              <td className="px-2 py-1.5 text-right font-mono text-zinc-400">{item.period}</td>
              <td className="px-2 py-1.5 text-right font-mono text-zinc-100">
                {formatLatestValue(item.value, item.unit)}
              </td>
              <td className="px-2 py-1.5 text-zinc-500">{item.data_quality_status}</td>
              <td className="px-2 py-1.5 text-zinc-500">{item.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SinPreviewTable({ rows }: { rows: SINKPIObservation[] }) {
  return (
    <div className="overflow-auto rounded border border-zinc-800">
      <table className="w-full text-left text-xs">
        <thead className="bg-zinc-950 text-[10px] uppercase tracking-[0.08em] text-zinc-500">
          <tr>
            <th className="px-2 py-1.5 font-medium">Subsystem</th>
            <th className="px-2 py-1.5 font-medium">Reference</th>
            <th className="px-2 py-1.5 text-right font-medium">Value</th>
            <th className="px-2 py-1.5 font-medium">Quality</th>
            <th className="px-2 py-1.5 font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={`${item.subsystem_code}-${item.reference_datetime}`} className="border-t border-zinc-800">
              <td className="px-2 py-1.5 text-zinc-300">{item.subsystem_name || item.subsystem_code}</td>
              <td className="px-2 py-1.5 font-mono text-zinc-400">{shortDateTime(item.reference_datetime)}</td>
              <td className="px-2 py-1.5 text-right font-mono text-zinc-100">
                {formatLatestValue(item.value, item.unit)}
              </td>
              <td className="px-2 py-1.5 text-zinc-500">{item.data_quality_status}</td>
              <td className="px-2 py-1.5 text-zinc-500">{item.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LibraryMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-[0.08em] text-zinc-600">{label}</dt>
      <dd className="m-0 break-words font-mono text-xs text-zinc-400">{value || "Unavailable"}</dd>
    </div>
  );
}

function exportReason(
  row: IndicatorLibraryRow,
  state: {
    countryLoading: boolean;
    countryError: boolean;
    countryRows: number;
  },
): string | null {
  if (!isCountryKpiLibraryRow(row)) return row.exportUnavailableReason ?? "No export is available for this indicator.";
  if (state.countryLoading) return "Load cached preview rows before exporting.";
  if (state.countryError) return "Cached country series could not be loaded.";
  if (state.countryRows === 0) return "No cached country rows are available for this indicator.";
  return null;
}

function latestCountryRows(rows: CountryKPIValue[], kpiId: string): CountryKPIValue[] {
  const latestByCountry = new Map<string, CountryKPIValue>();
  for (const row of rows) {
    if (row.kpi_id !== kpiId || row.value === null) continue;
    const current = latestByCountry.get(row.iso_code);
    if (!current || row.period > current.period) latestByCountry.set(row.iso_code, row);
  }
  return [...latestByCountry.values()]
    .sort((a, b) => (a.country_name || a.iso_code).localeCompare(b.country_name || b.iso_code))
    .slice(0, 8);
}

function latestSinRows(rows: SINKPIObservation[], kpiId: string): SINKPIObservation[] {
  const order = new Map([
    ["S", 0],
    ["SE_CO", 1],
    ["NE", 2],
    ["N", 3],
  ]);
  const latestBySubsystem = new Map<string, SINKPIObservation>();
  for (const row of rows) {
    if (row.kpi_id !== kpiId || row.value === null) continue;
    const current = latestBySubsystem.get(row.subsystem_code);
    if (!current || row.reference_datetime > current.reference_datetime) {
      latestBySubsystem.set(row.subsystem_code, row);
    }
  }
  return [...latestBySubsystem.values()].sort(
    (a, b) => (order.get(a.subsystem_code) ?? 99) - (order.get(b.subsystem_code) ?? 99),
  );
}

function coverageLabel(start?: string | null, end?: string | null): string {
  if (!start && !end) return "Unavailable";
  return `${start ?? "—"} - ${end ?? "—"}`;
}

function shortDateTime(value?: string | null): string {
  if (!value) return "Unavailable";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "2-digit" });
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
