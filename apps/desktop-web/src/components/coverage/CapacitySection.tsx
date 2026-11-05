import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchCoverageCapacityData, saveCoverageCapacityScenario } from "@/lib/api/coverage";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";

const DEFAULT_TIER_HOURS: Record<string, number> = {
  must_cover: 120.0,
  core: 80.0,
  watchlist: 30.0,
  opportunistic: 45.0,
  excluded: 5.0,
  inappropriate: 5.0,
};

// --- Capacity Simulator Widget ---
export function CapacityWidget({ universeId, onOpenMethodology }: { universeId: string; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
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
              <span className="text-3xs text-[var(--color-text-secondary)]">({(cap.required_hours || 0).toLocaleString()} / {(cap.available_hours || 0).toLocaleString()} h)</span>
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

// --- Capacity Section ---
export function CapacitySection({ universeId, onOpenMethodology }: { universeId: string; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
  const queryClient = useQueryClient();
  const [scenarioHours, setScenarioHours] = useState<number>(1600);
  const [scenarioTierHours, setScenarioTierHours] = useState<Record<string, number>>({ ...DEFAULT_TIER_HOURS });
  const [scenarioEdited, setScenarioEdited] = useState(false);

  const capacityQuery = useQuery({
    queryKey: ["coverage-capacity", universeId],
    queryFn: () => fetchCoverageCapacityData(universeId),
  });

  const saveMutation = useMutation({
    mutationFn: () => saveCoverageCapacityScenario({
      universe_id: universeId,
      available_hours: scenarioHours,
      tier_hours: scenarioTierHours,
    }),
    onSuccess: () => {
      setScenarioEdited(false);
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", universeId] });
    },
    onError: (err) => alert(String(err)),
  });

  const cap = capacityQuery.data;

  // Sync scenario state from loaded capacity data
  useEffect(() => {
    if (cap && !scenarioEdited) {
      setScenarioHours(cap.available_hours ?? 1600);
      setScenarioTierHours(cap.tier_hours_assumptions ?? { ...DEFAULT_TIER_HOURS });
    }
  }, [cap, scenarioEdited]);

  if (capacityQuery.isLoading) return <StateBanner variant="loading" title="Computing capacity..." />;
  if (capacityQuery.isError) return <StateBanner variant="error" title="Failed to load capacity" message={String(capacityQuery.error)} onRetry={() => void capacityQuery.refetch()} />;
  if (!cap) return <StateBanner variant="empty" title="No capacity data" message="Add companies to this universe first." />;

  const utilizationPct = cap.capacity_utilization_pct ?? 0;
  const utilizationColor = utilizationPct > 100 ? "text-red-400" : utilizationPct > 90 ? "text-amber-400" : "text-emerald-400";
  const tierOrder = ["must_cover", "core", "watchlist", "opportunistic", "excluded", "inappropriate"];

  return (
    <div className="space-y-6 font-mono text-xs">
      {/* Capacity warnings */}
      {cap.warnings?.map((w: string, i: number) => (
        <div key={i} className="flex items-start gap-2 p-3 border border-amber-800/40 bg-amber-950/10 rounded text-amber-400">
          <span className="font-bold shrink-0">⚠</span>
          <span>{w}</span>
        </div>
      ))}

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-[var(--color-surface-2)] p-3 rounded border border-[var(--color-border-subtle)] space-y-1">
          <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Available Hours</span>
          <span className="text-xl font-bold text-[var(--color-id-ticker)]">
            {cap.available_hours ? `${cap.available_hours.toLocaleString()} h` : "-"}
          </span>
        </div>
        <div className="bg-[var(--color-surface-2)] p-3 rounded border border-[var(--color-border-subtle)] space-y-1">
          <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Required Hours</span>
          <span className="text-xl font-bold text-zinc-200">
            {cap.required_hours ? `${cap.required_hours.toLocaleString()} h` : "-"}
          </span>
        </div>
        <div className="bg-[var(--color-surface-2)] p-3 rounded border border-[var(--color-border-subtle)] space-y-1">
          <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">Utilization</span>
          <span className={`text-xl font-bold ${utilizationColor}`}>{utilizationPct.toFixed(1)}%</span>
        </div>
        <div className="bg-[var(--color-surface-2)] p-3 rounded border border-[var(--color-border-subtle)] space-y-1">
          <span className="block text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider">GICS Unknown</span>
          <span className={`text-xl font-bold ${(cap.gics_unknown_companies?.length ?? 0) > 0 ? "text-amber-400" : "text-zinc-500"}`}>
            {cap.gics_unknown_companies?.length ?? 0}
          </span>
        </div>
      </div>

      {/* Tier breakdown */}
      <Panel title="Tier Breakdown" subtitle="Estimated hours per coverage tier">
        <table className="w-full">
          <thead>
            <tr className="text-left text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider border-b border-[var(--color-border-subtle)]">
              <th className="pb-2 pr-4">Tier</th>
              <th className="pb-2 pr-4 text-right"># Companies</th>
              <th className="pb-2 pr-4 text-right">Est. Hours</th>
              <th className="pb-2 text-right">Hours / Co. (Assumption)</th>
            </tr>
          </thead>
          <tbody>
            {tierOrder.filter(t => (cap.tier_counts?.[t] ?? 0) > 0 || (cap.tier_hours?.[t] ?? 0) > 0).map((tier) => (
              <tr key={tier} className="border-b border-[var(--color-border-subtle)]/40 hover:bg-[var(--color-surface-2)]">
                <td className="py-1.5 pr-4 font-bold uppercase text-2xs tracking-wider text-zinc-300">{tier.replace(/_/g, " ")}</td>
                <td className="py-1.5 pr-4 text-right text-zinc-400">{cap.tier_counts?.[tier] ?? 0}</td>
                <td className="py-1.5 pr-4 text-right text-zinc-200">{Number((cap.tier_hours?.[tier] ?? 0).toFixed(1)).toLocaleString()} h</td>
                <td className="py-1.5 text-right text-zinc-500">
                  {cap.tier_hours_assumptions?.[tier] ? `${cap.tier_hours_assumptions[tier].toLocaleString()} h` : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      {/* By-owner breakdown */}
      {cap.by_owner && Object.keys(cap.by_owner).length > 0 && (
        <Panel title="By Analyst Owner" subtitle="Coverage load distribution across assigned analysts">
          <table className="w-full">
            <thead>
              <tr className="text-left text-3xs text-[var(--color-text-tertiary)] uppercase tracking-wider border-b border-[var(--color-border-subtle)]">
                <th className="pb-2 pr-4">Owner</th>
                <th className="pb-2 pr-4 text-right"># Companies</th>
                <th className="pb-2 text-right">Est. Hours</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(cap.by_owner as Record<string, any>)
                .sort(([, a], [, b]) => b.required_hours - a.required_hours)
                .map(([owner, od]) => (
                  <tr key={owner} className={`border-b border-[var(--color-border-subtle)]/40 hover:bg-[var(--color-surface-2)] ${owner === "Unassigned" ? "text-amber-400/70" : ""}` }>
                    <td className="py-1.5 pr-4 font-medium">{owner}</td>
                    <td className="py-1.5 pr-4 text-right">{od.company_count}</td>
                    <td className="py-1.5 text-right">{Number(od.required_hours.toFixed(1)).toLocaleString()} h</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </Panel>
      )}

      {/* GICS unknown callout */}
      {(cap.gics_unknown_companies?.length ?? 0) > 0 && (
        <Panel
          title={`GICS Unknown (${cap.gics_unknown_companies.length})`}
          subtitle="Complexity multiplier NOT applied — uncertainty exposed, not hidden"
        >
          <div className="space-y-1">
            {cap.gics_unknown_companies.slice(0, 15).map((co: any) => (
              <div key={co.cd_cvm} className="flex items-center gap-3 py-1 border-b border-[var(--color-border-subtle)]/30">
                <span className="font-bold text-amber-400 w-20 truncate">{co.ticker_b3 || `CVM ${co.cd_cvm}`}</span>
                <span className="text-zinc-400 flex-1 truncate">{co.company_name}</span>
                <span className="text-zinc-600 text-3xs uppercase">{co.tier}</span>
                <Link to={`/empresas/${co.cd_cvm}/coverage`} className="text-2xs text-cyan-600 hover:text-cyan-400">Fix GICS</Link>
              </div>
            ))}
            {cap.gics_unknown_companies.length > 15 && (
              <p className="text-zinc-600 text-2xs pt-1">… and {cap.gics_unknown_companies.length - 15} more</p>
            )}
          </div>
        </Panel>
      )}

      {/* Scenario Input form */}
      <Panel title="Scenario Settings" subtitle="Adjust hours to model different capacity scenarios">
        <div className="space-y-4">
          <div className="space-y-1">
            <label className="block text-[var(--color-text-secondary)]">Available Analyst Hours / Year</label>
            <input
              type="number"
              min={0}
              step={40}
              value={scenarioHours}
              onChange={(e) => { setScenarioHours(Number(e.target.value)); setScenarioEdited(true); }}
              className="w-full max-w-xs bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none"
            />
          </div>

          <div className="space-y-2">
            <span className="block text-[var(--color-text-secondary)] text-2xs uppercase tracking-wider">Hours per Company by Tier (Base, before complexity)</span>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              {tierOrder.map((tier) => (
                <div key={tier} className="space-y-0.5">
                  <label className="block text-3xs text-zinc-500 uppercase">{tier.replace(/_/g, " ")}</label>
                  <input
                    type="number"
                    min={0}
                    step={5}
                    value={scenarioTierHours[tier] ?? DEFAULT_TIER_HOURS[tier]}
                    onChange={(e) => {
                      setScenarioTierHours(prev => ({ ...prev, [tier]: Number(e.target.value) }));
                      setScenarioEdited(true);
                    }}
                    className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none text-xs"
                  />
                </div>
              ))}
            </div>
          </div>

          {scenarioEdited && (
            <div className="flex items-center gap-2 pt-1">
              <Button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                loading={saveMutation.isPending}
              >
                Apply Scenario
              </Button>
              <button
                type="button"
                onClick={() => {
                  setScenarioEdited(false);
                  if (cap) {
                    setScenarioHours(cap.available_hours ?? 1600);
                    setScenarioTierHours(cap.tier_hours_assumptions ?? { ...DEFAULT_TIER_HOURS });
                  }
                }}
                className="text-2xs text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                Reset
              </button>
            </div>
          )}
        </div>
      </Panel>

      {/* Methodology help */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => onOpenMethodology("capacity")}
          className="text-2xs text-zinc-600 hover:text-zinc-400 underline transition-colors"
        >
          View capacity methodology
        </button>
      </div>
    </div>
  );
}
