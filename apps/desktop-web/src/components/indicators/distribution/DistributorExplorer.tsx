import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

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

  // Reset detail tab when switching views
  useEffect(() => {
    if (viewMode === "groups" && detailTab === "tariffs") {
      setDetailTab("market");
    }
  }, [viewMode, detailTab]);

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
                {activeSeries.length === 0 ? (
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
                        {activeSeries.map((row, i) => {
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
                {(["market", "balance", "quality", "delinquency", "mmgd"] as const).map((tab) => (
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

              {/* Statistics Table */}
              <div className="space-y-2">
                <div className="flex justify-between items-center text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                  <span>
                    {detailTab === "market" && "Market Stats (Monthly)"}
                    {detailTab === "balance" && "Energy Balance & Losses"}
                    {detailTab === "quality" && "Supply Quality (DEC/FEC)"}
                    {detailTab === "delinquency" && "Delinquency Metrics"}
                    {detailTab === "mmgd" && "Distributed Generation (MMGD)"}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono normal-case">
                    {detailTab === "market" && "MWh · BRL"}
                    {detailTab === "balance" && "MWh · %"}
                    {detailTab === "quality" && "Hours · Times"}
                    {detailTab === "delinquency" && "%"}
                    {detailTab === "mmgd" && "Projects · kW"}
                  </span>
                </div>
                {activeSeries.length === 0 ? (
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
                        {activeSeries.map((row, i) => {
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

  useEffect(() => {
    if (!isRunning && triggering) {
      setTriggering(false);
      // Invalidate queries so tables reload
      void queryClient.invalidateQueries({ queryKey: ["distribution-distributors"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-distributor-detail"] });
      void queryClient.invalidateQueries({ queryKey: ["distribution-series"] });
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
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/20 p-4 space-y-3">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h4 className="text-sm font-semibold text-zinc-200">Manual Ingestion: ANEEL Open Data</h4>
          <p className="text-xs text-zinc-500 mt-0.5">
            Download raw Parquet datasets directly from ANEEL and normalize facts locally.
          </p>
        </div>
        {!isRunning ? (
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {[2024, 2025, 2026].map((yr) => (
                <label key={yr} className="flex items-center gap-1.5 text-xs text-zinc-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={years.includes(yr)}
                    onChange={() => handleYearToggle(yr)}
                    disabled={triggering}
                    className="accent-amber-500 rounded border-zinc-700 bg-zinc-800"
                  />
                  <span>{yr}</span>
                </label>
              ))}
            </div>
            <Button
              size="xs"
              variant="primary"
              onClick={handleRefresh}
              disabled={triggering || years.length === 0}
              className="bg-amber-600 hover:bg-amber-700 text-white font-semibold"
            >
              {triggering ? "Starting..." : "Trigger Refresh"}
            </Button>
          </div>
        ) : (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse">
            Ingestion In Progress
          </span>
        )}
      </div>

      {isRunning && refreshState && (
        <div className="bg-zinc-950/40 rounded border border-zinc-800/80 p-3 space-y-2">
          <div className="flex justify-between items-center text-xs">
            <span className="text-zinc-400 font-medium">{refreshState.message}</span>
            <span className="text-zinc-500 font-mono">
              {refreshState.progress_current} / {refreshState.progress_total} years
            </span>
          </div>
          {/* Progress bar */}
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
