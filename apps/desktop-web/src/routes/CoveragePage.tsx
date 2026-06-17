import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  fetchCoverageUniverses,
  fetchCoverageUniverse,
  createCoverageUniverse,
  updateCoverageUniverse,
  deleteCoverageUniverse,
  duplicateCoverageUniverse,
  fetchCoveragePriorityScores,
  saveManualScoreOverride,
  fetchCoverageWorkQueue,
  fetchCoverageCapacityData,
  saveCoverageCapacityScenario,
  addCompanyToCoverageUniverse,
  removeCompanyFromCoverageUniverse,
  downloadCoverageUniverseExcel,
  fetchCoverageDecisionHistory,
  fetchCompanyCoverageChecklists,
  updateCompanyCoverageChecklistItem,
  type CoverageUniverse,
} from "@/lib/api/coverage";
import { fetchCompanies, fetchCompanyFilters, type CompanyFiltersResult } from "@/lib/api/companies";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";

// New sub-components
import { UniverseSidebar } from "@/components/coverage/UniverseSidebar";
import { BulkCompanyManagerModal } from "@/components/coverage/BulkCompanyManagerModal";
import { CoverageMethodologyModal } from "@/components/coverage/CoverageMethodologyModal";

const DEFAULT_TIER_HOURS: Record<string, number> = {
  must_cover: 120.0,
  core: 80.0,
  watchlist: 30.0,
  opportunistic: 45.0,
  excluded: 5.0,
  inappropriate: 5.0,
};

type Props = {
  section: "universes" | "prioritization" | "work-queue" | "capacity";
};

export function CoveragePage({ section }: Props) {
  const queryClient = useQueryClient();
  const [activeUniverseId, setActiveUniverseId] = useState<string>(() => {
    return localStorage.getItem("active_coverage_universe_id") || "";
  });
  const [showArchived, setShowArchived] = useState(false);

  // Modal and custom workflow states
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isDuplicateModalOpen, setIsDuplicateModalOpen] = useState(false);
  const [duplicateUniverseId, setDuplicateUniverseId] = useState("");
  const [isMethodologyOpen, setIsMethodologyOpen] = useState(false);
  const [methodologyTab, setMethodologyTab] = useState<"scoring" | "capacity">("scoring");

  const universesQuery = useQuery({
    queryKey: ["coverage-universes"],
    queryFn: fetchCoverageUniverses,
  });

  const universes = universesQuery.data || [];
  const filteredUniverses = useMemo(() => {
    return universes.filter((u) => showArchived || u.status !== "archived");
  }, [universes, showArchived]);

  // Land on empty/dashboard if activeUniverseId is empty or not found in filtered list
  const activeUniverse = filteredUniverses.find((u) => u.id === activeUniverseId);
  const currentUniverseId = activeUniverse?.id || "";

  const capacityQuery = useQuery({
    queryKey: ["coverage-capacity", currentUniverseId],
    queryFn: () => fetchCoverageCapacityData(currentUniverseId),
    enabled: !!currentUniverseId,
  });

  useEffect(() => {
    // If activeUniverseId was set but is not found in filtered list (e.g. deleted/archived), clear it
    if (activeUniverseId && !activeUniverse) {
      setActiveUniverseId("");
      localStorage.removeItem("active_coverage_universe_id");
    }
  }, [activeUniverse, activeUniverseId]);

  const handleSelectUniverse = (id: string) => {
    setActiveUniverseId(id);
    if (id) {
      localStorage.setItem("active_coverage_universe_id", id);
    } else {
      localStorage.removeItem("active_coverage_universe_id");
    }
  };

  if (universesQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading coverage universes..." />;
  }

  if (universesQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load universes"
        message={String(universesQuery.error)}
        onRetry={() => void universesQuery.refetch()}
      />
    );
  }

  const handleExport = async () => {
    try {
      const { filename, content_base64 } = await downloadCoverageUniverseExcel(currentUniverseId);
      const blob = await fetch(`data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${content_base64}`).then((r) => r.blob());
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      link.click();
    } catch (err) {
      alert(String(err));
    }
  };

  return (
    <div className="flex h-[calc(100vh-48px)] overflow-hidden select-none">
      <UniverseSidebar
        universes={filteredUniverses}
        activeUniverseId={currentUniverseId}
        onSelectUniverse={handleSelectUniverse}
        onOpenCreateModal={() => setIsCreateModalOpen(true)}
      />

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6 min-w-0 bg-[var(--color-surface-1)]">
        {!currentUniverseId ? (
          <DashboardHub
            universes={filteredUniverses}
            onSelectUniverse={handleSelectUniverse}
            onOpenCreateModal={() => setIsCreateModalOpen(true)}
            onOpenDuplicateModal={(id) => {
              setDuplicateUniverseId(id);
              setIsDuplicateModalOpen(true);
            }}
            onDeleteUniverse={async (id) => {
              if (window.confirm("Are you sure you want to delete this universe?")) {
                await deleteCoverageUniverse(id);
                void universesQuery.refetch();
                if (activeUniverseId === id) {
                  handleSelectUniverse("");
                }
              }
            }}
          />
        ) : (
          <>
            {/* Header cluster */}
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border-subtle)] pb-4">
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => handleSelectUniverse("")}
                    className="text-zinc-500 hover:text-cyan-400 font-mono text-2xs uppercase tracking-wider cursor-pointer border border-zinc-800 rounded px-1.5 py-0.5 bg-zinc-950/20"
                  >
                    ← Dashboard
                  </button>
                  <span className="text-zinc-700">/</span>
                  <span className="font-mono text-xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Active Workspace</span>
                  <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wide">
                    {activeUniverse?.name} [{activeUniverse?.analysis_type}]
                  </h2>
                  <label className="flex items-center gap-1.5 ml-3 cursor-pointer text-2xs text-[var(--color-text-secondary)] font-mono select-none">
                    <input
                      type="checkbox"
                      checked={showArchived}
                      onChange={(e) => setShowArchived(e.target.checked)}
                      className="bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded accent-cyan-600"
                    />
                    Show Archived
                  </label>
                </div>
                {activeUniverse?.purpose && (
                  <p className="text-xs text-[var(--color-text-secondary)] italic">{activeUniverse.purpose}</p>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Button variant="ghost" onClick={handleExport} disabled={!currentUniverseId}>
                  Export to Excel
                </Button>
                <Button variant="ghost" onClick={() => {
                  setDuplicateUniverseId(currentUniverseId);
                  setIsDuplicateModalOpen(true);
                }}>
                  Duplicate
                </Button>
                <DeleteUniverseButton universeId={currentUniverseId} onSuccess={() => {
                  void universesQuery.refetch();
                  handleSelectUniverse("");
                }} />
              </div>
            </div>

            {/* Main Area */}
            {section === "universes" && activeUniverse && (
              <UniverseSummarySection
                universe={activeUniverse}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
              />
            )}

            {section === "prioritization" && currentUniverseId && (
              <PrioritizationSection
                universeId={currentUniverseId}
                onOpenBulkModal={() => setIsBulkModalOpen(true)}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
              />
            )}

            {section === "work-queue" && currentUniverseId && (
              <WorkQueueSection
                universeId={currentUniverseId}
                onOpenMethodology={(tab) => {
                  setMethodologyTab(tab);
                  setIsMethodologyOpen(true);
                }}
              />
            )}
          </>
        )}
      </div>

      <CreateUniverseModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={(id) => {
          handleSelectUniverse(id);
        }}
      />

      <DuplicateUniverseModal
        isOpen={isDuplicateModalOpen}
        onClose={() => setIsDuplicateModalOpen(false)}
        universeId={duplicateUniverseId}
        onSuccess={(id) => {
          handleSelectUniverse(id);
        }}
      />

      <BulkCompanyManagerModal
        isOpen={isBulkModalOpen}
        onClose={() => setIsBulkModalOpen(false)}
        universeId={currentUniverseId}
        onSuccess={() => {
          void queryClient.invalidateQueries({ queryKey: ["coverage-scores", currentUniverseId] });
        }}
      />

      <CoverageMethodologyModal
        isOpen={isMethodologyOpen}
        onClose={() => setIsMethodologyOpen(false)}
        defaultTab={methodologyTab}
        availableHours={capacityQuery.data?.available_hours || 1600}
      />
    </div>
  );
}


// --- Delete Universe Button ---
function DeleteUniverseButton({ universeId, onSuccess }: { universeId: string; onSuccess: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const mutation = useMutation({
    mutationFn: () => deleteCoverageUniverse(universeId),
    onSuccess: () => {
      setConfirm(false);
      onSuccess();
    }
  });

  if (confirm) {
    return (
      <div className="inline-flex items-center gap-2 font-mono text-2xs">
        <span className="text-[var(--color-state-err)] uppercase">Delete permanently?</span>
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="px-2 py-0.5 border border-[var(--color-state-err)] bg-[var(--color-surface-2)] text-[var(--color-state-err)] rounded hover:bg-[var(--color-surface-3)]"
        >
          Yes
        </button>
        <button
          onClick={() => setConfirm(false)}
          className="px-2 py-0.5 border border-[var(--color-border-default)] rounded bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-3)]"
        >
          No
        </button>
      </div>
    );
  }

  return (
    <Button variant="danger" onClick={() => setConfirm(true)}>
      Delete
    </Button>
  );
}

// --- Create Universe Modal ---
function CreateUniverseModal({
  isOpen,
  onClose,
  onSuccess,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [type, setType] = useState<string>("Equity");
  const [benchmark, setBenchmark] = useState("");

  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => createCoverageUniverse({ name, purpose, analysis_type: type, benchmark }),
    onSuccess: (id) => {
      setName("");
      setPurpose("");
      setBenchmark("");
      onClose();
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      onSuccess(id);
    },
    onError: (err) => alert(String(err)),
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 font-mono text-xs select-none">
      <div className="w-full max-w-md bg-[var(--color-surface-1)] border border-[var(--color-border-default)] rounded p-4 shadow-xl space-y-4">
        <h3 className="text-sm font-medium border-b border-[var(--color-border-subtle)] pb-2 text-[var(--color-id-ticker)] uppercase">
          Create Coverage Universe
        </h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!name) return;
            mutation.mutate();
          }}
          className="space-y-3"
        >
          <div className="space-y-1">
            <label className="block text-[var(--color-text-secondary)]">Universe Name *</label>
            <input
              type="text"
              required
              placeholder="e.g., Equity Watch 2026"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="block text-[var(--color-text-secondary)]">Purpose / Scope</label>
            <textarea
              placeholder="Primary sector focus or theme details..."
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              className="w-full h-20 bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-[var(--color-text-secondary)]">Analysis Type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-sm text-zinc-200"
              >
                <option value="Equity">Equity</option>
                <option value="Credit">Credit</option>
                <option value="IB">IB</option>
                <option value="Portfolio Monitoring">Portfolio Monitoring</option>
                <option value="Sector Watch">Sector Watch</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="block text-[var(--color-text-secondary)]">Benchmark</label>
              <input
                type="text"
                placeholder="IBOV, IPCA, etc."
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-sm"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
            <Button type="button" variant="ghost" onClick={onClose} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name || mutation.isPending} loading={mutation.isPending}>
              Create
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// --- Duplicate Universe Modal ---
function DuplicateUniverseModal({
  isOpen,
  onClose,
  universeId,
  onSuccess,
}: {
  isOpen: boolean;
  onClose: () => void;
  universeId: string;
  onSuccess: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [copyCompanies, setCopyCompanies] = useState(true);
  const [copyChecklists, setCopyChecklists] = useState(false);

  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => duplicateCoverageUniverse(universeId, name, copyCompanies, copyChecklists),
    onSuccess: (newId) => {
      setName("");
      onClose();
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      onSuccess(newId);
    },
    onError: (err) => alert(String(err)),
  });

  useEffect(() => {
    if (isOpen) {
      setName("");
      setCopyCompanies(true);
      setCopyChecklists(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 font-mono text-xs select-none">
      <div className="w-full max-w-md bg-[var(--color-surface-1)] border border-[var(--color-border-default)] rounded p-4 shadow-xl space-y-4">
        <h3 className="text-sm font-medium border-b border-[var(--color-border-subtle)] pb-2 text-[var(--color-id-ticker)] uppercase">
          Duplicate Coverage Universe
        </h3>
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="block text-[var(--color-text-secondary)]">New Name</label>
            <input
              type="text"
              placeholder="e.g. Duplicated Watchlist"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none text-zinc-100"
            />
          </div>

          <div className="space-y-2 pt-2 border-t border-[var(--color-border-subtle)]/45">
            <label className="flex items-center gap-2 cursor-pointer select-none text-zinc-300">
              <input
                type="checkbox"
                checked={copyCompanies}
                onChange={(e) => {
                  setCopyCompanies(e.target.checked);
                  if (!e.target.checked) setCopyChecklists(false);
                }}
                className="accent-cyan-600 rounded"
              />
              <span>Copy companies list</span>
            </label>
            <label
              className={`flex items-center gap-2 select-none ${
                copyCompanies ? "cursor-pointer text-zinc-300" : "cursor-not-allowed text-zinc-650"
              }`}
            >
              <input
                type="checkbox"
                checked={copyChecklists}
                disabled={!copyCompanies}
                onChange={(e) => setCopyChecklists(e.target.checked)}
                className="accent-cyan-600 rounded"
              />
              <span>Copy checklists completed status</span>
            </label>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button onClick={() => mutation.mutate()} disabled={!name || mutation.isPending} loading={mutation.isPending}>
            Duplicate
          </Button>
        </div>
      </div>
    </div>
  );
}

// --- Dashboard Hub Component ---
function DashboardHub({
  universes,
  onSelectUniverse,
  onOpenCreateModal,
  onOpenDuplicateModal,
  onDeleteUniverse,
}: {
  universes: CoverageUniverse[];
  onSelectUniverse: (id: string) => void;
  onOpenCreateModal: () => void;
  onOpenDuplicateModal: (id: string) => void;
  onDeleteUniverse: (id: string) => void;
}) {
  return (
    <div className="space-y-6 font-mono text-xs select-none">
      <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-4">
        <div>
          <h1 className="text-lg font-bold text-zinc-150 uppercase tracking-wider">COVERAGE WORKSPACES</h1>
          <p className="text-3xs text-[var(--color-text-tertiary)] mt-1">
            Manage your stock coverage lists, priority weights, and checklists.
          </p>
        </div>
        <Button variant="primary" onClick={onOpenCreateModal}>
          + CREATE NEW WORKSPACE
        </Button>
      </div>

      {universes.length === 0 ? (
        <div className="p-10 border border-dashed border-[var(--color-border-subtle)] rounded-lg text-center text-zinc-500">
          No universes found. Create your first workspace to start covering stocks.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {universes.map((u) => {
            let typeColor = "text-zinc-400 bg-zinc-950 border-zinc-900";
            if (u.analysis_type === "Equity") typeColor = "text-cyan-400 bg-cyan-950/20 border-cyan-900/40";
            if (u.analysis_type === "Credit") typeColor = "text-emerald-400 bg-emerald-950/20 border-emerald-900/40";
            if (u.analysis_type === "IB") typeColor = "text-pink-400 bg-pink-950/20 border-pink-900/40";
            if (u.analysis_type === "Portfolio Monitoring") typeColor = "text-amber-400 bg-amber-950/20 border-amber-900/40";
            if (u.analysis_type === "Sector Watch") typeColor = "text-sky-400 bg-sky-950/20 border-sky-900/40";

            return (
              <div
                key={u.id}
                className="bg-[var(--color-surface-2)] border border-[var(--color-border-subtle)] hover:border-cyan-700/60 rounded p-4 flex flex-col justify-between gap-4 transition-all hover:shadow-lg"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-bold ${typeColor}`}>
                      {u.analysis_type}
                    </span>
                    <span className={`text-[10px] font-bold uppercase ${
                      u.status === "active" ? "text-emerald-400" : u.status === "draft" ? "text-amber-400" : "text-zinc-500"
                    }`}>
                      {u.status}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-zinc-100 mt-3 hover:text-cyan-400 cursor-pointer" onClick={() => onSelectUniverse(u.id)}>
                    {u.name}
                  </h4>
                  {u.purpose && (
                    <p className="text-3xs text-zinc-400 mt-1.5 line-clamp-2 italic leading-relaxed">
                      {u.purpose}
                    </p>
                  )}
                </div>

                <div className="border-t border-zinc-900/60 pt-3 flex items-center justify-between">
                  <div className="space-y-0.5">
                    <span className="block text-4xs text-zinc-500 uppercase">Covered Stocks</span>
                    <span className="text-xs font-bold text-zinc-200">{u.company_count} cos</span>
                  </div>
                  {u.benchmark && (
                    <div className="space-y-0.5 text-right">
                      <span className="block text-4xs text-zinc-500 uppercase">Benchmark</span>
                      <span className="text-xs font-bold text-zinc-200">{u.benchmark}</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 pt-1 border-t border-zinc-900/40">
                  <Button variant="secondary" size="xs" block onClick={() => onSelectUniverse(u.id)}>
                    Open
                  </Button>
                  <Button variant="ghost" size="xs" onClick={() => onOpenDuplicateModal(u.id)}>
                    Clone
                  </Button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteUniverse(u.id);
                    }}
                    className="p-1 px-2 border border-transparent rounded hover:border-red-900 hover:bg-red-950/30 text-red-500 transition-all text-2xs"
                    title="Delete Permanently"
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


// --- Universe Overview / Metadata Summary tab ---
function getUniverseAccentColor(name: string): string {
  const hash = Array.from(name).reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const colors = [
    "border-cyan-800/80 shadow-cyan-950/10",
    "border-blue-800/80 shadow-blue-950/10",
    "border-emerald-800/80 shadow-emerald-950/10",
    "border-amber-800/80 shadow-amber-950/10",
    "border-purple-800/80 shadow-purple-950/10",
  ];
  return colors[hash % colors.length];
}

function UniverseSummarySection({ universe, onOpenMethodology }: { universe: CoverageUniverse; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
  const queryClient = useQueryClient();
  
  // Inline metadata states
  const [isEditingMetadata, setIsEditingMetadata] = useState(false);
  const [name, setName] = useState(universe.name);
  const [purpose, setPurpose] = useState(universe.purpose || "");
  const [benchmark, setBenchmark] = useState(universe.benchmark || "");
  const [status, setStatus] = useState(universe.status);

  // Calibration states
  const [weights, setWeights] = useState({
    market_cap_weight: 0.3,
    volume_weight: 0.3,
    holding_weight: 0.2,
    sector_weight: 0.2,
  });
  const [tierHours, setTierHours] = useState({
    must_cover: 120,
    core: 80,
    watchlist: 30,
    opportunistic: 45,
    excluded: 5,
    inappropriate: 5,
  });

  // Load detailed configuration assumptions
  const detailQuery = useQuery({
    queryKey: ["coverage-universe-detail", universe.id],
    queryFn: () => fetchCoverageUniverse(universe.id),
  });

  const scoresQuery = useQuery({
    queryKey: ["coverage-scores", universe.id],
    queryFn: () => fetchCoveragePriorityScores(universe.id),
  });

  const capacityQuery = useQuery({
    queryKey: ["coverage-capacity", universe.id],
    queryFn: () => fetchCoverageCapacityData(universe.id),
  });

  const detailData = detailQuery.data;

  // Sync state when details load
  useEffect(() => {
    setName(universe.name);
    setPurpose(universe.purpose || "");
    setBenchmark(universe.benchmark || "");
    setStatus(universe.status);
    
    if (detailData?.assumptions) {
      const w = detailData.assumptions.weights || {};
      setWeights({
        market_cap_weight: w.market_cap_weight ?? 0.3,
        volume_weight: w.volume_weight ?? 0.3,
        holding_weight: w.holding_weight ?? 0.2,
        sector_weight: w.sector_weight ?? 0.2,
      });
      const th = detailData.assumptions.tier_hours || {};
      setTierHours({
        must_cover: th.must_cover ?? 120,
        core: th.core ?? 80,
        watchlist: th.watchlist ?? 30,
        opportunistic: th.opportunistic ?? 45,
        excluded: th.excluded ?? 5,
        inappropriate: th.inappropriate ?? 5,
      });
    }
  }, [universe, detailData]);

  const updateMutation = useMutation({
    mutationFn: (args: { name?: string; purpose?: string; benchmark?: string; status?: string; assumptions?: any }) => {
      const payload = {
        id: universe.id,
        name: args.name ?? name,
        purpose: args.purpose !== undefined ? args.purpose : purpose,
        benchmark: args.benchmark !== undefined ? args.benchmark : benchmark,
        status: args.status ?? status,
        assumptions: args.assumptions ?? (detailData?.assumptions || {}),
      };
      return updateCoverageUniverse(payload);
    },
    onSuccess: () => {
      setIsEditingMetadata(false);
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-universe-detail", universe.id] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", universe.id] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", universe.id] });
      alert("Settings updated successfully!");
    },
    onError: (err) => alert(String(err))
  });

  // Calculations for KPIs
  const items = scoresQuery.data || [];
  const avgScore = items.length > 0
    ? Math.round((items.reduce((acc: number, item: any) => acc + item.final_score, 0) / items.length) * 10) / 10
    : 0;

  let completedTasks = 0;
  let totalTasks = 0;
  for (const item of items) {
    completedTasks += item.completed_checklist_count || 0;
    totalTasks += item.total_checklist_count || 0;
  }
  const completionPct = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  const capData = capacityQuery.data || {};
  const capacityPct = capData.capacity_utilization_pct || 0;

  // Weight validation
  const totalWeight = Math.round(
    (weights.market_cap_weight +
      weights.volume_weight +
      weights.holding_weight +
      weights.sector_weight) *
      100
  );
  const isValidWeightSum = totalWeight === 100;

  const handleSaveAssumptions = () => {
    if (!isValidWeightSum) return;
    updateMutation.mutate({
      assumptions: {
        weights,
        tier_hours: tierHours,
      }
    });
  };

  const accentBorderClass = getUniverseAccentColor(universe.name);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 font-mono text-xs">
      {/* 1. KPI Cluster (Span 3 Columns) */}
      <div className="lg:col-span-3 grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[var(--color-surface-2)] p-4 rounded border border-[var(--color-border-subtle)] space-y-1">
          <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider font-semibold">Covered Companies</span>
          <span className="text-xl font-bold font-mono text-[var(--color-id-ticker)]">{universe.company_count}</span>
        </div>
        <div className="bg-[var(--color-surface-2)] p-4 rounded border border-[var(--color-border-subtle)] space-y-1">
          <div className="flex items-center justify-between">
            <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider font-semibold">Average Priority Score</span>
            <button
              type="button"
              onClick={() => onOpenMethodology("scoring")}
              className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-zinc-800 text-zinc-400 hover:bg-cyan-950 hover:text-cyan-400 text-3xs font-bold transition-colors cursor-pointer border border-zinc-700/60"
              title="Click for scoring methodology guide"
            >
              ?
            </button>
          </div>
          <span className="text-xl font-bold font-mono text-cyan-400">
            {avgScore} <span className="text-3xs text-[var(--color-text-secondary)]">/ 100</span>
          </span>
        </div>
        <div className="bg-[var(--color-surface-2)] p-4 rounded border border-[var(--color-border-subtle)] space-y-1">
          <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider font-semibold">Checklist Deliverables</span>
          <div className="flex items-center justify-between text-2xs text-[var(--color-text-secondary)]">
            <span>{completionPct}% ({completedTasks}/{totalTasks})</span>
          </div>
          <div className="w-full bg-[var(--color-surface-3)] h-1.5 rounded-full overflow-hidden mt-1.5">
            <div className="bg-emerald-500 h-full transition-all duration-300" style={{ width: `${completionPct}%` }} />
          </div>
        </div>
        <div className="bg-[var(--color-surface-2)] p-4 rounded border border-[var(--color-border-subtle)] space-y-1">
          <div className="flex items-center justify-between">
            <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider font-semibold">Capacity Boundary</span>
            <button
              type="button"
              onClick={() => onOpenMethodology("capacity")}
              className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-zinc-800 text-zinc-400 hover:bg-cyan-950 hover:text-cyan-400 text-3xs font-bold transition-colors cursor-pointer border border-zinc-700/60"
              title="Click for capacity guide & multipliers"
            >
              ?
            </button>
          </div>
          <div className="flex items-center justify-between text-2xs">
            <span className="text-[var(--color-text-secondary)]">{capData.required_hours || 0} / {capData.available_hours || 0} h</span>
            <span className={`font-semibold uppercase ${capacityPct > 100 ? "text-[var(--color-state-err)]" : "text-[var(--color-state-ok)]"}`}>
              {capacityPct}%
            </span>
          </div>
          <div className="w-full bg-[var(--color-surface-3)] h-1.5 rounded-full overflow-hidden mt-1.5">
            <div className={`h-full transition-all duration-300 ${capacityPct > 100 ? "bg-red-500 animate-pulse" : "bg-cyan-500"}`} style={{ width: `${Math.min(capacityPct, 100)}%` }} />
          </div>
        </div>
      </div>

      {/* 2. Left Column: Universe Settings Panel */}
      <div className={`lg:col-span-1 border rounded shadow-md ${accentBorderClass}`}>
        <Panel
          title="Universe Profile"
          subtitle="Define scope, benchmark targets, and active workflow status."
        >
          <div className="space-y-4">
            {!isEditingMetadata ? (
              <>
                <div className="grid grid-cols-2 gap-2 border-b border-[var(--color-border-subtle)] pb-3">
                  <div>
                    <span className="block text-[var(--color-text-tertiary)] uppercase text-3xs">Status</span>
                    <span className={`text-xs font-semibold uppercase ${universe.status === "active" ? "text-emerald-400" : "text-amber-400"}`}>
                      {universe.status}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[var(--color-text-tertiary)] uppercase text-3xs">Benchmark</span>
                    <span className="text-xs font-semibold">{universe.benchmark || "None"}</span>
                  </div>
                  <div className="pt-2">
                    <span className="block text-[var(--color-text-tertiary)] uppercase text-3xs">Created At</span>
                    <span>{universe.created_at.slice(0, 10)}</span>
                  </div>
                  <div className="pt-2">
                    <span className="block text-[var(--color-text-tertiary)] uppercase text-3xs">Last Review</span>
                    <span>{universe.updated_at.slice(0, 10)}</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <span className="block text-[var(--color-text-tertiary)] uppercase text-3xs">Purpose & Scope</span>
                  <p className="text-[var(--color-text-secondary)] leading-relaxed bg-[var(--color-surface-2)] p-2 rounded border border-[var(--color-border-subtle)] min-h-[80px]">
                    {universe.purpose || "No purpose description details entered."}
                  </p>
                </div>
                <div className="flex justify-end pt-2 border-t border-[var(--color-border-subtle)]">
                  <Button onClick={() => setIsEditingMetadata(true)}>Edit Profile</Button>
                </div>
              </>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  updateMutation.mutate({});
                }}
                className="space-y-3"
              >
                <div className="space-y-1">
                  <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Universe Name</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Benchmark</label>
                  <input
                    type="text"
                    value={benchmark}
                    onChange={(e) => setBenchmark(e.target.value)}
                    className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Status</label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value as any)}
                    className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 focus:outline-none"
                  >
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Scope / Purpose</label>
                  <textarea
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                    className="w-full h-24 bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none text-xs"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
                  <Button variant="ghost" onClick={() => setIsEditingMetadata(false)}>Cancel</Button>
                  <Button type="submit" disabled={updateMutation.isPending || !name}>
                    Save
                  </Button>
                </div>
              </form>
            )}
          </div>
        </Panel>

        <div className="mt-6">
          <Panel title="Wish List Quick Add" subtitle="Quick add companies to this workspace.">
            <WishListAdder universeId={universe.id} />
          </Panel>
        </div>
      </div>

      {/* 3. Right Column: Scoring Weights & Tier Hours Calibration */}
      <div className="lg:col-span-2">
        <Panel
          title="Priority Weights & capacity Settings"
          subtitle="Calibrate the multi-factor scoring model and workload hours mapped per company tier."
        >
          {detailQuery.isLoading ? (
            <StateBanner variant="loading" title="Retrieving settings assumptions..." />
          ) : (
            <div className="space-y-6">
              {/* Scoring Weights calibration */}
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-1.5">
                  <h4 className="font-semibold text-2xs uppercase tracking-wider text-[var(--color-id-ticker)]">1. Scoring Weights</h4>
                  <span className={`font-mono font-bold text-2xs px-2 py-0.5 rounded ${isValidWeightSum ? "bg-emerald-950/40 text-emerald-400 border border-emerald-900/60" : "bg-red-950/40 text-red-400 border border-red-900/60"}`}>
                    Total: {totalWeight}%
                  </span>
                </div>
                
                {!isValidWeightSum && (
                  <div className="p-2 border border-red-900 bg-red-950/20 text-red-400 rounded leading-relaxed">
                    [WARNING] Multi-factor priority scoring weights must sum to exactly 100% before saving. Adjust sliders below.
                  </div>
                )}

                <div className="space-y-3">
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-3xs text-[var(--color-text-secondary)]">
                      <span>Market Cap Weight</span>
                      <span>{Math.round(weights.market_cap_weight * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(weights.market_cap_weight * 100)}
                      onChange={(e) => setWeights({ ...weights, market_cap_weight: Number(e.target.value) / 100 })}
                      className="w-full accent-cyan-600 cursor-pointer h-1 rounded-full bg-zinc-800"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-3xs text-[var(--color-text-secondary)]">
                      <span>Average 30D Volume Weight</span>
                      <span>{Math.round(weights.volume_weight * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(weights.volume_weight * 100)}
                      onChange={(e) => setWeights({ ...weights, volume_weight: Number(e.target.value) / 100 })}
                      className="w-full accent-cyan-600 cursor-pointer h-1 rounded-full bg-zinc-800"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-3xs text-[var(--color-text-secondary)]">
                      <span>Analyst Holdings Weight</span>
                      <span>{Math.round(weights.holding_weight * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(weights.holding_weight * 100)}
                      onChange={(e) => setWeights({ ...weights, holding_weight: Number(e.target.value) / 100 })}
                      className="w-full accent-cyan-600 cursor-pointer h-1 rounded-full bg-zinc-800"
                    />
                  </div>

                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-3xs text-[var(--color-text-secondary)]">
                      <span>Sector Relevance Weight</span>
                      <span>{Math.round(weights.sector_weight * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={Math.round(weights.sector_weight * 100)}
                      onChange={(e) => setWeights({ ...weights, sector_weight: Number(e.target.value) / 100 })}
                      className="w-full accent-cyan-600 cursor-pointer h-1 rounded-full bg-zinc-800"
                    />
                  </div>
                </div>
              </div>

              {/* Target Hours settings */}
              <div className="space-y-4 pt-4 border-t border-[var(--color-border-subtle)]">
                <h4 className="font-semibold text-2xs uppercase tracking-wider text-[var(--color-id-ticker)]">2. Tier Hours / Year / Stock</h4>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Must Cover</label>
                    <input
                      type="number"
                      min="0"
                      value={tierHours.must_cover}
                      onChange={(e) => setTierHours({ ...tierHours, must_cover: Math.max(0, Number(e.target.value)) })}
                      className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 text-xs focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Core Coverage</label>
                    <input
                      type="number"
                      min="0"
                      value={tierHours.core}
                      onChange={(e) => setTierHours({ ...tierHours, core: Math.max(0, Number(e.target.value)) })}
                      className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 text-xs focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Watchlist</label>
                    <input
                      type="number"
                      min="0"
                      value={tierHours.watchlist}
                      onChange={(e) => setTierHours({ ...tierHours, watchlist: Math.max(0, Number(e.target.value)) })}
                      className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 text-xs focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Opportunistic</label>
                    <input
                      type="number"
                      min="0"
                      value={tierHours.opportunistic}
                      onChange={(e) => setTierHours({ ...tierHours, opportunistic: Math.max(0, Number(e.target.value)) })}
                      className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 text-xs focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Excluded</label>
                    <input
                      type="number"
                      min="0"
                      value={tierHours.excluded}
                      onChange={(e) => setTierHours({ ...tierHours, excluded: Math.max(0, Number(e.target.value)) })}
                      className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 text-xs focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="block text-[var(--color-text-secondary)] text-3xs uppercase">Not Appropriate</label>
                    <input
                      type="number"
                      min="0"
                      value={tierHours.inappropriate}
                      onChange={(e) => setTierHours({ ...tierHours, inappropriate: Math.max(0, Number(e.target.value)) })}
                      className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 text-xs focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-[var(--color-border-subtle)]">
                <Button
                  onClick={handleSaveAssumptions}
                  disabled={updateMutation.isPending || !isValidWeightSum}
                >
                  Save Configuration
                </Button>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

// --- Wish List Adder helper ---
function WishListAdder({ universeId }: { universeId: string }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [tier, setTier] = useState("watchlist");
  const [rationale, setRationale] = useState("");
  const [selectedCvm, setSelectedCvm] = useState<number | null>(null);

  // Auto search query suggestions
  const compQuery = useQuery({
    queryKey: ["companies-search-suggestions", search],
    queryFn: () => fetchCompanies({ search, page_size: 5 }),
    enabled: search.length >= 2,
  });

  const mutation = useMutation({
    mutationFn: () => {
      if (!selectedCvm || !rationale) throw new Error("Missing parameters");
      return addCompanyToCoverageUniverse({
        universe_id: universeId,
        cd_cvm: selectedCvm,
        tier,
        rationale,
      });
    },
    onSuccess: () => {
      setSelectedCvm(null);
      setRationale("");
      setSearch("");
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", universeId] });
      alert("Company added to universe!");
    },
    onError: (err) => alert(String(err))
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="space-y-4 font-mono text-xs"
    >
      <div className="space-y-1 relative">
        <label className="block text-[var(--color-text-secondary)]">Search Company Ticker/Name</label>
        <input
          type="text"
          placeholder="Type at least 2 chars..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setSelectedCvm(null);
          }}
          className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none"
        />
        {compQuery.data?.page?.items && selectedCvm === null && (
          <div className="absolute top-full left-0 right-0 z-10 bg-[var(--color-surface-1)] border border-[var(--color-border-default)] rounded shadow-lg overflow-y-auto max-h-40">
            {compQuery.data.page.items.map((c: any) => (
              <button
                key={c.cd_cvm}
                type="button"
                onClick={() => {
                  setSelectedCvm(c.cd_cvm);
                  setSearch(`${c.ticker_b3 || "CVM"} - ${c.company_name}`);
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-[var(--color-surface-3)] font-mono text-2xs truncate"
              >
                [{c.ticker_b3 || c.cd_cvm}] {c.company_name}
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedCvm !== null && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[var(--color-text-secondary)] mb-1">Coverage Tier</label>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value)}
                className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1 focus:outline-none"
              >
                <option value="must_cover">Must Cover</option>
                <option value="core">Core Coverage</option>
                <option value="watchlist">Watchlist</option>
                <option value="opportunistic">Opportunistic</option>
                <option value="excluded">Excluded</option>
                <option value="inappropriate">Not Appropriate</option>
              </select>
            </div>
          </div>
          <div className="space-y-1">
            <label className="block text-[var(--color-text-secondary)]">Investment Rationale *</label>
            <input
              type="text"
              required
              placeholder="Why cover this company? Mandatory audit log..."
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none"
            />
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={mutation.isPending || !rationale}>
              Add to Wish List
            </Button>
          </div>
        </>
      )}
    </form>
  );
}

// --- Prioritization Score List section ---
// --- Priority Score Tooltip Breakdown ---
function PriorityScoreTooltip({ item, weights }: { item: any; weights: any }) {
  const wCap = Math.round((weights?.market_cap_weight ?? 0.3) * 100);
  const wVol = Math.round((weights?.volume_weight ?? 0.3) * 100);
  const wHold = Math.round((weights?.holding_weight ?? 0.2) * 100);
  const wSect = Math.round((weights?.sector_weight ?? 0.2) * 100);

  const contrCap = ((item.cap_score * wCap) / 100).toFixed(1);
  const contrVol = ((item.vol_score * wVol) / 100).toFixed(1);
  const contrHold = ((item.holding_score * wHold) / 100).toFixed(1);
  const contrSect = ((item.sector_score * wSect) / 100).toFixed(1);

  return (
    <div className="relative group/score inline-block cursor-help">
      <span className="font-bold text-[var(--color-action-primary)] border-b border-dotted border-[var(--color-action-primary)]">
        {item.final_score}
      </span>
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-3 bg-zinc-950 border border-zinc-800 rounded shadow-xl opacity-0 invisible group-hover/score:opacity-100 group-hover/score:visible transition-all duration-200 z-50 text-left font-mono text-3xs text-zinc-300 pointer-events-none space-y-2 leading-relaxed">
        <div className="font-bold border-b border-zinc-850 pb-1 text-zinc-100 uppercase tracking-wider text-[10px]">
          Score Breakdown
        </div>
        <div className="space-y-1">
          <div className="flex justify-between">
            <span>Market Cap Factor ({item.cap_score} pts)</span>
            <span className="text-zinc-400">× {wCap}% = {contrCap}</span>
          </div>
          <div className="flex justify-between">
            <span>Volume Factor ({item.vol_score} pts)</span>
            <span className="text-zinc-400">× {wVol}% = {contrVol}</span>
          </div>
          <div className="flex justify-between">
            <span>Holdings Factor ({item.holding_score} pts)</span>
            <span className="text-zinc-400">× {wHold}% = {contrHold}</span>
          </div>
          <div className="flex justify-between">
            <span>Sector Factor ({item.sector_score} pts)</span>
            <span className="text-zinc-400">× {wSect}% = {contrSect}</span>
          </div>
        </div>
        <div className="border-t border-zinc-800 pt-1.5 space-y-1 text-2xs">
          <div className="flex justify-between">
            <span>Calculated Score:</span>
            <span className="font-bold text-zinc-100">{item.calculated_score}</span>
          </div>
          <div className="flex justify-between">
            <span>Manual Override:</span>
            <span className={`font-bold ${item.manual_score_override > 0 ? "text-emerald-400" : item.manual_score_override < 0 ? "text-red-400" : "text-zinc-500"}`}>
              {item.manual_score_override ? (item.manual_score_override > 0 ? `+${item.manual_score_override}` : item.manual_score_override) : "0.0"}
            </span>
          </div>
          <div className="flex justify-between border-t border-zinc-800/60 pt-1 font-bold text-zinc-100">
            <span>Final Score:</span>
            <span className="text-[var(--color-action-primary)]">{item.final_score}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Capacity Simulator Widget ---
function CapacityWidget({ universeId, onOpenMethodology }: { universeId: string; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
  const queryClient = useQueryClient();
  const capacityQuery = useQuery({
    queryKey: ["coverage-capacity", universeId],
    queryFn: () => fetchCoverageCapacityData(universeId),
  });

  const [isExpanded, setIsExpanded] = useState(false);
  const [availableHours, setAvailableHours] = useState(1600.0);
  const [tierHours, setTierHours] = useState<Record<string, number>>({});

  useEffect(() => {
    if (capacityQuery.data) {
      setAvailableHours(capacityQuery.data.available_hours);
      setTierHours(capacityQuery.data.tier_hours_assumptions || {});
    }
  }, [capacityQuery.data]);

  const mutation = useMutation({
    mutationFn: () => saveCoverageCapacityScenario({
      universe_id: universeId,
      available_hours: Number(availableHours),
      tier_hours: tierHours,
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", universeId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", universeId] });
      alert("Capacity parameters saved!");
      setIsExpanded(false);
    },
    onError: (err) => alert(String(err))
  });

  if (capacityQuery.isLoading) return <div className="p-3 bg-[var(--color-surface-2)] rounded border border-[var(--color-border-subtle)] text-2xs animate-pulse font-mono">Loading capacity details...</div>;
  const cap = capacityQuery.data;
  if (!cap) return null;

  const isOverloaded = cap.capacity_utilization_pct > 100;
  const capacityPct = cap.capacity_utilization_pct || 0;

  return (
    <div className="bg-[var(--color-surface-2)] p-4 rounded border border-[var(--color-border-subtle)] font-mono text-xs space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4 flex-1 min-w-[280px]">
          <div className="space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider font-semibold">Capacity Utilization</span>
              <button
                type="button"
                onClick={() => onOpenMethodology("capacity")}
                className="inline-flex items-center justify-center w-3 h-3 rounded-full bg-zinc-800 text-zinc-400 hover:bg-cyan-950 hover:text-cyan-400 text-3xs font-bold transition-colors cursor-pointer border border-zinc-700/60"
                title="Click for capacity guide & multipliers"
              >
                ?
              </button>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-sm font-bold uppercase ${isOverloaded ? "text-[var(--color-state-err)] animate-pulse" : "text-[var(--color-state-ok)]"}`}>
                {capacityPct}%
              </span>
              <span className="text-3xs text-[var(--color-text-secondary)]">({cap.required_hours || 0} / {cap.available_hours || 0} hrs)</span>
            </div>
          </div>
          <div className="flex-1 max-w-xs h-2 bg-[var(--color-surface-3)] rounded border border-[var(--color-border-subtle)] overflow-hidden">
            <div
              className="h-full transition-all duration-300"
              style={{
                width: `${Math.min(capacityPct, 100)}%`,
                backgroundColor: isOverloaded ? "var(--color-state-err)" : "var(--color-state-ok)",
              }}
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isOverloaded && (
            <span className="text-3xs text-[var(--color-state-err)] bg-red-950/40 border border-red-900/60 px-2 py-0.5 rounded uppercase font-bold animate-pulse">
              ⚠️ Bandwidth Overloaded
            </span>
          )}
          <Button variant="ghost" onClick={() => setIsExpanded(!isExpanded)}>
            {isExpanded ? "Hide Settings" : "Configure Simulator"}
          </Button>
        </div>
      </div>

      {isExpanded && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
          className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-[var(--color-border-subtle)] pt-4"
        >
          <div className="space-y-2 md:col-span-1 border-r border-[var(--color-border-subtle)] pr-4">
            <h5 className="font-bold text-2xs uppercase tracking-wider text-[var(--color-id-ticker)]">Available Bandwidth</h5>
            <div className="space-y-1">
              <label className="block text-3xs text-[var(--color-text-secondary)]">Analyst Hours / Year</label>
              <input
                type="number"
                value={availableHours}
                onChange={(e) => setAvailableHours(Number(e.target.value))}
                className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2 py-1 text-xs focus:outline-none"
              />
            </div>
            <p className="text-3xs text-[var(--color-text-tertiary)] italic">Adjust total available coverage hours to simulate new hires or part-time allocations.</p>
          </div>

          <div className="space-y-2 md:col-span-2 flex flex-col justify-between">
            <div>
              <h5 className="font-bold text-2xs uppercase tracking-wider text-[var(--color-id-ticker)] mb-2">Hours Per Stock by Tier</h5>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {Object.keys(DEFAULT_TIER_HOURS).map((tier) => (
                  <div key={tier} className="space-y-1">
                    <label className="block text-3xs text-[var(--color-text-tertiary)] capitalize">{tier.replace("_", " ")}</label>
                    <input
                      type="number"
                      value={tierHours[tier] !== undefined ? tierHours[tier] : DEFAULT_TIER_HOURS[tier]}
                      onChange={(e) => setTierHours({ ...tierHours, [tier]: Number(e.target.value) })}
                      className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2 py-1 text-xs focus:outline-none text-right"
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4 pt-2 border-t border-[var(--color-border-subtle)]">
              <Button type="button" variant="ghost" onClick={() => setIsExpanded(false)}>Cancel</Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Saving..." : "Save Simulator"}
              </Button>
            </div>
          </div>
        </form>
      )}
    </div>
  );
}

// --- Inline Checklist Popover Panel ---
function InlineChecklistPopover({
  universeId,
  company,
  onClose,
}: {
  universeId: string;
  company: any;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [rationale, setRationale] = useState("");
  const [comments, setComments] = useState<Record<string, string>>({});

  const checklistsQuery = useQuery({
    queryKey: ["company-coverage-checklist-popover", universeId, company.cd_cvm],
    queryFn: () => fetchCompanyCoverageChecklists(universeId, company.cd_cvm),
    enabled: !!universeId && !!company.cd_cvm,
  });

  const checklistMutation = useMutation({
    mutationFn: (args: { key: string; val: boolean }) => {
      if (!rationale) throw new Error("Rationale is required to update checklist status");
      return updateCompanyCoverageChecklistItem({
        universe_id: universeId,
        cd_cvm: company.cd_cvm,
        item_key: args.key,
        is_completed: args.val,
        comments: comments[args.key] || "",
        rationale,
      });
    },
    onSuccess: () => {
      setRationale("");
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-checklist-popover", universeId, company.cd_cvm] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", universeId] });
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-history-override", universeId, company.cd_cvm] });
      alert("Checklist item updated successfully!");
    },
    onError: (err) => alert(String(err))
  });

  const items = checklistsQuery.data || [];

  return (
    <>
      {/* Backdrop to close click outside */}
      <div className="fixed inset-0 z-30" onClick={onClose} />
      
      {/* Floating Popover Panel */}
      <div className="absolute right-0 top-full mt-1 z-40 w-80 p-4 bg-zinc-900 border border-zinc-800 rounded shadow-2xl font-mono text-xs text-zinc-100 text-left space-y-3">
        <h4 className="font-bold border-b border-zinc-800 pb-1.5 text-[var(--color-id-ticker)] uppercase text-3xs">
          Deliverables checklist: {company.ticker_b3}
        </h4>
        
        {checklistsQuery.isLoading ? (
          <div className="text-3xs text-zinc-500 animate-pulse">Loading checklist...</div>
        ) : items.length === 0 ? (
          <div className="text-3xs text-zinc-500 italic">No checklist items configured.</div>
        ) : (
          <div className="space-y-3 max-h-60 overflow-y-auto pr-1">
            {items.map((item: any) => (
              <div key={item.item_key} className="p-2 bg-zinc-950/60 rounded border border-zinc-850 space-y-2">
                <div className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={!!item.is_completed}
                    onChange={(e) => {
                      if (!rationale) {
                        alert("Please provide a decision rationale first before toggling.");
                        return;
                      }
                      checklistMutation.mutate({ key: item.item_key, val: e.target.checked });
                    }}
                    disabled={checklistMutation.isPending}
                    className="mt-0.5 cursor-pointer"
                  />
                  <div>
                    <span className="font-semibold block capitalize text-2xs">{item.item_key.replace(/_/g, " ")}</span>
                    {item.completed_at && (
                      <span className="text-3xs text-zinc-500 block">
                        Done: {item.completed_at.slice(0, 10)}
                      </span>
                    )}
                  </div>
                </div>
                
                {/* Comment input inline */}
                <div className="flex gap-1.5 items-center">
                  <input
                    type="text"
                    placeholder={item.comments || "Add a comment..."}
                    value={comments[item.item_key] ?? ""}
                    onChange={(e) => setComments({ ...comments, [item.item_key]: e.target.value })}
                    className="flex-1 bg-zinc-855 border border-zinc-700 rounded px-1.5 py-0.5 text-3xs text-zinc-300 focus:outline-none"
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Rationale input */}
        <div className="space-y-1 border-t border-zinc-800 pt-2.5">
          <label className="block text-3xs text-zinc-400 uppercase font-semibold">Change Rationale *</label>
          <input
            type="text"
            required
            placeholder="Why toggle? Compulsory log..."
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-3xs text-zinc-200 focus:outline-none"
          />
        </div>

        <div className="flex justify-end gap-1.5">
          <Button variant="ghost" onClick={onClose} className="px-2 py-0.5 text-3xs">
            Close
          </Button>
        </div>
      </div>
    </>
  );
}

// --- Quick Edit Drawer for Prioritization integration ---
function CoverageQuickEditDrawer({
  company,
  activeUniverseId,
  activeUniverseName,
  activeCoverageItem,
  onClose,
}: {
  company: any;
  activeUniverseId: string;
  activeUniverseName: string;
  activeCoverageItem: any;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [tier, setTier] = useState<string>(activeCoverageItem?.tier || "none");
  const [holdings, setHoldings] = useState<string>(
    activeCoverageItem?.holding_pct != null ? String(activeCoverageItem.holding_pct) : "0"
  );
  const [override, setOverride] = useState<string>(
    activeCoverageItem?.manual_score_override != null ? String(activeCoverageItem.manual_score_override) : ""
  );
  const [rationale, setRationale] = useState<string>("");

  const historyQuery = useQuery({
    queryKey: ["company-coverage-history-drawer-prio", activeUniverseId, company.cd_cvm],
    queryFn: () => fetchCoverageDecisionHistory(activeUniverseId, company.cd_cvm),
    enabled: !!activeUniverseId && !!company.cd_cvm,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!rationale) throw new Error("Rationale is mandatory for all coverage decisions");
      
      const prevTier = activeCoverageItem?.tier || "none";
      const newTier = tier;

      // 1. Handle Tier and Holdings pct
      if (newTier === "none") {
        if (prevTier !== "none") {
          await removeCompanyFromCoverageUniverse({
            universe_id: activeUniverseId,
            cd_cvm: company.cd_cvm,
            rationale,
          });
        }
      } else {
        await addCompanyToCoverageUniverse({
          universe_id: activeUniverseId,
          cd_cvm: company.cd_cvm,
          tier: newTier,
          rationale,
          holding_pct: holdings === "" ? 0.0 : Number(holdings),
        });
      }

      // 2. Handle Manual Score Override
      const prevOverride = activeCoverageItem?.manual_score_override;
      const newOverride = override === "" ? null : Number(override);
      
      if (newOverride !== prevOverride && newTier !== "none") {
        await saveManualScoreOverride({
          universe_id: activeUniverseId,
          cd_cvm: company.cd_cvm,
          override: newOverride,
          rationale,
        });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", activeUniverseId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", activeUniverseId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-universe-detail", activeUniverseId] });
      alert("Coverage settings saved successfully!");
      onClose();
    },
    onError: (err) => {
      alert(String(err));
    }
  });

  return (
    <>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slideIn {
          animation: slideIn 0.2s ease-out forwards;
        }
      `}</style>
      
      {/* Backdrop */}
      <div 
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-xs" 
        onClick={onClose}
      />
      
      {/* Drawer Container */}
      <div className="fixed inset-y-0 right-0 z-50 w-96 bg-zinc-900 border-l border-zinc-800 shadow-2xl p-6 flex flex-col font-mono text-xs text-zinc-100 animate-slideIn">
        {/* Header */}
        <div className="border-b border-zinc-850 pb-3 mb-4 flex justify-between items-start">
          <div className="max-w-[85%]">
            <h3 className="text-sm font-bold text-[var(--color-id-ticker)] truncate">
              {company.ticker_b3 || "N/A"} - {company.company_name}
            </h3>
            <span className="text-3xs text-zinc-500 block mt-0.5">
              CVM: {company.cd_cvm} · Sector: {company.gics_sector || company.sector_name || "N/A"}
            </span>
            <span className="text-3xs text-zinc-400 block mt-1">
              Universe: <span className="text-zinc-200">{activeUniverseName}</span>
            </span>
          </div>
          <button 
            type="button" 
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 text-sm focus:outline-none"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form 
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate();
          }}
          className="flex-1 overflow-y-auto space-y-4 pr-1"
        >
          {/* Coverage Tier */}
          <div className="space-y-1">
            <label className="block text-3xs text-zinc-400 uppercase font-semibold">Coverage Tier</label>
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
            >
              <option value="none">Not in Universe (Remove)</option>
              <option value="must_cover">Must Cover</option>
              <option value="core">Core Coverage</option>
              <option value="watchlist">Watchlist</option>
              <option value="opportunistic">Opportunistic</option>
              <option value="excluded">Excluded</option>
              <option value="inappropriate">Not Appropriate</option>
            </select>
          </div>

          {tier !== "none" && (
            <>
              {/* Holdings % */}
              <div className="space-y-1">
                <label className="block text-3xs text-zinc-400 uppercase font-semibold">Analyst Holdings %</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  value={holdings}
                  onChange={(e) => setHoldings(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
                />
              </div>

              {/* Manual Score Override */}
              <div className="space-y-1">
                <label className="block text-3xs text-zinc-400 uppercase font-semibold">Manual Score Override (+/-)</label>
                <input
                  type="number"
                  step="0.5"
                  placeholder="e.g. 5.0 or -10"
                  value={override}
                  onChange={(e) => setOverride(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
                />
              </div>
            </>
          )}

          {/* Decision Rationale */}
          <div className="space-y-1">
            <label className="block text-3xs text-zinc-400 uppercase font-semibold">Decision Rationale *</label>
            <textarea
              required
              rows={3}
              placeholder="Provide a mandatory reason for this tier, holdings, or score override change..."
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
            />
          </div>

          {/* Save Action */}
          <div className="pt-2">
            <Button 
              type="submit" 
              className="w-full"
              disabled={saveMutation.isPending || !rationale}
            >
              {saveMutation.isPending ? "Saving..." : "Save Coverage Config"}
            </Button>
          </div>

          {/* Decision History logs */}
          <div className="border-t border-zinc-800 pt-3 mt-4">
            <span className="block text-3xs text-zinc-400 uppercase font-semibold mb-2">Audit Decision History</span>
            {historyQuery.isLoading ? (
              <div className="text-3xs text-zinc-500 animate-pulse">Loading log history...</div>
            ) : historyQuery.data?.length === 0 ? (
              <div className="text-3xs text-zinc-500 italic">No historical changes logged.</div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {historyQuery.data?.map((h: any) => (
                  <div key={h.id} className="p-2 bg-zinc-950/60 rounded border border-zinc-850 text-3xs">
                    <div className="flex justify-between text-zinc-500 mb-1">
                      <span className="uppercase font-bold text-[var(--color-id-ticker)]">{h.event_type.replace("_", " ")}</span>
                      <span>{h.timestamp.slice(0, 16).replace("T", " ")}</span>
                    </div>
                    <div className="text-zinc-300">
                      {h.previous_value} ➔ {h.new_value}
                    </div>
                    {h.rationale && (
                      <div className="text-zinc-500 italic mt-0.5">"Rationale: {h.rationale}"</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </form>
      </div>
    </>
  );
}

// --- Prioritization Score List section ---
function PrioritizationSection({ universeId, onOpenBulkModal, onOpenMethodology }: { universeId: string; onOpenBulkModal: () => void; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
  const queryClient = useQueryClient();
  const [selectedCompany, setSelectedCompany] = useState<any | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [checklistCompany, setChecklistCompany] = useState<any | null>(null);

  const [overrideText, setOverrideText] = useState("");
  const [overrideRationale, setOverrideRationale] = useState("");

  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("");
  const [tierFilter, setTierFilter] = useState("");
  const [sortField, setSortField] = useState<string>("final_score");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const scoresQuery = useQuery({
    queryKey: ["coverage-scores", universeId],
    queryFn: () => fetchCoveragePriorityScores(universeId),
  });

  const detailQuery = useQuery({
    queryKey: ["coverage-universe-detail", universeId],
    queryFn: () => fetchCoverageUniverse(universeId),
  });

  const selectedCvm = selectedCompany?.cd_cvm || 0;
  const historyQuery = useQuery({
    queryKey: ["company-coverage-history-override", universeId, selectedCvm],
    queryFn: () => fetchCoverageDecisionHistory(universeId, selectedCvm),
    enabled: !!universeId && !!selectedCvm,
  });

  const overrideMutation = useMutation({
    mutationFn: () => {
      const overrideVal = overrideText === "" ? null : Number(overrideText);
      return saveManualScoreOverride({
        universe_id: universeId,
        cd_cvm: selectedCompany.cd_cvm,
        override: overrideVal,
        rationale: overrideRationale,
      });
    },
    onSuccess: () => {
      setSelectedCompany(null);
      setOverrideText("");
      setOverrideRationale("");
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", universeId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", universeId] });
    },
    onError: (err) => alert(String(err))
  });

  // Sector filters query
  const filtersQuery = useQuery<CompanyFiltersResult>({
    queryKey: ["company-filters"],
    queryFn: fetchCompanyFilters,
  });
  const sectors = filtersQuery.data?.mode === "desktop" ? filtersQuery.data.sectors : [];

  if (scoresQuery.isLoading) return <StateBanner variant="loading" title="Calculating priority rankings..." />;
  const scores = scoresQuery.data || [];

  const normalize = (str: string) =>
    str
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");

  // --- Compute health status based on score quartiles + checklist % ---
  const allFinalScores = scores.map((s: any) => s.final_score as number).sort((a: number, b: number) => a - b);
  const p25 = allFinalScores.length > 0
    ? allFinalScores[Math.floor(allFinalScores.length * 0.25)] ?? 0
    : 0;
  const p75 = allFinalScores.length > 0
    ? allFinalScores[Math.floor(allFinalScores.length * 0.75)] ?? 0
    : 0;

  function getHealthStatus(item: any): "healthy" | "at_risk" | "stale" {
    const total = item.total_checklist_count ?? 0;
    const completed = item.completed_checklist_count ?? 0;
    const pct = total > 0 ? (completed / total) * 100 : 0;
    const score = item.final_score ?? 0;

    if (score >= p75 && pct >= 80) return "healthy";
    if (score < p25 || pct === 0) return "stale";
    return "at_risk";
  }

  // Perform filtering & sorting locally
  const filteredScores = useMemo(() => {
    let list = [...scores];

    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (s) =>
          (s.ticker_b3 && s.ticker_b3.toLowerCase().includes(q)) ||
          (s.company_name && s.company_name.toLowerCase().includes(q))
      );
    }

    if (sector) {
      const secTarget = normalize(sector.replace(/-/g, " "));
      list = list.filter((s) => {
        const sSector = normalize(s.gics_sector || s.setor_analitico || "");
        return sSector.includes(secTarget);
      });
    }

    if (tierFilter) {
      list = list.filter((s) => s.tier === tierFilter);
    }

    list.sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      if (valA == null) return sortOrder === "asc" ? -1 : 1;
      if (valB == null) return sortOrder === "asc" ? 1 : -1;
      if (typeof valA === "string") {
        return sortOrder === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return sortOrder === "asc" ? valA - valB : valB - valA;
    });

    return list;
  }, [scores, search, sector, tierFilter, sortField, sortOrder]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const renderSortIndicator = (field: string) => {
    if (sortField !== field) return <span className="ml-1 opacity-20">↕</span>;
    return <span className="ml-1">{sortOrder === "asc" ? "▲" : "▼"}</span>;
  };

  const TIER_ORDER = ["must_cover", "core", "watchlist", "opportunistic", "excluded", "inappropriate"];
  const TIER_LABELS: Record<string, string> = {
    must_cover: "Must Cover",
    core: "Core Coverage",
    watchlist: "Watchlist",
    opportunistic: "Opportunistic",
    excluded: "Excluded",
    inappropriate: "Not Appropriate",
  };

  // Build rows with tier group headers injected
  type TableRow = { type: "group"; tier: string; count: number } | { type: "item"; data: any };
  const tableRows = useMemo<TableRow[]>(() => {
    const rows: TableRow[] = [];
    let lastTier = "";
    const sorted = [...filteredScores].sort((a, b) => {
      const ai = TIER_ORDER.indexOf(a.tier);
      const bi = TIER_ORDER.indexOf(b.tier);
      // If sort is by tier or default, group by tier first
      if (sortField === "tier" || sortField === "final_score") {
        if (ai !== bi) return ai - bi;
        return (b.final_score ?? 0) - (a.final_score ?? 0);
      }
      // Otherwise respect the sort field, but still group
      return 0;
    });

    // We use filteredScores directly for non-tier/score sorts, otherwise use tier-grouped
    const list = (sortField === "tier" || sortField === "final_score") ? sorted : filteredScores;
    const tierCounts: Record<string, number> = {};
    list.forEach((s) => { tierCounts[s.tier] = (tierCounts[s.tier] ?? 0) + 1; });

    let seen = new Set<string>();
    list.forEach((s) => {
      if (s.tier !== lastTier && !seen.has(s.tier)) {
        rows.push({ type: "group", tier: s.tier, count: tierCounts[s.tier] ?? 0 });
        lastTier = s.tier;
        seen.add(s.tier);
      }
      rows.push({ type: "item", data: s });
    });
    return rows;
  }, [filteredScores, sortField]);

  return (
    <div className="space-y-4">
      {/* Control Bar */}
      <div className="flex flex-wrap items-center gap-3 bg-[var(--color-surface-2)] px-4 py-3 rounded border border-[var(--color-border-subtle)] font-mono text-xs">
        <div className="flex-1 min-w-[180px]">
          <input
            type="text"
            placeholder="Search ticker or name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2.5 py-1.5 focus:outline-none text-zinc-200 placeholder:text-zinc-600"
          />
        </div>

        <div className="w-44">
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-zinc-300"
          >
            <option value="">All Sectors</option>
            {sectors.map((s) => (
              <option key={s.sector_slug} value={s.sector_slug}>
                {s.sector_name}
              </option>
            ))}
          </select>
        </div>

        <div className="w-40">
          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-zinc-300"
          >
            <option value="">All Tiers</option>
            <option value="must_cover">Must Cover</option>
            <option value="core">Core</option>
            <option value="watchlist">Watchlist</option>
            <option value="opportunistic">Opportunistic</option>
            <option value="excluded">Excluded</option>
            <option value="inappropriate">Not Appropriate</option>
          </select>
        </div>

        {(search || sector || tierFilter) && (
          <button
            type="button"
            onClick={() => { setSearch(""); setSector(""); setTierFilter(""); }}
            className="px-3 py-1.5 border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-2xs rounded text-zinc-400 cursor-pointer transition-colors"
          >
            Reset
          </button>
        )}

        <Button variant="primary" onClick={onOpenBulkModal}>
          Manage Companies
        </Button>

        <div className="ml-auto text-3xs text-[var(--color-text-tertiary)]">
          {filteredScores.length} stocks
        </div>
      </div>

      {/* Prioritization Table */}
      <div className="overflow-x-auto border border-[var(--color-border-default)] rounded bg-[var(--color-surface-1)]">
        <table className="w-full border-collapse font-mono text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border-default)] bg-[var(--color-surface-2)] text-[var(--color-text-tertiary)] uppercase text-2xs select-none">
              <th className="px-3 py-2.5 text-left w-8">
                {/* Health status — no sort */}
                Status
              </th>
              <th className="px-3 py-2.5 text-left cursor-pointer hover:text-[var(--color-text-primary)] transition-colors" onClick={() => handleSort("ticker_b3")}>
                Ticker{renderSortIndicator("ticker_b3")}
              </th>
              <th className="px-3 py-2.5 text-left cursor-pointer hover:text-[var(--color-text-primary)] transition-colors" onClick={() => handleSort("company_name")}>
                Company{renderSortIndicator("company_name")}
              </th>
              <th className="px-3 py-2.5 text-left cursor-pointer hover:text-[var(--color-text-primary)] transition-colors" onClick={() => handleSort("tier")}>
                Tier{renderSortIndicator("tier")}
              </th>
              <th className="px-3 py-2.5 text-center w-44">
                <div className="flex items-center justify-center gap-1 select-none">
                  <span className="cursor-pointer hover:text-[var(--color-text-primary)] transition-colors" onClick={() => handleSort("final_score")}>
                    Score{renderSortIndicator("final_score")}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenMethodology("scoring");
                    }}
                    className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-zinc-800 text-zinc-400 hover:bg-cyan-950 hover:text-cyan-400 text-3xs font-bold transition-colors cursor-pointer border border-zinc-700/60"
                    title="Click for scoring methodology guide"
                  >
                    ?
                  </button>
                </div>
              </th>
              <th className="px-3 py-2.5 text-center cursor-pointer hover:text-[var(--color-text-primary)] transition-colors w-32" onClick={() => handleSort("completed_checklist_count")}>
                Checklist{renderSortIndicator("completed_checklist_count")}
              </th>
              <th className="px-3 py-2.5 text-left">Next Action</th>
              <th className="px-3 py-2.5 text-center">Actions</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-[var(--color-text-tertiary)]">
                  No stocks match active filters.
                </td>
              </tr>
            ) : (
              tableRows.map((row, _idx) => {
                if (row.type === "group") {
                  return (
                    <tr key={`group-${row.tier}`} className="bg-[var(--color-surface-2)] border-y border-[var(--color-border-subtle)]">
                      <td colSpan={8} className="px-4 py-1.5">
                        <span className="text-2xs font-bold uppercase tracking-widest text-[var(--color-text-tertiary)]">
                          {TIER_LABELS[row.tier] ?? row.tier}
                        </span>
                        <span className="ml-2 text-3xs text-[var(--color-text-tertiary)] opacity-60">
                          ({row.count})
                        </span>
                      </td>
                    </tr>
                  );
                }

                const s = row.data;
                const health = getHealthStatus(s);
                const total = s.total_checklist_count ?? 0;
                const completed = s.completed_checklist_count ?? 0;
                const checkPct = total > 0 ? (completed / total) * 100 : 0;
                const delta: number | null = s.score_delta ?? null;

                return (
                  <tr key={s.cd_cvm} className="border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-surface-2)] transition-colors">

                    {/* Health Status */}
                    <td className="px-3 py-2.5 text-center">
                      {health === "healthy" && (
                        <span title="Healthy — high score and well covered" className="text-emerald-400 font-bold select-none cursor-default">●</span>
                      )}
                      {health === "at_risk" && (
                        <span title="At Risk — mid score or low checklist completion" className="text-amber-400 font-bold select-none cursor-default">⚠</span>
                      )}
                      {health === "stale" && (
                        <span title="Stale — low score or zero checklist completion" className="text-red-500 font-bold select-none cursor-default">✗</span>
                      )}
                    </td>

                    {/* Ticker */}
                    <td className="px-3 py-2.5 text-[var(--color-id-ticker)] font-bold">
                      <Link to={`/empresas/${s.cd_cvm}`} className="hover:underline">{s.ticker_b3 || "N/A"}</Link>
                    </td>

                    {/* Company Name */}
                    <td className="px-3 py-2.5 truncate max-w-[200px] text-[var(--color-text-primary)]">{s.company_name}</td>

                    {/* Tier badge */}
                    <td className="px-3 py-2.5 text-2xs uppercase">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedCompany(s);
                          setIsDrawerOpen(true);
                        }}
                        className="px-1.5 py-0.5 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-3)] hover:scale-105 transition-transform cursor-pointer hover:border-[var(--color-action-primary)]"
                      >
                        {s.tier.replace(/_/g, " ")}
                      </button>
                    </td>

                    {/* Score bar + delta */}
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden min-w-[60px]">
                          <div
                            className={`h-full rounded-full transition-all ${
                              s.final_score >= p75
                                ? "bg-emerald-500"
                                : s.final_score >= p25
                                ? "bg-amber-500"
                                : "bg-red-500"
                            }`}
                            style={{ width: `${s.final_score}%` }}
                          />
                        </div>
                        <span className={`font-bold tabular-nums text-xs min-w-[32px] text-right ${
                          s.final_score >= p75 ? "text-emerald-400" : s.final_score >= p25 ? "text-amber-400" : "text-red-400"
                        }`}>
                          {s.final_score}
                        </span>
                        {delta !== null && delta !== 0 && (
                          <span className={`text-3xs font-semibold tabular-nums ${delta > 0 ? "text-emerald-500" : "text-red-500"}`}>
                            {delta > 0 ? "▲" : "▼"}{Math.abs(delta)}
                          </span>
                        )}
                      </div>
                      <PriorityScoreTooltip item={s} weights={detailQuery.data?.assumptions?.weights} />
                    </td>

                    {/* Checklist progress bar */}
                    <td className="px-3 py-2.5 relative">
                      <button
                        type="button"
                        onClick={() => setChecklistCompany(s)}
                        className="w-full group flex flex-col gap-1 cursor-pointer"
                        title={`${completed}/${total} checklist items complete — click to manage`}
                      >
                        <div className="flex items-center justify-between text-3xs text-[var(--color-text-tertiary)]">
                          <span className={checkPct === 100 ? "text-emerald-400 font-semibold" : ""}>
                            {completed}/{total}
                          </span>
                          <span className={checkPct === 100 ? "text-emerald-400" : checkPct > 0 ? "text-amber-400" : "text-zinc-600"}>
                            {Math.round(checkPct)}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              checkPct === 100 ? "bg-emerald-500" : checkPct > 0 ? "bg-amber-500" : "bg-zinc-700"
                            }`}
                            style={{ width: `${checkPct}%` }}
                          />
                        </div>
                      </button>
                      {checklistCompany?.cd_cvm === s.cd_cvm && (
                        <InlineChecklistPopover
                          universeId={universeId}
                          company={s}
                          onClose={() => setChecklistCompany(null)}
                        />
                      )}
                    </td>

                    {/* Next Action */}
                    <td className="px-3 py-2.5 text-2xs max-w-[140px]">
                      {s.next_pending_item ? (
                        <span className="text-amber-400/80 truncate block" title={s.next_pending_item}>
                          {s.next_pending_item.replace(/_/g, " ")}
                        </span>
                      ) : (
                        <span className="text-emerald-500 font-semibold">✓ All done</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={() => {
                          setSelectedCompany(s);
                          setIsDrawerOpen(false);
                          setOverrideText(s.manual_score_override ? String(s.manual_score_override) : "");
                        }}
                        className="px-2 py-0.5 bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded text-2xs hover:border-[var(--color-action-primary)] transition-colors"
                      >
                        Override
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Override modal */}
      {selectedCompany && !isDrawerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 font-mono text-xs">
          <div className="w-full max-w-md bg-[var(--color-surface-1)] border border-[var(--color-border-default)] rounded p-4 shadow-xl space-y-4">
            <h3 className="text-sm font-medium border-b border-[var(--color-border-subtle)] pb-2 text-[var(--color-id-ticker)]">
              SCORE OVERRIDE: {selectedCompany.ticker_b3}
            </h3>
            <div className="space-y-3">
              <div className="bg-[var(--color-surface-2)] p-2 rounded space-y-1 text-2xs text-[var(--color-text-secondary)]">
                <div>Calculated Score: {selectedCompany.calculated_score}</div>
                <div>Weights: Cap ({Math.round((detailQuery.data?.assumptions?.weights?.market_cap_weight ?? 0.3) * 100)}%), Vol ({Math.round((detailQuery.data?.assumptions?.weights?.volume_weight ?? 0.3) * 100)}%), Holdings ({Math.round((detailQuery.data?.assumptions?.weights?.holding_weight ?? 0.2) * 100)}%), Sector ({Math.round((detailQuery.data?.assumptions?.weights?.sector_weight ?? 0.2) * 100)}%)</div>
              </div>
              <div className="space-y-1">
                <label className="block text-[var(--color-text-secondary)]">Override adjustment (+/-)</label>
                <input
                  type="number"
                  placeholder="e.g. 10 or -15"
                  value={overrideText}
                  onChange={(e) => setOverrideText(e.target.value)}
                  className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none"
                />
              </div>
              <div className="space-y-1">
                <label className="block text-[var(--color-text-secondary)]">Decision Rationale *</label>
                <input
                  type="text"
                  required
                  placeholder="Reason for overriding algorithmic score..."
                  value={overrideRationale}
                  onChange={(e) => setOverrideRationale(e.target.value)}
                  className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none"
                />
              </div>

              {/* History logs */}
              <div className="border-t border-[var(--color-border-subtle)] pt-3">
                <span className="block font-bold text-2xs text-[var(--color-text-secondary)] uppercase tracking-wider mb-2">Previous Decision Logs</span>
                {historyQuery.isLoading ? (
                  <div className="text-3xs text-[var(--color-text-tertiary)] animate-pulse">Loading log history...</div>
                ) : historyQuery.data?.length === 0 ? (
                  <div className="text-3xs text-[var(--color-text-tertiary)] italic">No previous decisions recorded.</div>
                ) : (
                  <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                    {historyQuery.data?.map((h: any) => (
                      <div key={h.id} className="p-1.5 bg-[var(--color-surface-2)] rounded border border-[var(--color-border-subtle)] text-3xs">
                        <div className="flex justify-between text-[var(--color-text-tertiary)]">
                          <span className="uppercase font-semibold text-[var(--color-id-ticker)]">{h.event_type.replace(/_/g, " ")}</span>
                          <span>{h.timestamp.slice(0, 16).replace("T", " ")}</span>
                        </div>
                        <div className="text-[var(--color-text-secondary)]">{h.previous_value} ➔ {h.new_value}</div>
                        {h.rationale && h.rationale !== "auto_snapshot" && (
                          <div className="text-zinc-500 italic mt-0.5">"{h.rationale}"</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
              <Button variant="ghost" onClick={() => setSelectedCompany(null)}>Cancel</Button>
              <Button
                onClick={() => overrideMutation.mutate()}
                disabled={overrideMutation.isPending || !overrideRationale}
              >
                {overrideMutation.isPending ? "Saving..." : "Apply"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Sliding Quick Edit Drawer */}
      {selectedCompany && isDrawerOpen && detailQuery.data && (
        <CoverageQuickEditDrawer
          company={selectedCompany}
          activeUniverseId={universeId}
          activeUniverseName={detailQuery.data.name}
          activeCoverageItem={selectedCompany}
          onClose={() => setSelectedCompany(null)}
        />
      )}
    </div>
  );
}



// --- Work Queue / Gaps list tab ---
function WorkQueueSection({ universeId, onOpenMethodology }: { universeId: string; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
  const queueQuery = useQuery({
    queryKey: ["coverage-work-queue", universeId],
    queryFn: () => fetchCoverageWorkQueue(universeId),
  });

  if (queueQuery.isLoading) return <StateBanner variant="loading" title="Compiling coverage gaps..." />;
  const tasks = queueQuery.data || [];

  return (
    <div className="space-y-4">
      <CapacityWidget universeId={universeId} onOpenMethodology={onOpenMethodology} />

      <Panel title="Active Tasks" subtitle="Dynamic checklist items missing from covered stocks in this universe.">
        <div className="space-y-2">
          {tasks.length === 0 ? (
            <StateBanner variant="empty" title="All up-to-date" message="No pending coverage gaps found in this universe!" />
          ) : (
            tasks.map((t: any, i: number) => (
              <div
                key={i}
                className="flex items-center justify-between p-3 border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] rounded font-mono text-xs hover:border-[var(--color-action-primary)]"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[var(--color-id-ticker)]">{t.ticker_b3}</span>
                    <span className="text-[var(--color-text-secondary)]">({t.company_name})</span>
                  </div>
                  <p className="text-[var(--color-text-tertiary)]">{t.description}</p>
                </div>
                <div>
                  <Link
                    to={`/empresas/${t.cd_cvm}/coverage`}
                    className="px-2 py-1 bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded text-2xs hover:border-[var(--color-action-primary)]"
                  >
                    Solve
                  </Link>
                </div>
              </div>
            ))
          )}
        </div>
      </Panel>
    </div>
  );
}
