import { useEffect, useMemo, useState, useCallback } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  fetchPlantParcelCatalog,
  fetchPlantParcelDetail,
  fetchPlantParcelSourceStatuses,
  fetchPlantParcelChartData,
} from "@/lib/api/energyKpis";
import type {
  PlantMetric,
  PlantParcelCatalogRecord,
  PlantParcelDetailResponse,
  PlantParcelSourceStatus,
} from "@/lib/bridge/types";
import { IndicatorChart } from "./IndicatorChart";
import { IndicatorControls } from "./IndicatorControls";
import { IndicatorLegend } from "./IndicatorLegend";
import type {
  AxisSide,
  ChartAesthetics,
  ChartType,
  IndicatorDef,
  IndicatorSelection,
  ResolvedSeries,
  IndicatorUnit,
} from "@/lib/indicators/types";

const PAGE_SIZE = 100;
const CCEE_PLANT_ENTITY_TYPE = "ccee_plant_parcel";
const CCEE_PLANT_SOURCE_ID_LIST = [
  "ccee_plant_parcel_monthly",
  "ccee_plant_generation_hourly",
] as const;
const CCEE_PLANT_SOURCE_IDS = new Set<string>(CCEE_PLANT_SOURCE_ID_LIST);

function mapPlantMetricUnit(unit: string, id: string): IndicatorUnit {
  const u = (unit || "").toLowerCase();
  if (u === "%" || u === "pct" || id.toLowerCase().includes("factor") || id.toLowerCase().endsWith("pct")) {
    return "pct";
  }
  if (u === "mw" || u === "mwmed" || u === "gwh" || u === "mwh") {
    return "volume";
  }
  return "number";
}

type Filters = {
  entity_type: string;
  generation_source: string;
  submarket: string;
  uf: string;
};

const EMPTY_FILTERS: Filters = {
  entity_type: "",
  generation_source: "",
  submarket: "",
  uf: "",
};

export function PlantParcelExplorer({ bridgeReady }: { bridgeReady: boolean }) {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<PlantParcelCatalogRecord | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedSearch, filters.generation_source, filters.submarket, filters.uf]);

  const statusQuery = useQuery({
    queryKey: ["plant-parcel-source-statuses", [...CCEE_PLANT_SOURCE_ID_LIST]],
    queryFn: () => fetchPlantParcelSourceStatuses({ source_ids: [...CCEE_PLANT_SOURCE_ID_LIST] }),
    enabled: bridgeReady,
    staleTime: 10_000,
  });

  const catalogQuery = useQuery({
    queryKey: [
      "plant-parcel-catalog",
      CCEE_PLANT_ENTITY_TYPE,
      debouncedSearch,
      filters.generation_source,
      filters.submarket,
      filters.uf,
      offset,
    ],
    queryFn: () =>
      fetchPlantParcelCatalog({
        search: debouncedSearch || undefined,
        entity_type: CCEE_PLANT_ENTITY_TYPE,
        generation_source: filters.generation_source || undefined,
        submarket: filters.submarket || undefined,
        uf: filters.uf || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    enabled: bridgeReady,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const records = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.records : [];
  const catalogResponse = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.response : null;
  const total = catalogResponse?.total ?? 0;
  const facets = catalogResponse?.facets ?? {};
  const statuses = statusQuery.data?.mode === "desktop"
    ? statusQuery.data.statuses.filter((source) => isCceePlantSource(source.source_id))
    : [];
  const statusResponse = statusQuery.data?.mode === "desktop" ? statusQuery.data.response : null;
  const plantJobActive = Boolean(statusResponse?.refresh_running);
  const bridgeReason =
    statusQuery.data?.mode === "browser"
      ? statusQuery.data.reason
      : catalogQuery.data?.mode === "browser"
        ? catalogQuery.data.reason
        : null;

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

  const detailQuery = useQuery({
    queryKey: ["plant-parcel-detail", selected?.entity_type, selected?.entity_id],
    queryFn: () =>
      fetchPlantParcelDetail({
        entity_type: selected?.entity_type,
        entity_id: selected?.entity_id ?? "",
      }),
    enabled: bridgeReady && !!selected,
    staleTime: 30_000,
    refetchInterval: plantJobActive ? 3_000 : false,
    refetchIntervalInBackground: true,
  });

  const detail = detailQuery.data?.mode === "desktop" ? detailQuery.data.detail : null;

  if (!bridgeReady || catalogQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading plant parcel cache..." />;
  }
  if (bridgeReason) {
    return <StateBanner variant="browser-only" message={bridgeReason} />;
  }
  if (catalogQuery.isError) {
    const error = catalogQuery.error;
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
              title="No CCEE plant parcel matches"
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
          <PlantDetailPanel
            selected={selected}
            detail={detail}
            loading={detailQuery.isLoading}
            dataRefreshing={plantJobActive}
          />
        </div>
      </div>
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
      <div className="grid gap-2 md:grid-cols-3">
        <SelectFilter
          label="Generation source"
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
    <div className="w-full max-w-full overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full min-w-[1050px] text-sm">
        <thead className="sticky top-0 bg-zinc-950 text-xs uppercase tracking-wide text-zinc-500">
          <tr>
            <Th>Entity</Th>
            <Th>Plant / Parcel</Th>
            <Th>CEG</Th>
            <Th>Generation source</Th>
            <Th>Owner</Th>
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
                    {row.plant_parcel_code ? `parcel ${row.plant_parcel_code}` : "plant parcel"}
                    {row.plant_parcel_acronym ? ` · ${row.plant_parcel_acronym}` : ""}
                  </div>
                </Td>
                <Td mono>{row.ceg ?? "—"}</Td>
                <Td>{row.generation_source ?? "—"}</Td>
                <Td>
                  {row.owner_name ? (
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium ${
                      row.is_custom_owner 
                        ? "bg-zinc-800/50 text-zinc-350 border border-zinc-700/80" 
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                    }`}>
                      <span>{row.owner_name}</span>
                      {row.owner_ticker && row.owner_ticker !== "Non-Listed" && (
                        <span className="text-[10px] text-amber-500/80 font-mono">({row.owner_ticker})</span>
                      )}
                    </span>
                  ) : (
                    <span className="text-zinc-650 italic">—</span>
                  )}
                </Td>
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


function PlantDetailPanel({
  selected,
  detail,
  loading,
  dataRefreshing,
}: {
  selected: PlantParcelCatalogRecord | null;
  detail: PlantParcelDetailResponse | null;
  loading: boolean;
  dataRefreshing: boolean;
}) {
  const [chartFreq, setChartFreq] = useState<"monthly" | "daily" | "hourly">("monthly");
  const [chartMonth, setChartMonth] = useState<string>("");
  const [selectedSelections, setSelectedSelections] = useState<IndicatorSelection[]>([]);
  const [chart, setChart] = useState<ChartAesthetics>({
    type: "line",
    smooth: true,
    markers: true,
    legend: true,
    grid: true,
    dataLabels: false,
    indexMode: false,
  });

  const toggleSelection = useCallback((id: string) => {
    setSelectedSelections((prev) => {
      const exists = prev.some((s) => s.id === id);
      if (exists) {
        return prev.filter((s) => s.id !== id);
      } else {
        return [...prev, { id, axis: "auto", type: "auto" }];
      }
    });
  }, []);

  const setAxis = useCallback((id: string, axis: "auto" | AxisSide) => {
    setSelectedSelections((prev) => prev.map((s) => (s.id === id ? { ...s, axis } : s)));
  }, []);

  const setType = useCallback((id: string, type: "auto" | ChartType) => {
    setSelectedSelections((prev) => prev.map((s) => (s.id === id ? { ...s, type } : s)));
  }, []);

  const onChartChange = useCallback((patch: Partial<ChartAesthetics>) => {
    setChart((prev) => ({ ...prev, ...patch }));
  }, []);

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
    placeholderData: keepPreviousData,
    refetchInterval: dataRefreshing ? 3_000 : false,
    refetchIntervalInBackground: true,
  });

  const rawSeries = useMemo(() => {
    return chartQuery.data?.mode === "desktop" ? chartQuery.data.data.series : [];
  }, [chartQuery.data]);

  const seriesKey = useMemo(() => {
    return (rawSeries ?? []).map((s: any) => s.id).join(",");
  }, [rawSeries]);

  useEffect(() => {
    if (rawSeries && rawSeries.length > 0) {
      setSelectedSelections(
        rawSeries.map((s: any) => ({
          id: s.id,
          axis: "auto",
          type: "auto",
        }))
      );
    } else {
      setSelectedSelections([]);
    }
  }, [seriesKey]);

  const defs: IndicatorDef[] = useMemo(() => {
    return (rawSeries ?? []).map((s: any) => ({
      id: s.id,
      label: s.label,
      category: "Generation",
      unit: mapPlantMetricUnit(s.unit, s.id),
      isPlaceholder: false,
      available: true,
    }));
  }, [rawSeries]);

  const { series: resolvedSeries, periods: chartPeriods } = useMemo(() => {
    const periods = chartQuery.data?.mode === "desktop" ? chartQuery.data.data.periods : [];

    const resolved: ResolvedSeries[] = selectedSelections
      .map((sel) => {
        const raw = rawSeries.find((s: any) => s.id === sel.id);
        if (!raw) return null;

        let color = raw.color || "#3B82F6";
        if (!raw.color) {
          const colors = ["#22D3EE", "#34D399", "#818CF8", "#FBBF24", "#F87171", "#A78BFA"];
          const idx = rawSeries.findIndex((s: any) => s.id === sel.id);
          color = colors[idx >= 0 ? idx % colors.length : 0];
        }

        let points = raw.points;
        let latest = raw.latest;
        
        const unitFamily = mapPlantMetricUnit(raw.unit, raw.id);
        const isPct = unitFamily === "pct";
        if (isPct) {
          points = raw.points.map((v: number | null) => (v !== null ? v / 100 : null));
          latest = raw.latest !== null ? raw.latest / 100 : null;
        }

        if (chart.indexMode) {
          const first = points.find((v: number | null): v is number => v !== null);
          if (first != null && first !== 0) {
            points = points.map((v: number | null) => (v !== null ? v / Math.abs(first) : null));
          }
        }

        const resolvedType: ChartType =
          sel.type === "auto" ? chart.type : sel.type;

        const resolvedAxis: AxisSide =
          sel.axis === "auto" ? "left" : sel.axis;

        return {
          id: raw.id,
          label: raw.label,
          unit: chart.indexMode ? ("number" as const) : unitFamily,
          color,
          type: resolvedType,
          axis: resolvedAxis,
          points,
          latest,
        } satisfies ResolvedSeries;
      })
      .filter((s): s is ResolvedSeries => s !== null);

    return { series: resolved, periods };
  }, [rawSeries, chartQuery.data, selectedSelections, chart.indexMode, chart.type]);

  if (!selected) {
    return (
      <StateBanner
        variant="empty"
        title="Select a CCEE plant parcel"
        message="The detail panel opens one selected entity at a time and does not render bulk charts."
      />
    );
  }
  if (loading || !detail) {
    return <StateBanner variant="loading" title="Loading selected entity..." />;
  }

  const parcel = detail.parcel ?? {};
  const monthly = detail.monthly_series ?? [];
  const hourly = detail.hourly_preview ?? [];
  const cceeMetrics = (detail.metrics ?? []).filter((metric) => isCceePlantSource(metric.source_id));
  const caveats = (detail.metadata?.caveats ?? []).filter((item: string) => !item.includes("ANEEL"));

  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-4 space-y-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{entityLabel(detail.entity_type)}</p>
        <h3 className="text-base font-semibold text-zinc-100">
          {textValue(parcel, "plant_name") || selected.plant_name || selected.entity_id}
        </h3>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-zinc-500">
          <span className="font-mono">entity {detail.entity_id}</span>
          {textValue(parcel, "plant_parcel_code") ? <span className="font-mono">parcel {textValue(parcel, "plant_parcel_code")}</span> : null}
          {textValue(parcel, "ceg") || selected.ceg ? <span className="font-mono">CEG {textValue(parcel, "ceg") || selected.ceg}</span> : null}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {cceeMetrics.slice(0, 6).map((metric: PlantMetric) => (
          <MetricTile key={metric.metric_id} metric={metric} />
        ))}
      </div>

      {/* Historical Charts */}
      <div className="border-t border-zinc-800 pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs uppercase tracking-wide text-zinc-500 font-semibold">Historical charts</h4>
          
          <div className="flex gap-2">
            <button
              onClick={() => { setChartFreq("monthly"); }}
              className={`rounded px-2 py-0.5 text-xs font-medium border ${chartFreq === "monthly" ? "bg-zinc-850 text-zinc-100 border-zinc-700" : "bg-transparent text-zinc-500 border-transparent hover:text-zinc-300"}`}
            >
              Monthly
            </button>
            <button
              onClick={() => { setChartFreq("daily"); }}
              className={`rounded px-2 py-0.5 text-xs font-medium border ${chartFreq === "daily" ? "bg-zinc-850 text-zinc-100 border-zinc-700" : "bg-transparent text-zinc-500 border-transparent hover:text-zinc-300"}`}
              disabled={months.length === 0}
            >
              Daily
            </button>
            <button
              onClick={() => { setChartFreq("hourly"); }}
              className={`rounded px-2 py-0.5 text-xs font-medium border ${chartFreq === "hourly" ? "bg-zinc-850 text-zinc-100 border-zinc-700" : "bg-transparent text-zinc-500 border-transparent hover:text-zinc-300"}`}
              disabled={months.length === 0}
            >
              Hourly
            </button>
          </div>
        </div>

        <IndicatorControls
          periodValue={chartFreq !== "monthly" ? chartMonth : undefined}
          periodOptions={chartFreq !== "monthly" ? months.map((m) => ({ value: m, label: m })) : undefined}
          onPeriodChange={setChartMonth}
          frequency="annual"
          quarterlyAvailable={false}
          onFrequencyChange={() => undefined}
          showFrequency={false}
          itemNoun="Metrics"
          defs={defs}
          selectedIds={selectedSelections.map((s) => s.id)}
          onToggleIndicator={toggleSelection}
          maxSelected={6}
          chart={chart}
          onChartChange={onChartChange}
        />

        {/* Chart rendering */}
        <div className="relative border border-zinc-850 rounded-md bg-zinc-950/20 p-2 min-h-[240px] flex flex-col justify-center">
          {chartQuery.isLoading ? (
            <div className="text-center text-xs text-zinc-500 py-12">Loading chart data...</div>
          ) : chartQuery.isError ? (
            <div className="text-center text-xs text-red-400 py-12">
              Error: {chartQuery.error instanceof Error ? chartQuery.error.message : String(chartQuery.error)}
            </div>
          ) : resolvedSeries.length === 0 ? (
            <div className="text-center text-xs text-zinc-500 py-12">No data to display. Please refresh the source.</div>
          ) : (
            <div className="space-y-3">
              <IndicatorChart
                series={resolvedSeries}
                periods={chartPeriods}
                config={chart}
                height={220}
              />
              
              {/* Legend */}
              {chart.legend && resolvedSeries.length > 0 && (
                <IndicatorLegend
                  series={resolvedSeries}
                  selectionById={new Map(selectedSelections.map((s) => [s.id, s]))}
                  indexMode={chart.indexMode}
                  showAxisControls={new Set(resolvedSeries.map((s) => s.unit)).size > 1}
                  onSetAxis={setAxis}
                  onSetType={setType}
                  onRemove={toggleSelection}
                />
              )}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <Meta label="Agent" value={textValue(parcel, "agent_name") ?? selected.agent_name ?? "—"} />
        <Meta label="Generation source" value={textValue(parcel, "generation_source") ?? selected.generation_source ?? "—"} />
        <Meta label="Submarket" value={textValue(parcel, "submarket") ?? selected.submarket ?? "—"} mono />
        <Meta label="UF" value={textValue(parcel, "uf") ?? selected.uf ?? "—"} mono />
        <div className="col-span-2 border-t border-zinc-800/60 pt-2">
          <p className="text-[11px] uppercase tracking-wide text-zinc-600">Mapped Owner / Controlling Group</p>
          {detail.owner ? (
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-zinc-200 font-semibold">{detail.owner.owner_name}</span>
              {detail.owner.ticker_b3 && detail.owner.ticker_b3 !== "Non-Listed" && (
                <span className="font-mono text-amber-500 text-[10.5px] font-semibold bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded">
                  {detail.owner.ticker_b3.replace(".SA", "")}
                </span>
              )}
              {detail.owner.is_custom && (
                <span className="px-1.5 py-0.5 text-[9px] font-semibold bg-zinc-800 text-zinc-400 rounded border border-zinc-700">
                  Non-Listed
                </span>
              )}
            </div>
          ) : (
            <span className="text-xs text-zinc-500 italic block mt-0.5">unmapped / loose</span>
          )}
        </div>
      </div>

      <MethodologyList metrics={cceeMetrics} />

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
        {caveats.map((item: string) => (
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



function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-zinc-600">{label}</p>
      <p className={`truncate text-xs text-zinc-300 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
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
  if (entityType === "aneel_plant") return "Plant";
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



function isCceePlantSource(sourceId: string): boolean {
  return CCEE_PLANT_SOURCE_IDS.has(sourceId);
}



function emptyCatalogMessage(statuses: PlantParcelSourceStatus[]): string {
  if (statuses.some((source) => source.last_error || source.cache_status === "failed")) {
    return "The latest source refresh failed. Check the source card error, then refresh again.";
  }
  if (statuses.some((source) => source.last_warning || source.cache_status === "warning")) {
    return "The latest refresh imported no rows. Check the source warning or choose another period.";
  }
  if (statuses.every((source) => source.cache_status === "never_refreshed")) {
    return "Refresh CCEE monthly data to populate the local plant parcel catalog.";
  }
  return "Refresh CCEE monthly data, or clear the current search and filters.";
}
