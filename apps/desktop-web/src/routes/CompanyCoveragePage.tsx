import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchCoverageUniverses,
  addCompanyToCoverageUniverse,
  removeCompanyFromCoverageUniverse,
  fetchCompanyCoverageChecklists,
  updateCompanyCoverageChecklistItem,
  fetchCoverageDecisionHistory,
} from "@/lib/api/coverage";
import { fetchCompanyInfo } from "@/lib/api/companyDetail";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";

export function CompanyCoveragePage() {
  const { cdCvm } = useParams();
  const cdCvmNum = Number(cdCvm);
  const queryClient = useQueryClient();

  const [activeUniverseId, setActiveUniverseId] = useState<string>(() => {
    return localStorage.getItem("active_coverage_universe_id") || "";
  });

  const [tier, setTier] = useState("watchlist");
  const [rationale, setRationale] = useState("");
  const [comments, setComments] = useState("");

  const companyQuery = useQuery({
    queryKey: ["company-info", cdCvmNum],
    queryFn: () => fetchCompanyInfo(cdCvmNum),
    enabled: !!cdCvmNum,
  });

  const universesQuery = useQuery({
    queryKey: ["coverage-universes"],
    queryFn: fetchCoverageUniverses,
  });

  const activeUniverse = universesQuery.data?.find((u) => u.id === activeUniverseId) || universesQuery.data?.[0];

  const checklistsQuery = useQuery({
    queryKey: ["company-coverage-checklist", activeUniverse?.id, cdCvmNum],
    queryFn: () => fetchCompanyCoverageChecklists(activeUniverse!.id, cdCvmNum),
    enabled: !!activeUniverse?.id && !!cdCvmNum,
  });

  const historyQuery = useQuery({
    queryKey: ["company-coverage-history", activeUniverse?.id, cdCvmNum],
    queryFn: () => fetchCoverageDecisionHistory(activeUniverse!.id, cdCvmNum),
    enabled: !!activeUniverse?.id && !!cdCvmNum,
  });

  const addMutation = useMutation({
    mutationFn: () => {
      if (!activeUniverse || !rationale) throw new Error("Missing params");
      return addCompanyToCoverageUniverse({
        universe_id: activeUniverse.id,
        cd_cvm: cdCvmNum,
        tier,
        rationale,
      });
    },
    onSuccess: () => {
      setRationale("");
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-checklist", activeUniverse?.id, cdCvmNum] });
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-history", activeUniverse?.id, cdCvmNum] });
      alert("Tier updated successfully!");
    },
    onError: (err) => alert(String(err))
  });

  const removeMutation = useMutation({
    mutationFn: () => {
      if (!activeUniverse || !rationale) throw new Error("Missing params");
      return removeCompanyFromCoverageUniverse({
        universe_id: activeUniverse.id,
        cd_cvm: cdCvmNum,
        rationale,
      });
    },
    onSuccess: () => {
      setRationale("");
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-checklist", activeUniverse?.id, cdCvmNum] });
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-history", activeUniverse?.id, cdCvmNum] });
      alert("Removed from coverage universe!");
    },
    onError: (err) => alert(String(err))
  });

  const checklistMutation = useMutation({
    mutationFn: (args: { key: string; val: boolean; comments?: string }) => {
      if (!activeUniverse || !rationale) throw new Error("Rationale is required to update checklist status");
      return updateCompanyCoverageChecklistItem({
        universe_id: activeUniverse.id,
        cd_cvm: cdCvmNum,
        item_key: args.key,
        is_completed: args.val,
        comments: args.comments,
        rationale,
      });
    },
    onSuccess: () => {
      setRationale("");
      setComments("");
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-checklist", activeUniverse?.id, cdCvmNum] });
      void queryClient.invalidateQueries({ queryKey: ["company-coverage-history", activeUniverse?.id, cdCvmNum] });
      alert("Checklist item updated!");
    },
    onError: (err) => alert(String(err))
  });

  if (companyQuery.isLoading || universesQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading coverage details..." />;
  }

  const company = companyQuery.data;
  const universes = universesQuery.data || [];

  if (!company) {
    return <StateBanner variant="empty" title="Company Not Found" message="Could not resolve company detail info." />;
  }

  if (universes.length === 0) {
    return (
      <div className="px-4 py-6 font-mono text-xs text-[var(--color-text-secondary)] space-y-2">
        <p>No Stock Coverage Universes are set up yet.</p>
        <p>Please navigate to the <Link to="/coverage" className="text-[var(--color-id-ticker)] hover:underline">Coverage Module</Link> first to configure a universe.</p>
      </div>
    );
  }

  const currentUniverseId = activeUniverse?.id || "";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 px-4 py-3">
      {/* Configuration Column */}
      <div className="space-y-6 lg:col-span-1">
        <Panel title="Universe Selection & Tier" subtitle="Associate company to active universe.">
          <div className="space-y-4 font-mono text-xs">
            <div className="space-y-1">
              <label className="block text-[var(--color-text-secondary)]">Active Workspace</label>
              <select
                value={currentUniverseId}
                onChange={(e) => {
                  setActiveUniverseId(e.target.value);
                  localStorage.setItem("active_coverage_universe_id", e.target.value);
                }}
                className="w-full bg-[var(--color-surface-2)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none"
              >
                {universes.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1 border-t border-[var(--color-border-subtle)] pt-3">
              <label className="block text-[var(--color-text-secondary)] mb-1">Set Coverage Tier</label>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value)}
                className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-1.5 py-1.5 focus:outline-none"
              >
                <option value="must_cover">Must Cover</option>
                <option value="core">Core Coverage</option>
                <option value="watchlist">Watchlist</option>
                <option value="opportunistic">Opportunistic</option>
                <option value="excluded">Excluded</option>
                <option value="inappropriate">Not Appropriate</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="block text-[var(--color-text-secondary)]">Decision Rationale *</label>
              <input
                type="text"
                placeholder="Reason for change (compulsory log)"
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none"
              />
            </div>

            <div className="flex justify-between gap-2 pt-2">
              <Button
                variant="danger"
                onClick={() => removeMutation.mutate()}
                disabled={removeMutation.isPending || !rationale}
              >
                Remove
              </Button>
              <Button
                onClick={() => addMutation.mutate()}
                disabled={addMutation.isPending || !rationale}
              >
                Update Tier
              </Button>
            </div>
          </div>
        </Panel>

        {/* Competitor / supply chain factors */}
        <Panel title="Valuation Factors & Peers" subtitle="Local value-chain attributes.">
          <div className="font-mono text-xs space-y-2 text-[var(--color-text-secondary)]">
            <div className="p-2 border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] rounded">
              <span className="block font-bold text-[var(--color-text-primary)]">Comparable Peers</span>
              <span className="text-[var(--color-text-tertiary)]">TRPL4, EQTL3, CPFE3</span>
            </div>
            <div className="p-2 border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] rounded">
              <span className="block font-bold text-[var(--color-text-primary)]">Key Value Drivers</span>
              <span className="text-[var(--color-text-tertiary)]">Hydrology, FX, SIN capacity</span>
            </div>
          </div>
        </Panel>
      </div>

      {/* Checklist & Logs Column */}
      <div className="lg:col-span-2 space-y-6">
        <Panel title="Coverage Deliverables Checklist" subtitle="Required deliverables validation. Rationale must be filled above first.">
          {checklistsQuery.isLoading ? (
            <div className="font-mono text-2xs p-3">Loading checklist items...</div>
          ) : checklistsQuery.data?.length === 0 ? (
            <div className="font-mono text-2xs p-3 text-[var(--color-text-tertiary)]">
              This company has not been added to the selected universe yet. Use the left panel to set its tier first.
            </div>
          ) : (
            <div className="space-y-3 font-mono text-xs">
              {checklistsQuery.data?.map((item: any) => (
                <div
                  key={item.item_key}
                  className="flex flex-wrap items-start justify-between gap-4 p-3 border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] rounded hover:border-[var(--color-action-primary)]"
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={!!item.is_completed}
                      onChange={(e) => {
                        checklistMutation.mutate({
                          key: item.item_key,
                          val: e.target.checked,
                          comments: comments || item.comments,
                        });
                      }}
                      disabled={checklistMutation.isPending || !rationale}
                      className="mt-0.5"
                    />
                    <div>
                      <span className="font-semibold block capitalize">{item.item_key.replace(/_/g, " ")}</span>
                      {item.completed_at && (
                        <span className="text-2xs text-[var(--color-text-tertiary)] block">
                          Completed: {item.completed_at.slice(0, 16).replace("T", " ")}
                        </span>
                      )}
                      {item.comments && (
                        <p className="text-2xs text-[var(--color-text-secondary)] italic mt-1 bg-[var(--color-surface-3)] p-1 rounded">
                          "{item.comments}"
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Comment..."
                      defaultValue={item.comments || ""}
                      onChange={(e) => setComments(e.target.value)}
                      className="bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-1.5 py-0.5 text-2xs max-w-[120px] focus:outline-none"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Log changes */}
        <Panel title="Audit History Log">
          {historyQuery.isLoading ? (
            <div className="font-mono text-2xs p-3">Loading log history...</div>
          ) : historyQuery.data?.length === 0 ? (
            <div className="font-mono text-2xs p-3 text-[var(--color-text-tertiary)]">No decision logs recorded.</div>
          ) : (
            <div className="space-y-2 max-h-60 overflow-y-auto font-mono text-2xs">
              {historyQuery.data?.map((h: any) => (
                <div key={h.id} className="p-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] rounded">
                  <div className="flex justify-between text-[var(--color-text-tertiary)] mb-1">
                    <span className="uppercase font-bold text-[var(--color-id-ticker)]">{h.event_type}</span>
                    <span>{h.timestamp.slice(0, 16).replace("T", " ")}</span>
                  </div>
                  <div>
                    <span className="text-[var(--color-text-secondary)]">Change:</span> {h.previous_value} ➔ {h.new_value}
                  </div>
                  <div className="italic text-[var(--color-text-tertiary)] mt-1">
                    "Rationale: {h.rationale}"
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
