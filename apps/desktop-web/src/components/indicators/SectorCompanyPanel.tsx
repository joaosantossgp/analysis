import { useEffect, useState, useMemo, Fragment, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type {
  AssetMappingEntry,
  ConglomerateEntry,
  CvmRegistryEntry,
} from "@/lib/bridge/types";
import {
  fetchConglomerates,
  fetchAssetMappings,
  updateAssetMapping,
  runAutomaticMapping,
  fetchCompanyUniverse,
} from "@/lib/api/distribution";
import {
  buildPortfolioRows,
  getAssetMappingReviewState,
  getPriorityReviewQueue,
  summarizeEntityWorkspace,
  type EntityWorkspaceSummary,
  type PortfolioRow,
} from "@/lib/indicators/entityWorkspace";
import {
  NEW_CUSTOM_OWNER_VALUE,
  assetMatchesMappingSourceFilter,
  buildInitialMappingDraft,
  buildMappingUpdateParams,
  getMappingDraftValidation,
  ownerValueForAsset,
  type MappingDraft,
} from "@/lib/indicators/mappingReview";

export function SectorCompanyPanel({ bridgeReady }: { bridgeReady: boolean }) {
  const [activeTab, setActiveTab] = useState<"portfolio" | "universe" | "groups" | "links">("portfolio");
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
  const [selectedAssetKey, setSelectedAssetKey] = useState<string | null>(null);
  const [mappingDraft, setMappingDraft] = useState<MappingDraft | null>(null);
  const [mappingFeedback, setMappingFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);

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

  const conglomerates: ConglomerateEntry[] =
    conglomeratesQuery.data?.mode === "desktop" || conglomeratesQuery.data?.mode === "mock"
      ? conglomeratesQuery.data.items
      : [];
  const assets: AssetMappingEntry[] =
    mappingsQuery.data?.mode === "desktop" || mappingsQuery.data?.mode === "mock"
      ? mappingsQuery.data.items
      : [];
  const universeCompanies: CvmRegistryEntry[] =
    universeQuery.data?.mode === "desktop" || universeQuery.data?.mode === "mock"
      ? universeQuery.data.items
      : [];

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

  const handleSaveMappingReview = async () => {
    if (!selectedAsset || !mappingDraft) return;
    const validation = getMappingDraftValidation(selectedAsset, mappingDraft);
    if (!validation.canSave) {
      setMappingFeedback({
        tone: "error",
        message: validation.message ?? "Review the mapping before saving.",
      });
      return;
    }

    const updateParams = buildMappingUpdateParams(selectedAsset, mappingDraft);
    const key = assetKey(selectedAsset);
    setUpdatingAssetKeys((prev) => new Set([...prev, key]));
    setMappingFeedback(null);
    try {
      const res = await updateAssetMapping(
        updateParams.assetId,
        updateParams.assetType,
        updateParams.cdCvm,
        updateParams.customOwnerName,
        updateParams.reviewNotes ?? undefined,
      );
      if (res.success) {
        void queryClient.invalidateQueries({ queryKey: ["conglomerates"] });
        void queryClient.invalidateQueries({ queryKey: ["asset-mappings"] });
        setMappingFeedback({
          tone: "success",
          message: "Manual mapping review saved to the local asset mapping table.",
        });
      } else if (res.error) {
        setMappingFeedback({ tone: "error", message: `Failed to save mapping: ${res.error}` });
      }
    } catch (err) {
      console.error(err);
      setMappingFeedback({ tone: "error", message: "An error occurred while saving the mapping." });
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
      const matchesSource = assetMatchesMappingSourceFilter(a, mappingSourceFilter);

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

  const selectedAsset = useMemo(() => {
    if (filteredAssets.length === 0) return null;
    if (!selectedAssetKey) return filteredAssets[0];
    return filteredAssets.find((asset) => assetKey(asset) === selectedAssetKey) ?? filteredAssets[0];
  }, [filteredAssets, selectedAssetKey]);

  const selectedAssetVersion = selectedAsset
    ? `${assetKey(selectedAsset)}:${ownerValueForAsset(selectedAsset)}:${selectedAsset.review_notes ?? ""}:${selectedAsset.mapping_source}`
    : "";

  useEffect(() => {
    if (activeTab !== "links") return;
    if (filteredAssets.length === 0) {
      setSelectedAssetKey(null);
      return;
    }
    if (!selectedAssetKey || !filteredAssets.some((asset) => assetKey(asset) === selectedAssetKey)) {
      setSelectedAssetKey(assetKey(filteredAssets[0]));
    }
  }, [activeTab, filteredAssets, selectedAssetKey]);

  useEffect(() => {
    if (!selectedAsset) {
      setMappingDraft(null);
      return;
    }
    setMappingDraft(buildInitialMappingDraft(selectedAsset));
    setMappingFeedback(null);
  }, [selectedAssetVersion, selectedAsset]);

  const mappingDraftValidation =
    selectedAsset && mappingDraft
      ? getMappingDraftValidation(selectedAsset, mappingDraft)
      : null;

  const entitySummary = useMemo(
    () => summarizeEntityWorkspace(assets, universeCompanies, conglomerates),
    [assets, universeCompanies, conglomerates],
  );
  const portfolioRows = useMemo(
    () => buildPortfolioRows(conglomerates, assets),
    [conglomerates, assets],
  );
  const priorityReviewQueue = useMemo(
    () => getPriorityReviewQueue(assets, 8),
    [assets],
  );

  const openMappings = (
    mappingSource: "all" | "auto" | "manual" | "unmapped" = "all",
    query = "",
  ) => {
    setActiveTab("links");
    setMappingSourceFilter(mappingSource);
    setAssetTypeFilter("all");
    setSearchQuery(query);
    setCurrentPage(1);
  };

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
          <h2 className="text-base font-semibold text-zinc-100">
            Companies & Asset Portfolios
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Review company coverage, mapped Energy assets, manual overrides and unresolved links before using operational indicators.
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
        <SummaryTile label="Mapped Assets" value={`${entitySummary.mappedAssets} / ${entitySummary.totalAssets}`} />
        <SummaryTile
          label="Needs Review"
          value={entitySummary.unmappedAssets}
          highlight={entitySummary.unmappedAssets > 0}
        />
        <SummaryTile label="Manual Overrides" value={entitySummary.manualLinks} />
        <SummaryTile label="Auto Links" value={entitySummary.autoLinks} />
        <SummaryTile label="Dist. Coverage" value={entitySummary.distributorCoverage} />
        <SummaryTile label="Gen. Coverage" value={entitySummary.plantCoverage} />
      </div>

      {/* Navigation & Filters Bar */}
      <div className="flex flex-col md:flex-row gap-3 justify-between items-start md:items-center bg-zinc-900/30 border border-zinc-850 rounded-lg p-2.5">
        <div className="flex rounded border border-zinc-700/80 overflow-hidden" role="tablist">
          <TabButton
            label="Portfolio Overview"
            active={activeTab === "portfolio"}
            onClick={() => { setActiveTab("portfolio"); setSearchQuery(""); setCurrentPage(1); }}
          />
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
            label="Mapping Review"
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

      {/* Tab 0: Portfolio Overview */}
      {activeTab === "portfolio" && (
        <PortfolioOverviewTab
          summary={entitySummary}
          rows={portfolioRows}
          reviewQueue={priorityReviewQueue}
          onOpenMappings={openMappings}
        />
      )}

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

      {/* Tab 1: Mapping Review */}
      {activeTab === "links" && (
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div className="space-y-3 min-w-0">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-3 text-xs text-zinc-500">
              Select an asset, verify the current owner, choose the corrected target, and save a review note.
              Saved changes are stored as manual mappings and override weak automatic inference.
            </div>

            <div className="overflow-hidden rounded-lg border border-zinc-850 bg-zinc-950/20">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-zinc-900/50 text-[10px] uppercase font-semibold text-zinc-500 tracking-wider">
                    <th className="px-3.5 py-2.5">Sectoral Asset</th>
                    <th className="px-3.5 py-2.5">Details</th>
                    <th className="px-3.5 py-2.5">Source</th>
                    <th className="px-3.5 py-2.5">Current Link</th>
                    <th className="px-3.5 py-2.5">Review State</th>
                    <th className="px-3.5 py-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900">
                  {paginatedAssets.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-zinc-500">
                        No sectoral assets found. Run "Auto-Link Sectors" or clear filters.
                      </td>
                    </tr>
                  ) : (
                    paginatedAssets.map((a) => {
                      const key = assetKey(a);
                      const isSelected = selectedAsset ? assetKey(selectedAsset) === key : false;
                      const reviewState = getAssetMappingReviewState(a);

                      return (
                        <tr
                          key={key}
                          onClick={() => {
                            setSelectedAssetKey(key);
                            setMappingFeedback(null);
                          }}
                          className={`cursor-pointer transition-colors hover:bg-zinc-900/20 ${
                            isSelected ? "bg-amber-500/5 outline outline-1 outline-amber-500/20" : ""
                          }`}
                        >
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
                            <CurrentLinkCell asset={a} />
                          </td>
                          <td className="px-3.5 py-2.5">
                            <ReviewStateBadge state={reviewState} />
                            <div className="mt-1 max-w-[220px] text-[10px] leading-snug text-zinc-500">
                              {reviewState.detail}
                            </div>
                          </td>
                          <td className="px-3.5 py-2.5 text-right">
                            <Button
                              size="xs"
                              onClick={(event) => {
                                event.stopPropagation();
                                setSelectedAssetKey(key);
                                setMappingFeedback(null);
                              }}
                            >
                              Review
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

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

          <MappingReviewEditor
            asset={selectedAsset}
            draft={mappingDraft}
            validation={mappingDraftValidation}
            companies={universeCompanies}
            customOwners={customOwnersList}
            feedback={mappingFeedback}
            isSaving={selectedAsset ? updatingAssetKeys.has(assetKey(selectedAsset)) : false}
            onDraftChange={setMappingDraft}
            onSave={handleSaveMappingReview}
          />
        </div>
      )}
    </div>
  );
}

// Helper components
function PortfolioOverviewTab({
  summary,
  rows,
  reviewQueue,
  onOpenMappings,
}: {
  summary: EntityWorkspaceSummary;
  rows: PortfolioRow[];
  reviewQueue: AssetMappingEntry[];
  onOpenMappings: (
    mappingSource?: "all" | "auto" | "manual" | "unmapped",
    query?: string,
  ) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <ReviewActionCard
          label="Unresolved assets"
          value={summary.unmappedAssets}
          description="Assets without a CVM company or custom owner."
          action="Review unlinked"
          highlight={summary.unmappedAssets > 0}
          onClick={() => onOpenMappings("unmapped")}
        />
        <ReviewActionCard
          label="Manual overrides"
          value={summary.manualLinks}
          description="User-adjusted relationships that override automatic matching."
          action="Review manual"
          onClick={() => onOpenMappings("manual")}
        />
        <ReviewActionCard
          label="Auto links"
          value={summary.autoLinks}
          description="Inferred relationships. Confidence is not recorded yet."
          action="Review auto"
          onClick={() => onOpenMappings("auto")}
        />
        <ReviewActionCard
          label="Custom owners"
          value={summary.customOwnerLinks}
          description="Assets linked to non-listed or user-entered owners."
          action="Review owners"
          onClick={() => onOpenMappings("manual")}
        />
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">
              Company Portfolio Spine
            </h3>
            <p className="mt-1 max-w-3xl text-xs leading-relaxed text-zinc-500">
              Start from a company or custom owner, inspect its linked distributors and
              generation assets, then drill into the mapping review table when a
              relationship needs confirmation or correction.
            </p>
          </div>
          <div className="rounded border border-zinc-800 px-2 py-1 text-[10px] text-zinc-500">
            {summary.listedPortfolios} listed · {summary.customPortfolios} custom
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="mt-4">
            <StateBanner
              variant="empty"
              title="No portfolios linked yet"
              message="Run Auto-Link Sectors or use Mapping Review to manually connect assets to companies or custom owners."
            />
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-md border border-zinc-800">
            <table className="w-full min-w-[940px] text-left text-xs">
              <thead>
                <tr className="bg-zinc-900/50 text-[10px] uppercase tracking-wider text-zinc-500">
                  <th className="px-3.5 py-2.5">Company / Owner</th>
                  <th className="px-3.5 py-2.5">Identity</th>
                  <th className="px-3.5 py-2.5 text-center">Assets</th>
                  <th className="px-3.5 py-2.5 text-right">Capacity</th>
                  <th className="px-3.5 py-2.5 text-right">Generation</th>
                  <th className="px-3.5 py-2.5">Mapping Mix</th>
                  <th className="px-3.5 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-900">
                {rows.slice(0, 12).map((row) => (
                  <tr key={row.ownerKey} className="hover:bg-zinc-900/25">
                    <td className="px-3.5 py-3">
                      <div className="font-medium text-zinc-200">{row.companyName}</div>
                      <div className="mt-0.5 text-[10px] text-zinc-600">
                        {row.isListed ? "CVM registered" : "Custom / non-listed owner"}
                      </div>
                    </td>
                    <td className="px-3.5 py-3 font-mono text-[10.5px] text-zinc-500">
                      {row.isListed ? (
                        <>
                          <div>{row.ticker ?? "no ticker"}</div>
                          <div>CVM {row.cdCvm ?? "—"}</div>
                        </>
                      ) : (
                        "Custom owner"
                      )}
                    </td>
                    <td className="px-3.5 py-3 text-center">
                      <div className="font-mono text-zinc-200 tabular-nums">
                        {row.totalAssets}
                      </div>
                      <div className="mt-0.5 text-[10px] text-zinc-600">
                        D:{row.distributorsCount} · G:{row.plantsCount}
                      </div>
                    </td>
                    <td className="px-3.5 py-3 text-right font-mono text-zinc-300 tabular-nums">
                      {formatMw(row.totalCapacityMw)}
                    </td>
                    <td className="px-3.5 py-3 text-right font-mono text-zinc-300 tabular-nums">
                      {row.totalGenerationMwmed > 0
                        ? `${row.totalGenerationMwmed.toLocaleString("en-US", {
                            maximumFractionDigits: 1,
                          })} MWmed`
                        : "—"}
                    </td>
                    <td className="px-3.5 py-3">
                      <div className="flex flex-wrap gap-1">
                        {row.manualLinks > 0 && (
                          <MiniBadge tone="warning">Manual {row.manualLinks}</MiniBadge>
                        )}
                        {row.autoLinks > 0 && (
                          <MiniBadge tone="success">Auto {row.autoLinks}</MiniBadge>
                        )}
                        {row.customOwnerLinks > 0 && (
                          <MiniBadge tone="neutral">Custom {row.customOwnerLinks}</MiniBadge>
                        )}
                      </div>
                    </td>
                    <td className="px-3.5 py-3 text-right">
                      <Button
                        size="xs"
                        onClick={() => onOpenMappings("all", row.companyName)}
                      >
                        Review links
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-zinc-200">
              Priority Mapping Queue
            </h3>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-zinc-500">
              Unresolved assets appear first. Auto-linked assets are usable, but the
              current data does not store confidence or match evidence.
            </p>
          </div>
          <Button size="xs" onClick={() => onOpenMappings("unmapped")}>
            Open full queue
          </Button>
        </div>

        <div className="mt-4 grid gap-2 lg:grid-cols-2">
          {reviewQueue.length === 0 ? (
            <StateBanner
              variant="empty"
              title="No assets available"
              message="No sectoral asset mappings were returned by the local bridge."
            />
          ) : (
            reviewQueue.map((asset) => {
              const state = getAssetMappingReviewState(asset);
              return (
                <div
                  key={`${asset.id}-${asset.type}`}
                  className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-zinc-200">
                        {asset.name}
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-zinc-600">
                        {asset.type === "distributor" ? "Distribution" : "Generation"} · {asset.id}
                      </div>
                    </div>
                    <ReviewStateBadge state={state} />
                  </div>
                  <div className="mt-2 text-[11px] leading-snug text-zinc-500">
                    {state.detail}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

function MappingReviewEditor({
  asset,
  draft,
  validation,
  companies,
  customOwners,
  feedback,
  isSaving,
  onDraftChange,
  onSave,
}: {
  asset: AssetMappingEntry | null;
  draft: MappingDraft | null;
  validation: ReturnType<typeof getMappingDraftValidation> | null;
  companies: CvmRegistryEntry[];
  customOwners: string[];
  feedback: { tone: "success" | "error"; message: string } | null;
  isSaving: boolean;
  onDraftChange: (draft: MappingDraft) => void;
  onSave: () => void;
}) {
  if (!asset || !draft) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-950/30 p-4">
        <StateBanner
          variant="empty"
          title="No asset selected"
          message="Select an asset from the mapping queue to review or correct its owner relationship."
        />
      </div>
    );
  }

  const reviewState = getAssetMappingReviewState(asset);
  const listedCompanies = companies
    .filter((company) => Number.isFinite(company.cd_cvm))
    .sort((a, b) => a.company_name.localeCompare(b.company_name));

  return (
    <aside className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4 xl:sticky xl:top-3 xl:self-start">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-zinc-100">
            Mapping Review
          </h3>
          <p className="mt-1 text-[11px] leading-snug text-zinc-500">
            Confirm, correct, or clear one asset-to-company relationship.
          </p>
        </div>
        <ReviewStateBadge state={reviewState} />
      </div>

      <div className="mt-4 rounded-md border border-zinc-800 bg-zinc-950/60 p-3">
        <div className="text-xs font-semibold text-zinc-200">{asset.name}</div>
        <div className="mt-1 font-mono text-[10px] text-zinc-600">
          {asset.type === "distributor" ? "Distribution" : "Generation"} · {asset.id}
        </div>
        <div className="mt-2 text-[11px] leading-snug text-zinc-500">
          {asset.sub_name}
        </div>
      </div>

      <div className="mt-4 space-y-3">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">
            Current link
          </div>
          <div className="rounded border border-zinc-800 bg-zinc-950/60 px-3 py-2">
            <CurrentLinkCell asset={asset} />
            <p className="mt-2 text-[10px] leading-snug text-zinc-600">
              {reviewState.detail}
            </p>
          </div>
        </div>

        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-wider text-zinc-500">
            Corrected target
          </span>
          <select
            value={draft.targetValue}
            onChange={(event) =>
              onDraftChange({ ...draft, targetValue: event.target.value })
            }
            className="h-9 w-full rounded border border-zinc-800 bg-zinc-950 px-2 text-xs text-zinc-200 outline-none focus:border-amber-500"
          >
            <option value="">Unlinked / unresolved</option>
            <option value={NEW_CUSTOM_OWNER_VALUE}>New custom owner...</option>
            <optgroup label="CVM registered companies">
              {listedCompanies.map((company) => (
                <option key={company.cd_cvm} value={`cvm:${company.cd_cvm}`}>
                  {company.company_name} ({company.ticker_b3 || `CVM ${company.cd_cvm}`})
                </option>
              ))}
            </optgroup>
            {customOwners.length > 0 && (
              <optgroup label="Existing custom owners">
                {customOwners.map((ownerName) => (
                  <option key={ownerName} value={`custom:${ownerName}`}>
                    {ownerName}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>

        {draft.targetValue === NEW_CUSTOM_OWNER_VALUE && (
          <label className="block">
            <span className="mb-1 block text-[10px] uppercase tracking-wider text-zinc-500">
              Custom owner name
            </span>
            <Input
              value={draft.customOwnerName}
              onChange={(event) =>
                onDraftChange({ ...draft, customOwnerName: event.target.value })
              }
              placeholder="Non-listed owner or operating group"
              className="h-9 text-xs"
            />
          </label>
        )}

        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-wider text-zinc-500">
            Review note
          </span>
          <textarea
            value={draft.reviewNotes}
            onChange={(event) =>
              onDraftChange({ ...draft, reviewNotes: event.target.value })
            }
            rows={5}
            placeholder="Why is this link correct, corrected, or unresolved?"
            className="w-full resize-y rounded border border-zinc-800 bg-zinc-950 px-2 py-2 text-xs leading-relaxed text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-amber-500"
          />
          <p className="mt-1 text-[10px] leading-snug text-zinc-600">
            Notes are stored with the local manual mapping. Automatic mapping confidence is not recorded.
          </p>
        </label>

        {validation?.message && (
          <div className="rounded border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-[11px] text-zinc-500">
            {validation.message}
          </div>
        )}

        {feedback && (
          <div
            className={`rounded border px-3 py-2 text-[11px] ${
              feedback.tone === "success"
                ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                : "border-red-500/20 bg-red-500/10 text-red-300"
            }`}
          >
            {feedback.message}
          </div>
        )}

        <Button
          size="sm"
          onClick={onSave}
          disabled={!validation?.canSave || isSaving}
          className="w-full justify-center"
        >
          {isSaving ? "Saving review..." : "Save manual review"}
        </Button>
      </div>
    </aside>
  );
}

function CurrentLinkCell({ asset }: { asset: AssetMappingEntry }) {
  if (asset.mapped_cvm) {
    return (
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-zinc-200">
          {asset.company_name || "CVM company"}
        </div>
        <div className="mt-0.5 font-mono text-[10.5px] text-zinc-500">
          {asset.ticker || "no ticker"} · CVM {asset.mapped_cvm}
        </div>
      </div>
    );
  }

  if (asset.custom_owner_name) {
    return (
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-zinc-200">
          {asset.custom_owner_name}
        </div>
        <div className="mt-0.5 font-mono text-[10.5px] text-zinc-500">
          Custom owner
        </div>
      </div>
    );
  }

  return <span className="text-xs text-zinc-600">Unlinked / unresolved</span>;
}

function ReviewActionCard({
  label,
  value,
  description,
  action,
  highlight = false,
  onClick,
}: {
  label: string;
  value: number;
  description: string;
  action: string;
  highlight?: boolean;
  onClick: () => void;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div
        className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${
          highlight ? "text-amber-400" : "text-zinc-100"
        }`}
      >
        {value.toLocaleString()}
      </div>
      <p className="mt-2 min-h-[34px] text-[11px] leading-snug text-zinc-500">
        {description}
      </p>
      <button
        type="button"
        onClick={onClick}
        className="mt-3 rounded border border-zinc-700 px-2 py-1 text-[11px] font-semibold text-zinc-300 hover:border-amber-500/60 hover:text-amber-300"
      >
        {action}
      </button>
    </div>
  );
}

function ReviewStateBadge({ state }: { state: ReturnType<typeof getAssetMappingReviewState> }) {
  const classes =
    state.tone === "success"
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
      : state.tone === "warning"
        ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
        : "border-zinc-750 bg-zinc-800 text-zinc-500";

  return (
    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[9px] font-semibold ${classes}`}>
      {state.label}
    </span>
  );
}

function MiniBadge({
  tone,
  children,
}: {
  tone: "success" | "warning" | "neutral";
  children: ReactNode;
}) {
  const classes =
    tone === "success"
      ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
      : tone === "warning"
        ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
        : "border-zinc-750 bg-zinc-800 text-zinc-500";

  return (
    <span className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${classes}`}>
      {children}
    </span>
  );
}

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

function formatMw(value: number): string {
  if (!value || value <= 0) return "—";
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 1 })} MW`;
}

function assetKey(asset: AssetMappingEntry): string {
  return `${asset.id}-${asset.type}`;
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
