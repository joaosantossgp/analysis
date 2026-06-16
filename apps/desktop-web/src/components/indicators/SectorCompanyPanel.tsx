import { useState, useMemo, Fragment } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { CvmRegistryEntry } from "@/lib/bridge/types";
import {
  fetchConglomerates,
  fetchAssetMappings,
  updateAssetMapping,
  runAutomaticMapping,
  fetchCompanyUniverse,
} from "@/lib/api/distribution";

export function SectorCompanyPanel({ bridgeReady }: { bridgeReady: boolean }) {
  const [activeTab, setActiveTab] = useState<"universe" | "groups" | "links">("universe");
  const [searchQuery, setSearchQuery] = useState("");
  const [assetTypeFilter, setAssetTypeFilter] = useState<"all" | "distributor" | "plant">("all");
  const [mappingSourceFilter, setMappingSourceFilter] = useState<"all" | "auto" | "manual" | "unmapped">("all");
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  
  // Expanded conglomerate row IDs (use strings to support custom:Name format)
  const [expandedRowIds, setExpandedRowIds] = useState<Set<string>>(new Set());

  // Pending updates mapping (for loading state during change)
  const [updatingAssetKeys, setUpdatingAssetKeys] = useState<Set<string>>(new Set());
  const [runningAutoMatcher, setRunningAutoMatcher] = useState(false);
  const [autoMatcherMessage, setAutoMatcherMessage] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // Queries
  const conglomeratesQuery = useQuery({
    queryKey: ["conglomerates"],
    queryFn: fetchConglomerates,
    enabled: bridgeReady,
    staleTime: 30_000,
  });

  const mappingsQuery = useQuery({
    queryKey: ["asset-mappings"],
    queryFn: fetchAssetMappings,
    enabled: bridgeReady,
    staleTime: 30_000,
  });

  const universeQuery = useQuery({
    queryKey: ["company-universe"],
    queryFn: fetchCompanyUniverse,
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const conglomerates = conglomeratesQuery.data?.mode === "desktop" ? conglomeratesQuery.data.items : [];
  const assets = mappingsQuery.data?.mode === "desktop" ? mappingsQuery.data.items : [];
  const universeCompanies: CvmRegistryEntry[] = universeQuery.data?.mode === "desktop" ? universeQuery.data.items : [];

  // Extract unique custom owner names from conglomerates
  const customOwnersList = useMemo(() => {
    return conglomerates.filter((c) => !c.is_listed).map((c) => c.company_name);
  }, [conglomerates]);

  const isLoading = conglomeratesQuery.isLoading || mappingsQuery.isLoading;
  const isError = conglomeratesQuery.isError || mappingsQuery.isError;
  const error = conglomeratesQuery.error ?? mappingsQuery.error;

  // Universe pagination + filters — uses shared searchQuery from nav bar
  const [universeConnectedOnly, setUniverseConnectedOnly] = useState(false);
  const [universePage, setUniversePage] = useState(1);
  const UNIVERSE_PAGE_SIZE = 100;

  const filteredUniverse = useMemo(() => {
    const q = searchQuery.toLowerCase();
    return universeCompanies.filter((c) => {
      const matchSearch =
        !q ||
        c.company_name.toLowerCase().includes(q) ||
        (c.ticker_b3 ?? "").toLowerCase().includes(q) ||
        (c.cnpj ?? "").includes(q) ||
        (c.setor_cvm ?? "").toLowerCase().includes(q) ||
        (c.gics_sector ?? "").toLowerCase().includes(q);
      const matchConnected =
        !universeConnectedOnly ||
        c.has_financials ||
        c.mapped_distributors > 0 ||
        c.mapped_plants > 0;
      return matchSearch && matchConnected;
    });
  }, [universeCompanies, searchQuery, universeConnectedOnly]);

  const universeTotalPages = Math.max(1, Math.ceil(filteredUniverse.length / UNIVERSE_PAGE_SIZE));
  const universeValidPage = Math.min(universePage, universeTotalPages);
  const paginatedUniverse = useMemo(() => {
    const start = (universeValidPage - 1) * UNIVERSE_PAGE_SIZE;
    return filteredUniverse.slice(start, start + UNIVERSE_PAGE_SIZE);
  }, [filteredUniverse, universeValidPage, UNIVERSE_PAGE_SIZE]);

  const toggleExpand = (rowId: string) => {
    setExpandedRowIds((prev) => {
      const next = new Set(prev);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  };

  const handleMappingChange = async (
    assetId: string,
    assetType: "distributor" | "plant",
    newCvm: number | null,
    customOwnerName?: string | null
  ) => {
    const key = `${assetId}-${assetType}`;
    setUpdatingAssetKeys((prev) => new Set([...prev, key]));
    try {
      const res = await updateAssetMapping(assetId, assetType, newCvm, customOwnerName);
      if (res.success) {
        void queryClient.invalidateQueries({ queryKey: ["conglomerates"] });
        void queryClient.invalidateQueries({ queryKey: ["asset-mappings"] });
      } else if (res.error) {
        alert(`Failed to update mapping: ${res.error}`);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setUpdatingAssetKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  const handleRunAutoMatcher = async () => {
    setRunningAutoMatcher(true);
    setAutoMatcherMessage(null);
    try {
      const res = await runAutomaticMapping();
      if (res.success) {
        void queryClient.invalidateQueries({ queryKey: ["conglomerates"] });
        void queryClient.invalidateQueries({ queryKey: ["asset-mappings"] });
        setAutoMatcherMessage("Auto-mapping complete! Checked CNPJ roots and company name keywords.");
        setTimeout(() => setAutoMatcherMessage(null), 5000);
      } else {
        setAutoMatcherMessage(`Auto-mapping failed: ${res.error}`);
      }
    } catch (err) {
      console.error(err);
      setAutoMatcherMessage("An error occurred during mapping.");
    } finally {
      setRunningAutoMatcher(false);
    }
  };

  // Filter Economic Groups
  const filteredConglomerates = useMemo(() => {
    if (!searchQuery) return conglomerates;
    const q = searchQuery.toLowerCase();
    return conglomerates.filter(
      (c) =>
        c.company_name.toLowerCase().includes(q) ||
        (c.ticker_b3 && c.ticker_b3.toLowerCase().includes(q)) ||
        (c.setor_cvm && c.setor_cvm.toLowerCase().includes(q)) ||
        (c.gics_sector && c.gics_sector.toLowerCase().includes(q))
    );
  }, [conglomerates, searchQuery]);

  // Filter Assets
  const filteredAssets = useMemo(() => {
    return assets.filter((a) => {
      const matchesSearch =
        !searchQuery ||
        a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.sub_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        a.company_name.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesType = assetTypeFilter === "all" || a.type === assetTypeFilter;
      const matchesSource =
        mappingSourceFilter === "all" ||
        a.mapping_source === mappingSourceFilter;

      return matchesSearch && matchesType && matchesSource;
    });
  }, [assets, searchQuery, assetTypeFilter, mappingSourceFilter]);

  // Paginated Assets
  const pageSize = 50;
  const totalPages = Math.max(1, Math.ceil(filteredAssets.length / pageSize));
  const validCurrentPage = Math.min(currentPage, totalPages);
  
  const paginatedAssets = useMemo(() => {
    const start = (validCurrentPage - 1) * pageSize;
    return filteredAssets.slice(start, start + pageSize);
  }, [filteredAssets, validCurrentPage, pageSize]);

  // Metrics summary
  const summary = useMemo(() => {
    const activeCongs = conglomerates.filter((c) => c.distributors_count > 0 || c.plants_count > 0).length;
    const totalDists = assets.filter((a) => a.type === "distributor").length;
    const mappedDists = assets.filter((a) => a.type === "distributor" && (a.mapped_cvm || a.custom_owner_name)).length;
    const totalPlants = assets.filter((a) => a.type === "plant").length;
    const mappedPlants = assets.filter((a) => a.type === "plant" && (a.mapped_cvm || a.custom_owner_name)).length;
    const unmapped = assets.filter((a) => !a.mapped_cvm && !a.custom_owner_name).length;
    const totalCompanies = universeCompanies.length;
    const connectedCompanies = universeCompanies.filter(
      (c) => c.has_financials || c.mapped_distributors > 0 || c.mapped_plants > 0
    ).length;

    return {
      activeCongs,
      distributors: `${mappedDists} / ${totalDists}`,
      plants: `${mappedPlants} / ${totalPlants}`,
      unmapped,
      totalCompanies,
      connectedCompanies,
    };
  }, [conglomerates, assets, universeCompanies]);

  if (!bridgeReady || isLoading) {
    return <StateBanner variant="loading" title="Loading CVM registry and sectoral linkages..." />;
  }

  if (isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load registry data"
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      {/* Top Header Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800 pb-3.5">
        <div>
          <h2 className="text-base font-semibold text-zinc-100">CVM Registry & Sectoral Data Hub</h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Connect CVM-registered companies (CNPJ) with sectoral databases to build auditable, traceable indicator pipelines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="xs"
            onClick={handleRunAutoMatcher}
            disabled={runningAutoMatcher}
            className="bg-amber-600 hover:bg-amber-700 text-white font-semibold flex items-center gap-1.5"
          >
            {runningAutoMatcher ? "Matching..." : "⚡ Auto-Link Sectors"}
          </Button>
        </div>
      </div>

      {autoMatcherMessage && (
        <div className="bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs rounded p-2.5">
          {autoMatcherMessage}
        </div>
      )}

      {/* Summary Metrics */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4 lg:grid-cols-6">
        <SummaryTile label="Registry Size" value={summary.totalCompanies} />
        <SummaryTile label="Active Links" value={summary.connectedCompanies} />
        <SummaryTile label="Economic Groups" value={summary.activeCongs} />
        <SummaryTile
          label="Pending Links"
          value={summary.unmapped}
          highlight={summary.unmapped > 0}
        />
        <SummaryTile label="Dist. Coverage" value={summary.distributors} />
        <SummaryTile label="Gen. Coverage" value={summary.plants} />
      </div>

      {/* Navigation & Filters Bar */}
      <div className="flex flex-col md:flex-row gap-3 justify-between items-start md:items-center bg-zinc-900/30 border border-zinc-850 rounded-lg p-2.5">
        <div className="flex rounded border border-zinc-700/80 overflow-hidden" role="tablist">
          <TabButton
            label="Company Registry"
            active={activeTab === "universe"}
            onClick={() => { setActiveTab("universe"); setSearchQuery(""); setUniversePage(1); }}
          />
          <TabButton
            label="Economic Groups"
            active={activeTab === "groups"}
            onClick={() => { setActiveTab("groups"); setSearchQuery(""); setCurrentPage(1); }}
          />
          <TabButton
            label="Sector Data Links"
            active={activeTab === "links"}
            onClick={() => { setActiveTab("links"); setSearchQuery(""); setCurrentPage(1); }}
          />
        </div>

        <div className="flex items-center gap-2 w-full md:w-auto">
          <Input
            placeholder="Search assets, companies, tickers, or CNPJs..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); setUniversePage(1); }}
            className="h-8 w-full md:max-w-xs text-xs"
          />

          {activeTab === "links" && (
            <>
              <select
                value={assetTypeFilter}
                onChange={(e: any) => { setAssetTypeFilter(e.target.value); setCurrentPage(1); }}
                className="h-8 rounded border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-300 outline-none focus:border-amber-500"
              >
                <option value="all">All Types</option>
                <option value="distributor">Distribution</option>
                <option value="plant">Generation</option>
              </select>

              <select
                value={mappingSourceFilter}
                onChange={(e: any) => { setMappingSourceFilter(e.target.value); setCurrentPage(1); }}
                className="h-8 rounded border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-300 outline-none focus:border-amber-500"
              >
                <option value="all">All Sources</option>
                <option value="auto">Auto linked</option>
                <option value="manual">Manual override</option>
                <option value="unmapped">Unlinked</option>
              </select>
            </>
          )}

          {activeTab === "universe" && (
            <label className="flex items-center gap-1.5 cursor-pointer text-xs text-zinc-400 select-none whitespace-nowrap">
              <input
                type="checkbox"
                checked={universeConnectedOnly}
                onChange={(e) => { setUniverseConnectedOnly(e.target.checked); setUniversePage(1); }}
                className="accent-amber-500"
              />
              Connected only
            </label>
          )}
        </div>
      </div>

      {/* Tab 3: Company Registry */}
      {activeTab === "universe" && (
        <div className="space-y-3">
          {universeQuery.isLoading ? (
            <StateBanner variant="loading" title="Loading CVM company registry..." />
          ) : universeQuery.isError ? (
            <StateBanner
              variant="error"
              title="Could not load company registry"
              message={universeQuery.error instanceof Error ? universeQuery.error.message : "Unknown error"}
            />
          ) : (
            <>
              <div className="flex items-center justify-between text-xs text-zinc-500 px-0.5">
                <span className="font-mono">
                  {filteredUniverse.length} of {universeCompanies.length} companies
                </span>
              </div>
              <AllCompaniesTable companies={paginatedUniverse} />
              {filteredUniverse.length > UNIVERSE_PAGE_SIZE && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-900/10 border border-zinc-850 rounded-lg p-3 text-xs text-zinc-400">
                  <div>
                    Showing{" "}
                    <span className="font-semibold text-zinc-200">
                      {Math.min(filteredUniverse.length, (universeValidPage - 1) * UNIVERSE_PAGE_SIZE + 1)}
                    </span>{" "}to{" "}
                    <span className="font-semibold text-zinc-200">
                      {Math.min(filteredUniverse.length, universeValidPage * UNIVERSE_PAGE_SIZE)}
                    </span>{" "}of{" "}
                    <span className="font-semibold text-zinc-200">{filteredUniverse.length}</span> companies
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button size="xs" disabled={universeValidPage === 1} onClick={() => setUniversePage(1)}>First</Button>
                    <Button size="xs" disabled={universeValidPage === 1} onClick={() => setUniversePage((p) => Math.max(1, p - 1))}>Prev</Button>
                    <span className="px-2 font-mono text-[11px] text-zinc-300">Page {universeValidPage} of {universeTotalPages}</span>
                    <Button size="xs" disabled={universeValidPage === universeTotalPages} onClick={() => setUniversePage((p) => Math.min(universeTotalPages, p + 1))}>Next</Button>
                    <Button size="xs" disabled={universeValidPage === universeTotalPages} onClick={() => setUniversePage(universeTotalPages)}>Last</Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Tab 2: Economic Groups */}
      {activeTab === "groups" && (
        <div className="border border-zinc-850 rounded-lg bg-zinc-950/20 overflow-hidden">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="bg-zinc-900/50 text-[10px] uppercase font-semibold text-zinc-500 tracking-wider">
                <th className="px-3.5 py-2.5">Company / Group</th>
                <th className="px-3.5 py-2.5">Ticker</th>
                <th className="px-3.5 py-2.5">CNPJ</th>
                <th className="px-3.5 py-2.5">CVM Sector</th>
                <th className="px-3.5 py-2.5">GICS Sector</th>
                <th className="px-3.5 py-2.5 text-center">Linked Assets</th>
                <th className="px-3.5 py-2.5 text-right">Capacity (MW)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-900">
              {filteredConglomerates.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-zinc-500">
                    No groups found matching the search.
                  </td>
                </tr>
              ) : (
                filteredConglomerates.map((c) => {
                  const rowId = c.is_listed ? `cvm-${c.cd_cvm}` : `custom-${c.company_name}`;
                  const isExpanded = expandedRowIds.has(rowId);
                  const hasMappedAssets = c.distributors_count > 0 || c.plants_count > 0;
                  const companyAssets = assets.filter((a) => 
                    c.is_listed 
                      ? a.mapped_cvm === c.cd_cvm 
                      : a.custom_owner_name === c.company_name
                  );

                  return (
                    <Fragment key={rowId}>
                      <tr
                        onClick={() => hasMappedAssets && toggleExpand(rowId)}
                        className={`hover:bg-zinc-900/30 transition-colors ${
                          hasMappedAssets ? "cursor-pointer" : "opacity-60"
                        } ${isExpanded ? "bg-zinc-900/20" : ""}`}
                      >
                        <td className="px-3.5 py-3 font-medium text-zinc-200">
                          <div className="flex items-center gap-1.5">
                            {hasMappedAssets && (
                              <span className="text-[10px] text-zinc-500">
                                {isExpanded ? "▼" : "▶"}
                              </span>
                            )}
                            <span>{c.company_name}</span>
                            {!c.is_listed && (
                              <span className="px-1.5 py-0.5 text-[9px] font-semibold bg-zinc-800 text-zinc-400 rounded">
                                Non-Listed
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3.5 py-3 font-mono text-zinc-400">{c.ticker_b3 || "—"}</td>
                        <td className="px-3.5 py-3 font-mono text-zinc-400">
                          {c.cnpj ? c.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5") : "—"}
                        </td>
                        <td className="px-3.5 py-3 text-zinc-400">{c.setor_cvm || "—"}</td>
                        <td className="px-3.5 py-3 text-zinc-400">{c.gics_sector || "—"}</td>
                        <td className="px-3.5 py-3 text-center font-semibold text-zinc-300">
                          {c.distributors_count}
                        </td>
                        <td className="px-3.5 py-3 text-right font-mono font-medium text-zinc-300">
                          {c.total_capacity_mw > 0 ? `${c.total_capacity_mw.toLocaleString("en-US", { maximumFractionDigits: 1 })} MW` : "—"}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${rowId}-details`} className="bg-zinc-950/45">
                          <td colSpan={7} className="px-8 py-2.5">
                            <div className="space-y-1.5 border-l-2 border-amber-600/30 pl-4 py-1">
                              <h4 className="text-[10px] uppercase font-semibold text-zinc-500 tracking-wider mb-2">
                                Linked sectoral assets
                              </h4>
                              {companyAssets.map((a) => (
                                <div key={`${a.id}-${a.type}`} className="flex items-center justify-between text-xs py-1 border-b border-zinc-900/40 last:border-0">
                                  <div className="flex items-center gap-2">
                                    <span className={`px-1.5 py-0.5 text-[9px] font-semibold rounded ${
                                      a.type === "distributor" ? "bg-sky-500/10 text-sky-400" : "bg-emerald-500/10 text-emerald-400"
                                    }`}>
                                      {a.type === "distributor" ? "Dist" : "Gen"}
                                    </span>
                                    <span className="font-medium text-zinc-300">{a.name}</span>
                                    <span className="text-[10px] text-zinc-500 font-mono">({a.id})</span>
                                  </div>
                                  <div className="flex items-center gap-4">
                                    <span className="text-zinc-500 font-mono text-[10.5px]">{a.stats}</span>
                                    <span className={`px-1.5 py-0.5 text-[9px] rounded-full font-medium ${
                                      a.mapping_source === "manual" ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "bg-zinc-800 text-zinc-500"
                                    }`}>
                                      {a.mapping_source === "manual" ? "Override" : "Auto"}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 1: Sector Data Links */}
      {activeTab === "links" && (
        <div className="space-y-3">
          <div className="border border-zinc-850 rounded-lg bg-zinc-950/20 overflow-hidden">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-zinc-900/50 text-[10px] uppercase font-semibold text-zinc-500 tracking-wider">
                  <th className="px-3.5 py-2.5">Sectoral Asset</th>
                  <th className="px-3.5 py-2.5">Details</th>
                  <th className="px-3.5 py-2.5">Source</th>
                  <th className="px-3.5 py-2.5">Linked CVM Company</th>
                  <th className="px-3.5 py-2.5">Link Status</th>
                  <th className="px-3.5 py-2.5 text-right">CNPJ / Ticker</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-900">
                {paginatedAssets.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                      No sectoral assets found. Run "Auto-Link Sectors" to detect linkages automatically.
                    </td>
                  </tr>
                ) : (
                  paginatedAssets.map((a) => {
                    const key = `${a.id}-${a.type}`;
                    const isUpdating = updatingAssetKeys.has(key);

                    return (
                      <tr key={key} className="hover:bg-zinc-900/20 transition-colors">
                        <td className="px-3.5 py-2.5 font-medium text-zinc-200">
                          <div>
                            <div>{a.name}</div>
                            <div className="text-[10px] font-mono text-zinc-600 mt-0.5">ID: {a.id}</div>
                          </div>
                        </td>
                        <td className="px-3.5 py-2.5 text-zinc-400 text-[10.5px]">
                          {a.sub_name}
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span className={`px-1.5 py-0.5 text-[9px] font-semibold rounded ${
                            a.type === "distributor" ? "bg-sky-500/10 text-sky-400" : "bg-emerald-500/10 text-emerald-400"
                          }`}>
                            {a.type === "distributor" ? "Energy Dist." : "Energy Gen."}
                          </span>
                        </td>
                        <td className="px-3.5 py-2.5">
                          <select
                            value={a.mapped_cvm ? `cvm:${a.mapped_cvm}` : a.custom_owner_name ? `custom:${a.custom_owner_name}` : ""}
                            disabled={isUpdating}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (val === "action:add-custom") {
                                const name = prompt("Enter the name of the custom Non-Listed Owner/Group:");
                                if (name && name.trim()) {
                                  void handleMappingChange(a.id, a.type, null, name.trim());
                                } else {
                                  e.target.value = a.mapped_cvm ? `cvm:${a.mapped_cvm}` : a.custom_owner_name ? `custom:${a.custom_owner_name}` : "";
                                }
                              } else if (val.startsWith("cvm:")) {
                                const cdCvm = Number(val.substring(4));
                                void handleMappingChange(a.id, a.type, cdCvm, null);
                              } else if (val.startsWith("custom:")) {
                                const ownerName = val.substring(7);
                                void handleMappingChange(a.id, a.type, null, ownerName);
                              } else {
                                void handleMappingChange(a.id, a.type, null, null);
                              }
                            }}
                            className={`w-full max-w-[200px] h-8 rounded border bg-zinc-950 px-2 text-xs outline-none transition-colors focus:border-amber-500 ${
                              isUpdating ? "border-amber-500/40 text-amber-500" : "border-zinc-800 text-zinc-200"
                            }`}
                          >
                            <option value="">-- Unlinked --</option>
                            <option value="action:add-custom" className="text-amber-500 font-semibold">+ Add Custom Entity...</option>
                            
                            <optgroup label="CVM Listed Companies">
                              {conglomerates.filter(c => c.is_listed).map((c) => (
                                <option key={c.cd_cvm} value={`cvm:${c.cd_cvm}`}>
                                  {c.company_name} ({c.ticker_b3 || "no-ticker"})
                                </option>
                              ))}
                            </optgroup>

                            {customOwnersList.length > 0 && (
                              <optgroup label="Non-Listed Custom Entities">
                                {customOwnersList.map((o) => (
                                  <option key={`custom-${o}`} value={`custom:${o}`}>
                                    {o} (Non-Listed)
                                  </option>
                                ))}
                              </optgroup>
                            )}
                          </select>
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span className={`px-2 py-0.5 text-[9px] rounded-full font-semibold border ${
                            a.mapping_source === "manual"
                              ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
                              : a.mapping_source === "auto"
                              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                              : "bg-zinc-800 border-zinc-750 text-zinc-500"
                          }`}>
                            {a.mapping_source === "manual" ? "Override" : a.mapping_source === "auto" ? "Auto linked" : "Unlinked"}
                          </span>
                        </td>
                        <td className="px-3.5 py-2.5 text-right font-mono text-[10.5px] text-zinc-500">
                          {a.mapped_cvm ? (
                            <div>
                              <span className="text-zinc-400">{a.ticker}</span>
                              <span className="mx-1.5 text-zinc-800">·</span>
                              <span>CVM: {a.mapped_cvm}</span>
                            </div>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {filteredAssets.length > pageSize && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-900/10 border border-zinc-850 rounded-lg p-3 text-xs text-zinc-400">
              <div>
                Showing <span className="font-semibold text-zinc-200">{Math.min(filteredAssets.length, (validCurrentPage - 1) * pageSize + 1)}</span> to{" "}
                <span className="font-semibold text-zinc-200">{Math.min(filteredAssets.length, validCurrentPage * pageSize)}</span> of{" "}
                <span className="font-semibold text-zinc-200">{filteredAssets.length}</span> linked assets
              </div>
              <div className="flex items-center gap-1.5">
                <Button
                  size="xs"
                  disabled={validCurrentPage === 1}
                  onClick={() => setCurrentPage(1)}
                >
                  First
                </Button>
                <Button
                  size="xs"
                  disabled={validCurrentPage === 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                >
                  Prev
                </Button>
                <span className="px-2 font-mono text-[11px] text-zinc-300">
                  Page {validCurrentPage} of {totalPages}
                </span>
                <Button
                  size="xs"
                  disabled={validCurrentPage === totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                >
                  Next
                </Button>
                <Button
                  size="xs"
                  disabled={validCurrentPage === totalPages}
                  onClick={() => setCurrentPage(totalPages)}
                >
                  Last
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Helper components
function SummaryTile({ label, value, highlight = false }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 flex flex-col justify-between min-h-[68px]">
      <span className="text-[10px] uppercase font-semibold text-zinc-500 tracking-wider block">{label}</span>
      <span className={`text-lg font-bold font-mono tracking-tight ${highlight ? "text-amber-500" : "text-zinc-200"}`}>
        {value}
      </span>
    </div>
  );
}

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      role="tab"
      aria-selected={active}
      className={`px-3.5 py-1.5 text-xs font-semibold cursor-pointer transition-colors outline-none ${
        active ? "bg-zinc-800 text-zinc-100" : "bg-zinc-900/15 text-zinc-500 hover:text-zinc-350 hover:bg-zinc-900/50"
      }`}
    >
      {label}
    </button>
  );
}

function formatCnpj(cnpj: string | null): string {
  if (!cnpj) return "—";
  const digits = cnpj.replace(/\D/g, "");
  if (digits.length !== 14) return cnpj;
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
}

function AllCompaniesTable({ companies }: { companies: CvmRegistryEntry[] }) {
  if (companies.length === 0) {
    return (
      <div className="rounded-md border border-zinc-800 bg-zinc-950/20 px-4 py-10 text-center text-xs text-zinc-500">
        No companies match your search. Try clearing the filters.
      </div>
    );
  }
  return (
    <div className="w-full max-w-full overflow-x-auto rounded-md border border-zinc-800">
      <table className="w-full min-w-[900px] text-xs text-left border-collapse">
        <thead>
          <tr className="bg-zinc-900/50 text-[10px] uppercase font-semibold text-zinc-500 tracking-wider sticky top-0">
            <th className="px-3.5 py-2.5">Company</th>
            <th className="px-3.5 py-2.5">Ticker</th>
            <th className="px-3.5 py-2.5">CNPJ</th>
            <th className="px-3.5 py-2.5">CVM Sector</th>
            <th className="px-3.5 py-2.5">GICS Sector</th>
            <th className="px-3.5 py-2.5 text-center">Connections</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-900">
          {companies.map((c) => {
            const hasEnergy = c.mapped_distributors > 0 || c.mapped_plants > 0;
            const hasAny = c.has_financials || hasEnergy;
            return (
              <tr
                key={c.cd_cvm}
                className={`hover:bg-zinc-900/30 transition-colors ${!hasAny ? "opacity-50" : ""}`}
              >
                <td className="px-3.5 py-2.5 font-medium text-zinc-200">
                  <div>{c.company_name}</div>
                  <div className="text-[10px] font-mono text-zinc-600 mt-0.5">CVM {c.cd_cvm}</div>
                </td>
                <td className="px-3.5 py-2.5 font-mono text-zinc-400">{c.ticker_b3 || "—"}</td>
                <td className="px-3.5 py-2.5 font-mono text-zinc-500 text-[10.5px]">{formatCnpj(c.cnpj)}</td>
                <td className="px-3.5 py-2.5 text-zinc-400">{c.setor_cvm || "—"}</td>
                <td className="px-3.5 py-2.5 text-zinc-400">{c.gics_sector || "—"}</td>
                <td className="px-3.5 py-2.5">
                  <div className="flex flex-wrap items-center justify-center gap-1">
                    {c.has_financials && (
                      <span className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 whitespace-nowrap">
                        Financials
                      </span>
                    )}
                    {hasEnergy && (
                      <span
                        title={`${c.mapped_distributors} distributor(s) · ${c.mapped_plants} plant(s)${c.total_capacity_mw > 0 ? ` · ${c.total_capacity_mw.toLocaleString("en-US", { maximumFractionDigits: 1 })} MW` : ""}`}
                        className="px-1.5 py-0.5 text-[9px] font-semibold rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 whitespace-nowrap cursor-help"
                      >
                        Energy
                        {c.mapped_distributors > 0 && (
                          <span className="ml-1 opacity-70">D:{c.mapped_distributors}</span>
                        )}
                        {c.mapped_plants > 0 && (
                          <span className="ml-1 opacity-70">G:{c.mapped_plants}</span>
                        )}
                      </span>
                    )}
                    {!hasAny && (
                      <span className="text-zinc-700 italic">—</span>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
