import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchCoverageUniverse, updateCoverageUniverse, fetchCoveragePriorityScores, fetchCoverageCapacityData, addCompanyToCoverageUniverse, fetchCoverageDecisionHistory, fetchCoverageRecommendation, saveCoverageManagerDecision, type CoverageUniverse } from "@/lib/api/coverage";
import { fetchCompanies } from "@/lib/api/companies";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { DeleteUniverseButton } from "@/components/coverage/UniverseLifecycle";
import { formatB3OrCvm } from "@/components/coverage/companyLabel";

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

export function UniverseSummarySection({
  universe,
  onOpenMethodology,
  onSelectUniverse,
}: {
  universe: CoverageUniverse;
  onOpenMethodology: (tab: "scoring" | "capacity") => void;
  onSelectUniverse: (id: string) => void;
}) {
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
  const rankedItems = items.filter((i: any) => i.score_status !== "blocked" && typeof i.final_score === "number");
  const avgScore = rankedItems.length > 0
    ? Math.round((rankedItems.reduce((acc: number, item: any) => acc + item.final_score, 0) / rankedItems.length) * 10) / 10
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
            <span className="text-[var(--color-text-secondary)]">{(capData.required_hours || 0).toLocaleString()} / {(capData.available_hours || 0).toLocaleString()} h</span>
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

        <div className="mt-6 border-t border-red-900/45 pt-6">
          <Panel
            title="Danger Zone"
            subtitle="Irreversible operations. Be careful."
          >
            <div className="space-y-3 p-1">
              <p className="text-3xs text-zinc-400 leading-normal">
                Permanent deletion will cascade and erase all companies, checklists, decision history, and capacity setups for this universe. This action is transactional and cannot be undone.
              </p>
              <div className="flex justify-start pt-1.5 border-t border-zinc-900/40">
                <DeleteUniverseButton
                  universeId={universe.id}
                  onSuccess={() => {
                    void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
                    onSelectUniverse("");
                  }}
                />
              </div>
            </div>
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

      {/* 3. Full-width Row: Recommendation Package */}
      <div className="lg:col-span-3">
        <RecommendationSection universe={universe} />
      </div>
    </div>
  );
}

// --- Recommendation Section ---
function RecommendationSection({ universe }: { universe: CoverageUniverse }) {
  const queryClient = useQueryClient();
  const [decisionStatus, setDecisionStatus] = useState<"draft" | "pending_review" | "approved" | "rejected">("draft");
  const [decisionNotes, setDecisionNotes] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const recQuery = useQuery({
    queryKey: ["coverage-recommendation", universe.id],
    queryFn: () => fetchCoverageRecommendation(universe.id),
    enabled: !!universe.id,
  });

  const historyQuery = useQuery({
    queryKey: ["coverage-decision-history", universe.id],
    queryFn: () => fetchCoverageDecisionHistory(universe.id),
    enabled: showHistory && !!universe.id,
  });

  const decisionMutation = useMutation({
    mutationFn: () => saveCoverageManagerDecision({
      universe_id: universe.id,
      status: decisionStatus,
      notes: decisionNotes,
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["coverage-recommendation", universe.id] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-decision-history", universe.id] });
    },
    onError: (err) => alert(String(err)),
  });

  const rec = recQuery.data;
  const currentDecision = rec?.manager_decision;

  const STATUS_LABELS: Record<string, { label: string; color: string }> = {
    draft: { label: "Draft", color: "text-zinc-400 border-zinc-700" },
    pending_review: { label: "Pending Review", color: "text-amber-400 border-amber-700" },
    approved: { label: "Approved", color: "text-emerald-400 border-emerald-700" },
    rejected: { label: "Rejected", color: "text-red-400 border-red-700" },
  };

  // Sync form with current decision
  useEffect(() => {
    if (currentDecision?.status) {
      setDecisionStatus(currentDecision.status);
      setDecisionNotes(currentDecision.notes || "");
    }
  }, [currentDecision]);

  return (
    <Panel title="Recommendation Package" subtitle="Manager review — proposed actions and risks. Not auto-approved.">
      <div className="space-y-4 font-mono text-xs">
        {recQuery.isLoading && <StateBanner variant="loading" title="Loading recommendation..." />}

        {!recQuery.isLoading && rec && (
          <>
            {/* Current decision status badge */}
            <div className="flex items-center gap-3 pb-3 border-b border-[var(--color-border-subtle)]">
              <span className="text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Current Status:</span>
              {currentDecision ? (
                <span className={`px-2 py-0.5 rounded border text-2xs font-bold ${STATUS_LABELS[currentDecision.status]?.color || "text-zinc-400 border-zinc-700"}`}>
                  {STATUS_LABELS[currentDecision.status]?.label ?? currentDecision.status}
                </span>
              ) : (
                <span className="text-zinc-600 italic">No decision recorded</span>
              )}
              {currentDecision?.decided_at && (
                <span className="text-3xs text-zinc-600">{currentDecision.decided_at.slice(0, 10)}</span>
              )}
            </div>

            {/* Proposed actions */}
            {rec.proposed_actions?.length > 0 && (
              <div className="space-y-1">
                <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Proposed Actions</span>
                <ul className="space-y-1">
                  {rec.proposed_actions.map((action: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-zinc-300">
                      <span className="text-cyan-600 shrink-0 mt-0.5">→</span>
                      <span>{action}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risks */}
            {rec.risks?.length > 0 && (
              <div className="space-y-1">
                <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Risks to Review</span>
                <ul className="space-y-1">
                  {rec.risks.map((risk: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-amber-400/80">
                      <span className="shrink-0 mt-0.5">⚠</span>
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Coverage summary metrics */}
            {rec.summary && (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 pt-2 border-t border-[var(--color-border-subtle)]">
                {Object.entries(rec.summary as Record<string, any>).slice(0, 8).map(([k, v]) => (
                  <div key={k} className="bg-[var(--color-surface-2)] px-2 py-1.5 rounded border border-[var(--color-border-subtle)]">
                    <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">{k.replace(/_/g, " ")}</span>
                    <span className="font-bold text-zinc-200">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Manager decision form */}
            <div className="pt-3 border-t border-[var(--color-border-subtle)] space-y-3">
              <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Record Manager Decision</span>
              <div className="flex flex-wrap items-center gap-3">
                <select
                  value={decisionStatus}
                  onChange={(e) => setDecisionStatus(e.target.value as any)}
                  className="bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none text-xs"
                >
                  <option value="draft">Draft</option>
                  <option value="pending_review">Pending Review</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
                <input
                  type="text"
                  placeholder="Notes (optional)..."
                  value={decisionNotes}
                  onChange={(e) => setDecisionNotes(e.target.value)}
                  className="flex-1 min-w-[200px] bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none text-xs"
                />
                <Button
                  onClick={() => decisionMutation.mutate()}
                  disabled={decisionMutation.isPending}
                >
                  {decisionMutation.isPending ? "Saving..." : "Save Decision"}
                </Button>
              </div>
              <p className="text-3xs text-zinc-600">Every status change is logged to the decision audit trail.</p>
            </div>

            {/* Decision history toggle */}
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setShowHistory(!showHistory)}
                className="text-2xs text-zinc-600 hover:text-zinc-400 underline transition-colors"
              >
                {showHistory ? "Hide" : "Show"} Decision History
              </button>
              {showHistory && (
                <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
                  {historyQuery.isLoading && <span className="text-zinc-600">Loading...</span>}
                  {(historyQuery.data || []).length === 0 && !historyQuery.isLoading && (
                    <span className="text-zinc-700 italic">No history entries.</span>
                  )}
                  {(historyQuery.data || []).map((h: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 py-1 border-b border-[var(--color-border-subtle)]/30 text-3xs">
                      <span className="text-zinc-600">{h.timestamp?.slice(0, 16)}</span>
                      <span className="text-zinc-500 uppercase">{h.event_type}</span>
                      {h.previous_value && <span className="text-zinc-600">{h.previous_value}</span>}
                      {h.previous_value && <span className="text-zinc-700">→</span>}
                      <span className="text-zinc-300">{h.new_value}</span>
                      {h.rationale && <span className="text-zinc-600 italic">{h.rationale}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </Panel>
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
                  setSearch(`${formatB3OrCvm(c)} - ${c.company_name}`);
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-[var(--color-surface-3)] font-mono text-2xs truncate"
              >
                [{formatB3OrCvm(c)}] {c.company_name}
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
