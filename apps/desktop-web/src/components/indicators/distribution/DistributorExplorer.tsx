import { useEffect, useState, useCallback, useMemo } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import { IndicatorControls } from "@/components/indicators/IndicatorControls";
import { IndicatorLegend } from "@/components/indicators/IndicatorLegend";
import type {
  AxisSide,
  ChartAesthetics,
  ChartType,
  IndicatorDef,
  IndicatorSelection,
  IndicatorUnit,
  ResolvedSeries,
} from "@/lib/indicators/types";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  fetchDistributionDistributors,
  fetchDistributionDistributorDetail,
  fetchDistributionSeries,
  fetchDistributionRefreshStatus,
  triggerDistributionRefresh,
  fetchDistributionGroups,
  fetchDistributionGroupDetail,
  exportDistributionExcel,
} from "@/lib/api/distribution";
import type {
  DistributorEntry,
  DistributorDetail,
  DistributionSeriesEntry,
  EconomicGroupEntry,
  EconomicGroupDetail,
} from "@/lib/bridge/types";

export function DistributorExplorer({ bridgeReady }: { bridgeReady: boolean }) {
  const [viewMode, setViewMode] = useState<"distributors" | "groups">("distributors");
  
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("");
  const [selectedUf, setSelectedUf] = useState("");
  const [selected, setSelected] = useState<DistributorEntry | null>(null);
  const [selectedGroupEntry, setSelectedGroupEntry] = useState<EconomicGroupEntry | null>(null);
  
  const [detailTab, setDetailTab] = useState<"market" | "balance" | "quality" | "tariffs" | "delinquency" | "mmgd">("market");
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);

  const queryClient = useQueryClient();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Query distributors list
  const catalogQuery = useQuery({
    queryKey: ["distribution-distributors", debouncedSearch, selectedGroup, selectedUf],
    queryFn: () =>
      fetchDistributionDistributors({
        search: debouncedSearch || undefined,
        economic_group_id: selectedGroup || undefined,
        uf: selectedUf || undefined,
      }),
    enabled: bridgeReady && viewMode === "distributors",
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  });

  const items = catalogQuery.data?.mode !== "browser" ? catalogQuery.data?.items ?? [] : [];
  const count = catalogQuery.data?.mode !== "browser" ? catalogQuery.data?.count ?? 0 : 0;
  const bridgeReason = catalogQuery.data?.mode === "browser" ? catalogQuery.data.reason : null;

  // Query economic groups list
  const groupsQuery = useQuery({
    queryKey: ["distribution-groups"],
    queryFn: () => fetchDistributionGroups(),
    enabled: bridgeReady && viewMode === "groups",
    staleTime: 30_000,
  });

  const groupItems = groupsQuery.data?.mode !== "browser" ? groupsQuery.data?.items ?? [] : [];

  // Sync selected distributor selection
  useEffect(() => {
    if (viewMode === "distributors" && items.length > 0) {
      const stillVisible = selected
        ? items.some((row) => row.distributor_id === selected.distributor_id)
        : false;
      if (!stillVisible) setSelected(items[0]);
    }
  }, [items, selected, viewMode]);

  // Sync selected group selection
  useEffect(() => {
    if (viewMode === "groups" && groupItems.length > 0) {
      const stillVisible = selectedGroupEntry
        ? groupItems.some((row) => row.economic_group_id === selectedGroupEntry.economic_group_id)
        : false;
      if (!stillVisible) setSelectedGroupEntry(groupItems[0]);
    }
  }, [groupItems, selectedGroupEntry, viewMode]);

  // Query selected distributor detail
  const detailQuery = useQuery({
    queryKey: ["distribution-distributor-detail", selected?.distributor_id],
    queryFn: () => fetchDistributionDistributorDetail(selected?.distributor_id ?? ""),
    enabled: bridgeReady && !!selected && viewMode === "distributors",
    staleTime: 30_000,
  });

  const detail = detailQuery.data?.mode !== "browser" ? (detailQuery.data?.detail as DistributorDetail) : null;

  // Query selected distributor series
  const seriesQuery = useQuery({
    queryKey: ["distribution-series", selected?.distributor_id],
    queryFn: () =>
      fetchDistributionSeries({
        entity_type: "distributor",
        entity_id: selected?.distributor_id ?? "",
        frequency: "monthly",
      }),
    enabled: bridgeReady && !!selected && viewMode === "distributors",
    staleTime: 30_000,
  });

  const series = seriesQuery.data?.mode !== "browser" ? seriesQuery.data?.series ?? [] : [];

  // Query selected group detail
  const groupDetailQuery = useQuery({
    queryKey: ["distribution-group-detail", selectedGroupEntry?.economic_group_id],
    queryFn: () => fetchDistributionGroupDetail(selectedGroupEntry?.economic_group_id ?? ""),
    enabled: bridgeReady && !!selectedGroupEntry && viewMode === "groups",
    staleTime: 30_000,
  });

  const groupDetail = groupDetailQuery.data?.mode !== "browser" ? (groupDetailQuery.data?.detail as EconomicGroupDetail) : null;

  // Query selected group series
  const groupSeriesQuery = useQuery({
    queryKey: ["distribution-group-series", selectedGroupEntry?.economic_group_id],
    queryFn: () =>
      fetchDistributionSeries({
        entity_type: "group",
        entity_id: selectedGroupEntry?.economic_group_id ?? "",
        frequency: "monthly",
      }),
    enabled: bridgeReady && !!selectedGroupEntry && viewMode === "groups",
    staleTime: 30_000,
  });

  const groupSeries = groupSeriesQuery.data?.mode !== "browser" ? groupSeriesQuery.data?.series ?? [] : [];

  const handleExcelExport = async () => {
    const entityType = viewMode === "distributors" ? "distributor" : "group";
    const entityId = viewMode === "distributors" ? selected?.distributor_id : selectedGroupEntry?.economic_group_id;
    if (!entityId) return;

    setExporting(true);
    setExportMessage(null);
    try {
      const res = await exportDistributionExcel(entityType, entityId);
      if (res.error) {
        setExportMessage(`⚠️ Export failed: ${res.error}`);
      } else if (res.path) {
        setExportMessage(`✓ Saved to: ${res.path}`);
      }
    } catch (err: any) {
      setExportMessage(`⚠️ Export failed: ${err.message || String(err)}`);
    } finally {
      setExporting(false);
    }
  };

  // Unique UFs and groups from items for filter dropdowns
  const availableUfs = Array.from(new Set(items.map((i) => i.primary_uf).filter(Boolean) as string[])).sort();
  const availableGroups = Array.from(
    new Set(
      items
        .map((i) => (i.economic_group_id ? JSON.stringify({ id: i.economic_group_id, name: i.group_name }) : null))
        .filter(Boolean) as string[]
    )
  )
    .map((str) => JSON.parse(str) as { id: string; name: string })
    .sort((a, b) => a.name.localeCompare(b.name));

  if (!bridgeReady || catalogQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading distributor analytics..." />;
  }
  if (bridgeReason) {
    return <StateBanner variant="browser-only" message={bridgeReason} />;
  }
  if (catalogQuery.isError) {
    const error = catalogQuery.error;
    return (
      <StateBanner
        variant="error"
        title="Could not load distribution database"
        message={error instanceof Error ? error.message : String(error)}
        onRetry={() => {
          void catalogQuery.refetch();
        }}
      />
    );
  }

  const isGroup = viewMode === "groups";
  const activeSeries = isGroup ? groupSeries : series;
  const filteredSeries = activeSeries
    .filter((row) => {
      const metrics = TREND_METRICS[detailTab];
      return metrics.some((metric) => {
        const val = metric.value(row);
        return val !== null && Number.isFinite(val);
      });
    })
    .sort((a, b) => a.period.localeCompare(b.period));

  return (
    <div className="space-y-4">
      {/* Manual Refresh Banner Component */}
      <RefreshBanner queryClient={queryClient} />

      {/* View Mode Toggle */}
      <div className="flex border-b border-zinc-800 gap-2">
        <button
          onClick={() => setViewMode("distributors")}
          className={`px-4 py-2 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
            viewMode === "distributors"
              ? "border-amber-500 text-amber-500 font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          Distributors
        </button>
        <button
          onClick={() => setViewMode("groups")}
          className={`px-4 py-2 text-xs uppercase tracking-wider font-semibold border-b-2 transition-colors ${
            viewMode === "groups"
              ? "border-amber-500 text-amber-500 font-bold"
              : "border-transparent text-zinc-400 hover:text-zinc-200"
          }`}
        >
          Economic Groups
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.5fr_1fr] items-start">
        <div className="space-y-3 min-w-0">
          {viewMode === "distributors" ? (
            <>
              <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 space-y-3">
                <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
                  <Input
                    aria-label="Search distributors"
                    placeholder="Search by distributor name, CNPJ..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                  <div className="text-xs text-zinc-500 whitespace-nowrap font-mono">
                    {items.length} shown · {count} total
                  </div>
                </div>
                <div className="grid gap-2 md:grid-cols-2">
                  <SelectFilter
                    label="Economic Group"
                    value={selectedGroup}
                    options={availableGroups.map((g) => ({ value: g.id, label: g.name }))}
                    onChange={setSelectedGroup}
                  />
                  <SelectFilter
                    label="State (UF)"
                    value={selectedUf}
                    options={availableUfs.map((uf) => ({ value: uf, label: uf }))}
                    onChange={setSelectedUf}
                  />
                </div>
                {(selectedGroup || selectedUf || search) && (
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => {
                      setSearch("");
                      setSelectedGroup("");
                      setSelectedUf("");
                    }}
                  >
                    Clear filters
                  </Button>
                )}
              </div>

              {items.length === 0 ? (
                <StateBanner
                  variant="empty"
                  title="No distributor matches"
                  message="No distributors found matching filters. Trigger a refresh if the database is unseeded."
                />
              ) : (
                <div className="overflow-auto rounded-md border border-zinc-800">
                  <table className="min-w-full text-sm">
                    <thead className="sticky top-0 bg-zinc-950 text-xs uppercase tracking-wide text-zinc-500">
                      <tr>
                        <Th>Distributor</Th>
                        <Th>CNPJ</Th>
                        <Th>UF</Th>
                        <Th>Group</Th>
                        <Th>Listed Link</Th>
                        <Th>Status</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((row) => {
                        const isSelected = selected?.distributor_id === row.distributor_id;
                        return (
                          <tr
                            key={row.distributor_id}
                            className={`cursor-pointer border-t border-zinc-800 hover:bg-zinc-800/40 ${isSelected ? "bg-zinc-800/60" : ""}`}
                            onClick={() => setSelected(row)}
                          >
                            <Td>
                              <div className="font-medium text-zinc-100">{row.canonical_name}</div>
                              <div className="text-xs text-zinc-500 font-mono">{row.trade_name}</div>
                            </Td>
                            <Td mono className="font-mono text-zinc-400">
                              {row.normalized_cnpj
                                ? row.normalized_cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5")
                                : "—"}
                            </Td>
                            <Td mono className="text-center font-mono">
                              {row.primary_uf ?? "—"}
                            </Td>
                            <Td>
                              {row.group_name ? (
                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-zinc-800 text-zinc-200 border border-zinc-700">
                                  {row.group_name}
                                </span>
                              ) : (
                                <span className="text-zinc-500 italic">unmapped</span>
                              )}
                            </Td>
                            <Td>
                              {row.ticker_b3 ? (
                                <span className="font-mono text-amber-500 text-xs font-semibold">
                                  {row.ticker_b3.replace(".SA", "")}
                                </span>
                              ) : (
                                <span className="text-zinc-600">—</span>
                              )}
                            </Td>
                            <Td>
                              <span
                                className={`inline-block w-2 h-2 rounded-full ${row.status === "active" ? "bg-emerald-500" : "bg-zinc-600"}`}
                                title={row.status}
                              />
                            </Td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <>
              {groupItems.length === 0 ? (
                <StateBanner
                  variant="empty"
                  title="No economic groups"
                  message="No economic groups found. Trigger a refresh if the database is unseeded."
                />
              ) : (
                <div className="overflow-auto rounded-md border border-zinc-800">
                  <table className="min-w-full text-sm">
                    <thead className="sticky top-0 bg-zinc-950 text-xs uppercase tracking-wide text-zinc-500">
                      <tr>
                        <Th>Economic Group</Th>
                        <Th>Listed Company Link</Th>
                        <Th>Ticker B3</Th>
                        <Th align="right">Controlled Distributors</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupItems.map((g) => {
                        const isSelected = selectedGroupEntry?.economic_group_id === g.economic_group_id;
                        return (
                          <tr
                            key={g.economic_group_id}
                            className={`cursor-pointer border-t border-zinc-800 hover:bg-zinc-800/40 ${isSelected ? "bg-zinc-800/60" : ""}`}
                            onClick={() => setSelectedGroupEntry(g)}
                          >
                            <Td>
                              <div className="font-medium text-zinc-100">{g.group_name}</div>
                            </Td>
                            <Td>
                              {g.company_name ? (
                                <span className="text-zinc-300">{g.company_name}</span>
                              ) : (
                                <span className="text-zinc-500 italic">No listed linkage</span>
                              )}
                            </Td>
                            <Td>
                              {g.ticker_b3 ? (
                                <span className="font-mono text-amber-500 text-xs font-semibold">
                                  {g.ticker_b3.replace(".SA", "")}
                                </span>
                              ) : (
                                <span className="text-zinc-600">—</span>
                              )}
                            </Td>
                            <Td align="right" mono className="font-mono text-zinc-400">
                              {g.distributors_count}
                            </Td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>

        <div className="min-w-0 xl:sticky xl:top-4 space-y-4">
          {!isGroup && selected && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-4">
              <div className="border-b border-zinc-800 pb-3 flex justify-between items-center">
                <div>
                  <h3 className="text-base font-semibold text-zinc-100">{selected.canonical_name}</h3>
                  <p className="text-xs text-zinc-500 font-mono mt-0.5">ID: {selected.distributor_id}</p>
                </div>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={exporting}
                  onClick={handleExcelExport}
                  className="bg-zinc-850 border-zinc-700 text-zinc-200 hover:bg-zinc-800 font-semibold"
                >
                  {exporting ? "Exporting..." : "Excel Report"}
                </Button>
              </div>

              {exportMessage && (
                <div className={`p-2 rounded text-xs ${exportMessage.startsWith("✓") ? "bg-emerald-950/20 text-emerald-400 border border-emerald-900/30" : "bg-red-950/20 text-red-400 border border-red-900/30"}`}>
                  {exportMessage}
                </div>
              )}

              {detail && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-zinc-500 block">Legal Name</span>
                      <span className="text-zinc-200 block truncate">{detail.identity.legal_name ?? "—"}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 block">CNPJ</span>
                      <span className="text-zinc-200 block font-mono">
                        {detail.identity.normalized_cnpj
                          ? detail.identity.normalized_cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5")
                          : "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-500 block">Agent/Concession Code</span>
                      <span className="text-zinc-200 block font-mono">
                        {detail.identity.agent_code ?? "—"} / {detail.identity.distributor_code ?? "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-500 block">Region (UF)</span>
                      <span className="text-zinc-200 block font-mono">{detail.identity.primary_uf ?? "—"}</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-zinc-500 block">Service Area</span>
                      <span className="text-zinc-200 block whitespace-pre-wrap leading-tight text-justify">
                        {detail.identity.service_area ?? "—"}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-zinc-400 block uppercase tracking-wider">
                      Ownership History
                    </span>
                    {detail.ownership_history.length === 0 ? (
                      <span className="text-xs text-zinc-500 italic block">No control history recorded</span>
                    ) : (
                      <div className="space-y-2 max-h-[120px] overflow-y-auto pr-1">
                        {detail.ownership_history.map((h, i) => (
                          <div
                            key={h.ownership_id || i}
                            className="bg-zinc-950/40 border border-zinc-800/80 rounded p-2 text-xs flex justify-between items-center"
                          >
                            <div>
                              <div className="font-semibold text-zinc-300 font-mono">
                                {h.group_name ?? "Independent/Unmapped"}
                              </div>
                              <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                                {h.valid_from} to {h.valid_to.startsWith("2099") ? "Present" : h.valid_to}
                              </div>
                            </div>
                            <div className="text-right">
                              {h.ownership_percentage !== null && (
                                <div className="font-mono text-zinc-400">{(h.ownership_percentage * 100).toFixed(0)}%</div>
                              )}
                              <div className="text-[10px] text-amber-500 font-mono font-semibold">
                                {h.ticker_b3 ? h.ticker_b3.replace(".SA", "") : ""}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Tabs for different domains */}
              <div className="flex border-b border-zinc-800 overflow-x-auto text-[11px] no-scrollbar">
                {(["market", "balance", "quality", "tariffs", "delinquency", "mmgd"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setDetailTab(tab)}
                    className={`px-2.5 py-1.5 font-medium -mb-px border-b-2 transition-colors whitespace-nowrap capitalize ${
                      detailTab === tab
                        ? "border-amber-500 text-amber-500 font-semibold"
                        : "border-transparent text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {tab === "mmgd" ? "MMGD" : tab === "quality" ? "Quality" : tab.replace("_", " ")}
                  </button>
                ))}
              </div>

              <DistributionTrendPanel series={filteredSeries} activeTab={detailTab} />

              {/* Statistics Table */}
              <div className="space-y-2">
                <div className="flex justify-between items-center text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                  <span>
                    {detailTab === "market" && "Market Stats (Monthly)"}
                    {detailTab === "balance" && "Energy Balance & Losses"}
                    {detailTab === "quality" && "Supply Quality (DEC/FEC)"}
                    {detailTab === "tariffs" && "Homologated Tariffs"}
                    {detailTab === "delinquency" && "Delinquency Metrics"}
                    {detailTab === "mmgd" && "Distributed Generation (MMGD)"}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono normal-case">
                    {detailTab === "market" && "MWh · BRL"}
                    {detailTab === "balance" && "MWh · %"}
                    {detailTab === "quality" && "Hours · Times"}
                    {detailTab === "tariffs" && "R$/MWh · R$/kW"}
                    {detailTab === "delinquency" && "%"}
                    {detailTab === "mmgd" && "Projects · kW"}
                  </span>
                </div>
                {filteredSeries.length === 0 ? (
                  <span className="text-xs text-zinc-500 italic block">No historical records available</span>
                ) : (
                  <div className="overflow-auto rounded border border-zinc-800 max-h-[220px]">
                    <table className="min-w-full text-[11px]">
                      <thead className="sticky top-0 bg-zinc-950 text-zinc-500 font-mono">
                        <tr className="border-b border-zinc-800">
                          <Th className="py-1 px-2">Month</Th>
                          {detailTab === "market" && (
                            <>
                              <Th className="py-1 px-2" align="right">Energy (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Revenue (BRL)</Th>
                              <Th className="py-1 px-2" align="right">Avg Tariff</Th>
                            </>
                          )}
                          {detailTab === "balance" && (
                            <>
                              <Th className="py-1 px-2" align="right">Injected (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Measured (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Losses (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Losses (%)</Th>
                            </>
                          )}
                          {detailTab === "quality" && (
                            <>
                              <Th className="py-1 px-2" align="right">DEC Act</Th>
                              <Th className="py-1 px-2" align="right">DEC Lim</Th>
                              <Th className="py-1 px-2" align="right">FEC Act</Th>
                              <Th className="py-1 px-2" align="right">FEC Lim</Th>
                              <Th className="py-1 px-2" align="right">Comp. Count</Th>
                              <Th className="py-1 px-2" align="right">Comp. Value</Th>
                            </>
                          )}
                          {detailTab === "tariffs" && (
                            <>
                              <Th className="py-1 px-2" align="right">TE (R$/MWh)</Th>
                              <Th className="py-1 px-2" align="right">TUSD (R$/MWh)</Th>
                              <Th className="py-1 px-2" align="right">Demand (R$/kW)</Th>
                            </>
                          )}
                          {detailTab === "delinquency" && (
                            <>
                              <Th className="py-1 px-2" align="right">Delinquency (%)</Th>
                            </>
                          )}
                          {detailTab === "mmgd" && (
                            <>
                              <Th className="py-1 px-2" align="right">Projects</Th>
                              <Th className="py-1 px-2" align="right">Capacity (kW)</Th>
                            </>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSeries.map((row, i) => {
                          const avgTariff =
                            row.revenue_brl && row.billed_energy_mwh
                              ? row.revenue_brl / row.billed_energy_mwh
                              : null;
                          return (
                            <tr key={row.period || i} className="border-t border-zinc-800 hover:bg-zinc-800/20">
                              <Td className="py-1 px-2 font-mono" mono>
                                {row.period}
                              </Td>
                              {detailTab === "market" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.billed_energy_mwh !== null
                                      ? row.billed_energy_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.revenue_brl !== null
                                      ? row.revenue_brl.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {avgTariff !== null
                                      ? `${avgTariff.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/MWh`
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "balance" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.injected_energy_mwh !== null
                                      ? row.injected_energy_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.measured_energy_mwh !== null
                                      ? row.measured_energy_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-red-400" align="right" mono>
                                    {row.losses_mwh !== null
                                      ? row.losses_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.losses_pct !== null
                                      ? `${(row.losses_pct * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "quality" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.dec_actual !== null
                                      ? row.dec_actual.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.dec_limit !== null
                                      ? row.dec_limit.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.fec_actual !== null
                                      ? row.fec_actual.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.fec_limit !== null
                                      ? row.fec_limit.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.compensation_count !== null
                                      ? row.compensation_count.toLocaleString("pt-BR")
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.compensation_value !== null
                                      ? row.compensation_value.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "tariffs" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.te_homologated !== null
                                      ? row.te_homologated.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.tusd_homologated !== null
                                      ? row.tusd_homologated.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    —
                                  </Td>
                                </>
                              )}
                              {detailTab === "delinquency" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.delinquency_pct !== null
                                      ? `${(row.delinquency_pct * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "mmgd" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.mmgd_projects_count !== null
                                      ? row.mmgd_projects_count.toLocaleString("pt-BR")
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.mmgd_capacity_kw !== null
                                      ? row.mmgd_capacity_kw.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                </>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {isGroup && selectedGroupEntry && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 space-y-4">
              <div className="border-b border-zinc-800 pb-3 flex justify-between items-center">
                <div>
                  <h3 className="text-base font-semibold text-zinc-100">{selectedGroupEntry.group_name}</h3>
                  <p className="text-xs text-zinc-500 font-mono mt-0.5">Economic Group</p>
                </div>
                <Button
                  size="xs"
                  variant="secondary"
                  disabled={exporting}
                  onClick={handleExcelExport}
                  className="bg-zinc-850 border-zinc-700 text-zinc-200 hover:bg-zinc-800 font-semibold"
                >
                  {exporting ? "Exporting..." : "Excel Report"}
                </Button>
              </div>

              {exportMessage && (
                <div className={`p-2 rounded text-xs ${exportMessage.startsWith("✓") ? "bg-emerald-950/20 text-emerald-400 border border-emerald-900/30" : "bg-red-950/20 text-red-400 border border-red-900/30"}`}>
                  {exportMessage}
                </div>
              )}

              {groupDetail && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-zinc-500 block">Listed Company</span>
                      <span className="text-zinc-200 block truncate">{groupDetail.identity.company_name ?? "—"}</span>
                    </div>
                    <div>
                      <span className="text-zinc-500 block">Ticker B3</span>
                      <span className="text-zinc-200 block font-mono">
                        {groupDetail.identity.ticker_b3 ? groupDetail.identity.ticker_b3.replace(".SA", "") : "—"}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-500 block">CVM Code</span>
                      <span className="text-zinc-200 block font-mono">{groupDetail.identity.cd_cvm ?? "—"}</span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <span className="text-xs font-semibold text-zinc-400 block uppercase tracking-wider">
                      Portfolio Distributors
                    </span>
                    {groupDetail.portfolio.length === 0 ? (
                      <span className="text-xs text-zinc-500 italic block">No distributors in this group</span>
                    ) : (
                      <div className="space-y-2 max-h-[120px] overflow-y-auto pr-1">
                        {groupDetail.portfolio.map((p, i) => (
                          <div
                            key={p.ownership_id || i}
                            className="bg-zinc-950/40 border border-zinc-800/80 rounded p-2 text-xs flex justify-between items-center"
                          >
                            <div>
                              <div className="font-semibold text-zinc-300 font-mono">{p.canonical_name}</div>
                              <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                                {p.valid_from} to {p.valid_to.startsWith("2099") ? "Present" : p.valid_to}
                              </div>
                            </div>
                            <div className="text-right">
                              {p.ownership_percentage !== null && (
                                <div className="font-mono text-zinc-400">{(p.ownership_percentage * 100).toFixed(0)}%</div>
                              )}
                              <div className="text-[10px] text-amber-500 font-mono font-semibold">
                                {p.control_status}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Tabs for different domains */}
              <div className="flex border-b border-zinc-800 overflow-x-auto text-[11px] no-scrollbar">
                {(["market", "balance", "quality", "tariffs", "delinquency", "mmgd"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setDetailTab(tab as any)}
                    className={`px-2.5 py-1.5 font-medium -mb-px border-b-2 transition-colors whitespace-nowrap capitalize ${
                      detailTab === tab
                        ? "border-amber-500 text-amber-500 font-semibold"
                        : "border-transparent text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    {tab === "mmgd" ? "MMGD" : tab === "quality" ? "Quality" : tab.replace("_", " ")}
                  </button>
                ))}
              </div>

              <DistributionTrendPanel series={filteredSeries} activeTab={detailTab} />

              {/* Statistics Table */}
              <div className="space-y-2">
                <div className="flex justify-between items-center text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                  <span>
                    {detailTab === "market" && "Market Stats (Monthly)"}
                    {detailTab === "balance" && "Energy Balance & Losses"}
                    {detailTab === "quality" && "Supply Quality (DEC/FEC)"}
                    {detailTab === "tariffs" && "Homologated Tariffs"}
                    {detailTab === "delinquency" && "Delinquency Metrics"}
                    {detailTab === "mmgd" && "Distributed Generation (MMGD)"}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono normal-case">
                    {detailTab === "market" && "MWh · BRL"}
                    {detailTab === "balance" && "MWh · %"}
                    {detailTab === "quality" && "Hours · Times"}
                    {detailTab === "tariffs" && "R$/MWh"}
                    {detailTab === "delinquency" && "%"}
                    {detailTab === "mmgd" && "Projects · kW"}
                  </span>
                </div>
                {filteredSeries.length === 0 ? (
                  <span className="text-xs text-zinc-500 italic block">No consolidated records available</span>
                ) : (
                  <div className="overflow-auto rounded border border-zinc-800 max-h-[220px]">
                    <table className="min-w-full text-[11px]">
                      <thead className="sticky top-0 bg-zinc-950 text-zinc-500 font-mono">
                        <tr className="border-b border-zinc-800">
                          <Th className="py-1 px-2">Month</Th>
                          {detailTab === "market" && (
                            <>
                              <Th className="py-1 px-2" align="right">Energy (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Revenue (BRL)</Th>
                              <Th className="py-1 px-2" align="right">Avg Tariff</Th>
                            </>
                          )}
                          {detailTab === "balance" && (
                            <>
                              <Th className="py-1 px-2" align="right">Injected (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Measured (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Losses (MWh)</Th>
                              <Th className="py-1 px-2" align="right">Losses (%)</Th>
                            </>
                          )}
                          {detailTab === "quality" && (
                            <>
                              <Th className="py-1 px-2" align="right">DEC Act</Th>
                              <Th className="py-1 px-2" align="right">DEC Lim</Th>
                              <Th className="py-1 px-2" align="right">FEC Act</Th>
                              <Th className="py-1 px-2" align="right">FEC Lim</Th>
                              <Th className="py-1 px-2" align="right">Comp. Count</Th>
                              <Th className="py-1 px-2" align="right">Comp. Value</Th>
                            </>
                          )}
                          {detailTab === "tariffs" && (
                            <>
                              <Th className="py-1 px-2" align="right">TE</Th>
                              <Th className="py-1 px-2" align="right">TUSD</Th>
                            </>
                          )}
                          {detailTab === "delinquency" && (
                            <>
                              <Th className="py-1 px-2" align="right">Delinquency (%)</Th>
                            </>
                          )}
                          {detailTab === "mmgd" && (
                            <>
                              <Th className="py-1 px-2" align="right">Projects</Th>
                              <Th className="py-1 px-2" align="right">Capacity (kW)</Th>
                            </>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSeries.map((row, i) => {
                          const avgTariff =
                            row.revenue_brl && row.billed_energy_mwh
                              ? row.revenue_brl / row.billed_energy_mwh
                              : null;
                          return (
                            <tr key={row.period || i} className="border-t border-zinc-800 hover:bg-zinc-800/20">
                              <Td className="py-1 px-2 font-mono" mono>
                                {row.period}
                              </Td>
                              {detailTab === "market" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.billed_energy_mwh !== null
                                      ? row.billed_energy_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.revenue_brl !== null
                                      ? row.revenue_brl.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {avgTariff !== null
                                      ? `${avgTariff.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/MWh`
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "balance" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.injected_energy_mwh !== null
                                      ? row.injected_energy_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.measured_energy_mwh !== null
                                      ? row.measured_energy_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-red-400" align="right" mono>
                                    {row.losses_mwh !== null
                                      ? row.losses_mwh.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.losses_pct !== null
                                      ? `${(row.losses_pct * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "quality" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.dec_actual !== null
                                      ? row.dec_actual.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.dec_limit !== null
                                      ? row.dec_limit.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.fec_actual !== null
                                      ? row.fec_actual.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.fec_limit !== null
                                      ? row.fec_limit.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.compensation_count !== null
                                      ? row.compensation_count.toLocaleString("pt-BR")
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.compensation_value !== null
                                      ? row.compensation_value.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "tariffs" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.te_homologated !== null
                                      ? row.te_homologated.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.tusd_homologated !== null
                                      ? row.tusd_homologated.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "delinquency" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.delinquency_pct !== null
                                      ? `${(row.delinquency_pct * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
                                      : "—"}
                                  </Td>
                                </>
                              )}
                              {detailTab === "mmgd" && (
                                <>
                                  <Td className="py-1 px-2" align="right" mono>
                                    {row.mmgd_projects_count !== null
                                      ? row.mmgd_projects_count.toLocaleString("pt-BR")
                                      : "—"}
                                  </Td>
                                  <Td className="py-1 px-2 text-zinc-400" align="right" mono>
                                    {row.mmgd_capacity_kw !== null
                                      ? row.mmgd_capacity_kw.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                                      : "—"}
                                  </Td>
                                </>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RefreshBanner({ queryClient }: { queryClient: any }) {
  const [years, setYears] = useState<number[]>([2024, 2025, 2026]);
  const [triggering, setTriggering] = useState(false);
  const [initialized, setInitialized] = useState(false);

  // Poll refresh status
  const statusQuery = useQuery({
    queryKey: ["distribution-refresh-status"],
    queryFn: fetchDistributionRefreshStatus,
    refetchInterval: (query) => {
      const status = query.state.data?.mode !== "browser" ? query.state.data?.status?.status : "idle";
      return status === "running" ? 1500 : false;
    },
    refetchIntervalInBackground: true,
  });

  const refreshState = statusQuery.data?.mode !== "browser" ? statusQuery.data?.status : null;
  const isRunning = refreshState?.status === "running";

  const supportedYears = refreshState?.supported_years ?? [2024, 2025, 2026];
  const ingestedYears = refreshState?.ingested_years ?? [];

  useEffect(() => {
    if (refreshState?.supported_years && !initialized) {
      const defaultRecent = refreshState.supported_years.filter((y) => y >= 2024);
      setYears(defaultRecent.length > 0 ? defaultRecent : refreshState.supported_years);
      setInitialized(true);
    }
  }, [refreshState?.supported_years, initialized]);

  useEffect(() => {
    if (!isRunning && triggering) {
      setTriggering(false);
      void queryClient.invalidateQueries({ queryKey: ["distribution-distributors"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-groups"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-distributor-detail"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-group-detail"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-series"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-group-series"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-health"] });
      void statusQuery.refetch();
    }
  }, [isRunning, triggering, queryClient]);

  const handleYearToggle = (yr: number) => {
    setYears((prev) => (prev.includes(yr) ? prev.filter((y) => y !== yr) : [...prev, yr].sort()));
  };

  const handleRefresh = async () => {
    if (years.length === 0 || isRunning) return;
    setTriggering(true);
    try {
      await triggerDistributionRefresh({ years });
      void statusQuery.refetch();
    } catch (err) {
      console.error("Refresh trigger failed:", err);
      setTriggering(false);
    }
  };

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 space-y-4">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
        <div>
          <h4 className="text-sm font-semibold text-zinc-200">Manual Ingestion: ANEEL Open Data</h4>
          <p className="text-xs text-zinc-500 mt-0.5">
            Download raw Parquet datasets directly from ANEEL and normalize facts locally.
          </p>
        </div>
        {!isRunning && (
          <Button
            size="xs"
            variant="primary"
            onClick={handleRefresh}
            disabled={triggering || years.length === 0}
            className="bg-amber-600 hover:bg-amber-700 text-white font-semibold self-end md:self-auto"
          >
            {triggering ? "Starting..." : "Trigger Ingestion"}
          </Button>
        )}
        {isRunning && (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse">
            Ingestion In Progress
          </span>
        )}
      </div>

      {!isRunning && (
        <div className="border-t border-zinc-900 pt-3 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-semibold text-zinc-400">Select Market Years:</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setYears(supportedYears)}
                disabled={triggering}
                className="text-[10px] font-semibold text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded px-2 py-0.5 bg-zinc-950/60 hover:bg-zinc-900 transition-colors"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={() => setYears([])}
                disabled={triggering}
                className="text-[10px] font-semibold text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded px-2 py-0.5 bg-zinc-950/60 hover:bg-zinc-900 transition-colors"
              >
                Clear All
              </button>
              <button
                type="button"
                onClick={() => setYears(supportedYears.filter((y) => y >= 2024))}
                disabled={triggering}
                className="text-[10px] font-semibold text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded px-2 py-0.5 bg-zinc-950/60 hover:bg-zinc-900 transition-colors"
              >
                Select Recent
              </button>
            </div>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
            {supportedYears.map((yr) => {
              const isIngested = ingestedYears.includes(yr);
              return (
                <label
                  key={yr}
                  className={`flex items-center justify-between gap-1.5 text-xs px-2 py-1.5 rounded border border-zinc-850 cursor-pointer transition-colors hover:border-zinc-700 ${
                    years.includes(yr)
                      ? "bg-amber-500/5 border-amber-500/30 text-amber-400 font-semibold"
                      : "bg-zinc-900/10 text-zinc-400"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={years.includes(yr)}
                      onChange={() => handleYearToggle(yr)}
                      disabled={triggering}
                      className="accent-amber-500 rounded border-zinc-700 bg-zinc-800"
                    />
                    <span>{yr}</span>
                  </div>
                  {isIngested && (
                    <span className="text-[9px] text-emerald-500 font-semibold font-mono" title="Already ingested/cached">
                      ✓
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        </div>
      )}

      {isRunning && refreshState && (
        <div className="bg-zinc-950/40 rounded border border-zinc-800/80 p-3 space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="text-zinc-400 font-medium">{refreshState.message}</span>
            <span className="text-zinc-500 font-mono">
              {refreshState.progress_current} / {refreshState.progress_total} steps
            </span>
          </div>
          <div className="w-full h-1.5 bg-zinc-850 rounded overflow-hidden">
            <div
              className="h-full bg-amber-500 transition-all duration-300"
              style={{
                width: `${(refreshState.progress_current / (refreshState.progress_total || 1)) * 100}%`,
              }}
            />
          </div>
          <div className="text-[10px] font-mono text-zinc-500">Stage: {refreshState.stage}</div>
        </div>
      )}

      {refreshState && refreshState.status === "error" && (
        <div className="p-2 bg-red-950/20 border border-red-900/30 rounded text-xs text-red-400">
          ⚠️ Refresh failed: {refreshState.error}
        </div>
      )}

      {refreshState && refreshState.status === "success" && !isRunning && (
        <div className="p-2 bg-emerald-950/20 border border-emerald-900/30 rounded text-xs text-emerald-400">
          ✓ {refreshState.message}
        </div>
      )}
    </div>
  );
}

type DistributionTab = "market" | "balance" | "quality" | "tariffs" | "delinquency" | "mmgd";

type TrendMetric = {
  key: keyof DistributionSeriesEntry | "avg_tariff";
  label: string;
  unit: string;
  color: string;
  value: (row: DistributionSeriesEntry) => number | null;
  scaleGroup: string;
  isPercentage?: boolean;
};

const TREND_METRICS: Record<DistributionTab, TrendMetric[]> = {
  market: [
    {
      key: "billed_energy_mwh",
      label: "Billed energy",
      unit: "MWh",
      color: "#38bdf8",
      value: (row) => row.billed_energy_mwh,
      scaleGroup: "mwh",
    },
    {
      key: "revenue_brl",
      label: "Revenue",
      unit: "BRL",
      color: "#f5a524",
      value: (row) => row.revenue_brl,
      scaleGroup: "brl",
    },
  ],
  balance: [
    {
      key: "injected_energy_mwh",
      label: "Injected",
      unit: "MWh",
      color: "#22c55e",
      value: (row) => row.injected_energy_mwh,
      scaleGroup: "mwh",
    },
    {
      key: "losses_mwh",
      label: "Losses",
      unit: "MWh",
      color: "#ef4444",
      value: (row) => row.losses_mwh,
      scaleGroup: "mwh",
    },
    {
      key: "losses_pct",
      label: "Losses %",
      unit: "%",
      color: "#a855f7",
      value: (row) => row.losses_pct,
      scaleGroup: "percent",
      isPercentage: true,
    },
  ],
  quality: [
    {
      key: "dec_actual",
      label: "DEC actual",
      unit: "hours",
      color: "#f5a524",
      value: (row) => row.dec_actual,
      scaleGroup: "dec",
    },
    {
      key: "dec_limit",
      label: "DEC limit",
      unit: "hours",
      color: "#aeb4c0",
      value: (row) => row.dec_limit,
      scaleGroup: "dec",
    },
    {
      key: "fec_actual",
      label: "FEC actual",
      unit: "times",
      color: "#38bdf8",
      value: (row) => row.fec_actual,
      scaleGroup: "fec",
    },
    {
      key: "fec_limit",
      label: "FEC limit",
      unit: "times",
      color: "#64748b",
      value: (row) => row.fec_limit,
      scaleGroup: "fec",
    },
  ],
  tariffs: [
    {
      key: "te_homologated",
      label: "TE",
      unit: "R$/MWh",
      color: "#38bdf8",
      value: (row) => row.te_homologated,
      scaleGroup: "tariff",
    },
    {
      key: "tusd_homologated",
      label: "TUSD",
      unit: "R$/MWh",
      color: "#f5a524",
      value: (row) => row.tusd_homologated,
      scaleGroup: "tariff",
    },
  ],
  delinquency: [
    {
      key: "delinquency_pct",
      label: "Delinquency",
      unit: "%",
      color: "#ef4444",
      value: (row) => row.delinquency_pct,
      scaleGroup: "percent",
      isPercentage: true,
    },
  ],
  mmgd: [
    {
      key: "mmgd_projects_count",
      label: "Projects",
      unit: "projects",
      color: "#38bdf8",
      value: (row) => row.mmgd_projects_count,
      scaleGroup: "projects",
    },
    {
      key: "mmgd_capacity_kw",
      label: "Capacity",
      unit: "kW",
      color: "#22c55e",
      value: (row) => row.mmgd_capacity_kw,
      scaleGroup: "capacity",
    },
  ],
};

function mapMetricUnit(unit: string): IndicatorUnit {
  if (unit === "%") return "pct";
  if (unit === "BRL" || unit === "R$") return "brl";
  if (unit === "MWh" || unit === "kW") return "volume";
  return "number";
}

function DistributionTrendPanel({
  series,
  activeTab,
}: {
  series: DistributionSeriesEntry[];
  activeTab: DistributionTab;
}) {
  const metrics = TREND_METRICS[activeTab];
  const ordered = [...series].sort((a, b) => a.period.localeCompare(b.period));
  const hasValues = ordered.length > 0;

  if (!hasValues) {
    return (
      <div className="rounded border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-500">
        No chart data available for this selection.
      </div>
    );
  }

  // State
  const [selected, setSelected] = useState<IndicatorSelection[]>([]);
  const [chart, setChart] = useState<ChartAesthetics>({
    type: "line",
    smooth: true,
    markers: true,
    legend: true,
    grid: true,
    dataLabels: false,
    indexMode: false,
  });

  useEffect(() => {
    setSelected(
      metrics.map((m) => ({
        id: m.key,
        axis: "auto",
        type: "auto",
      }))
    );
  }, [activeTab, metrics]);

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const exists = prev.some((s) => s.id === id);
      if (exists) {
        return prev.filter((s) => s.id !== id);
      } else {
        return [...prev, { id, axis: "auto", type: "auto" }];
      }
    });
  }, []);

  const setAxis = useCallback((id: string, axis: "auto" | AxisSide) => {
    setSelected((prev) => prev.map((s) => (s.id === id ? { ...s, axis } : s)));
  }, []);

  const setType = useCallback((id: string, type: "auto" | ChartType) => {
    setSelected((prev) => prev.map((s) => (s.id === id ? { ...s, type } : s)));
  }, []);

  const selectionById = useMemo(
    () => new Map(selected.map((s) => [s.id, s])),
    [selected]
  );

  const defs: IndicatorDef[] = useMemo(
    () =>
      metrics.map((m) => ({
        id: m.key,
        label: m.label,
        category: "Distribution",
        unit: mapMetricUnit(m.unit),
        isPlaceholder: false,
        available: true,
      })),
    [metrics]
  );

  const { series: resolvedSeries, periods } = useMemo(() => {
    const sorted = [...series].sort((a, b) => a.period.localeCompare(b.period));
    const periods = sorted.map((row) => row.period);

    const resolved: ResolvedSeries[] = selected
      .map((sel) => {
        const metric = metrics.find((m) => m.key === sel.id);
        if (!metric) return null;

        let points = sorted.map((row) => metric.value(row));

        if (chart.indexMode) {
          const first = points.find((v): v is number => v !== null);
          if (first != null && first !== 0) {
            points = points.map((v) => (v !== null ? v / Math.abs(first) : null));
          }
        }

        const finite = points.filter((v): v is number => v !== null);

        const resolvedType: ChartType =
          sel.type === "auto" ? chart.type : sel.type;

        const resolvedAxis: AxisSide =
          sel.axis === "auto" ? "left" : sel.axis;

        return {
          id: metric.key as string,
          label: metric.label,
          unit: chart.indexMode ? "number" as const : mapMetricUnit(metric.unit),
          color: metric.color,
          type: resolvedType,
          axis: resolvedAxis,
          points,
          latest: finite.length > 0 ? finite[finite.length - 1] : null,
        } satisfies ResolvedSeries;
      })
      .filter((s): s is ResolvedSeries => s !== null);

    return { series: resolved, periods };
  }, [series, selected, chart.indexMode, chart.type, metrics]);

  const showAxisControls = useMemo(
    () => new Set(resolvedSeries.map((s) => s.unit)).size > 1,
    [resolvedSeries]
  );

  const onChartChange = useCallback((patch: Partial<ChartAesthetics>) => {
    setChart((prev) => ({ ...prev, ...patch }));
  }, []);

  return (
    <div className="space-y-3 rounded border border-zinc-800 bg-zinc-950/40 p-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/60 pb-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            Historical chart
          </div>
          <div className="text-[10px] font-mono text-zinc-600">
            {periods[0] ?? ""} to {periods[periods.length - 1] ?? ""}
          </div>
        </div>
      </div>

      <IndicatorControls
        frequency="annual"
        quarterlyAvailable={false}
        onFrequencyChange={() => undefined}
        showFrequency={false}
        itemNoun="Metrics"
        defs={defs}
        selectedIds={selected.map((s) => s.id)}
        onToggleIndicator={toggle}
        maxSelected={6}
        chart={chart}
        onChartChange={onChartChange}
      />

      {resolvedSeries.length === 0 || periods.length === 0 ? (
        <StateBanner
          variant="empty"
          title="Nothing to plot"
          message="Select at least one metric to visualize."
        />
      ) : (
        <IndicatorChart series={resolvedSeries} periods={periods} config={chart} height={180} />
      )}

      {chart.legend && resolvedSeries.length > 0 && (
        <IndicatorLegend
          series={resolvedSeries}
          selectionById={selectionById}
          indexMode={chart.indexMode}
          showAxisControls={showAxisControls}
          onSetAxis={setAxis}
          onSetType={setType}
          onRemove={toggle}
        />
      )}
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
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <span className="text-[10px] uppercase font-semibold text-zinc-500 tracking-wider block">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-zinc-900 border border-zinc-850 rounded px-2 py-1 text-xs text-zinc-200 outline-none focus:border-amber-500"
      >
        <option value="">All</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function Th({
  children,
  align = "left",
  className = "",
}: {
  children: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
}) {
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <th className={`px-3 py-2 text-[10px] font-semibold tracking-wider ${alignClass} ${className}`}>
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  mono = false,
  className = "",
}: {
  children: ReactNode;
  align?: "left" | "right" | "center";
  mono?: boolean;
  className?: string;
}) {
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  const fontClass = mono ? "font-mono" : "";
  return (
    <td className={`px-3 py-2 text-zinc-300 align-middle ${alignClass} ${fontClass} ${className}`}>
      {children}
    </td>
  );
}
