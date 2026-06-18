import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchCompanies, fetchCompanyFilters, resolveCompanyIdentities, type ResolvedIdentity } from "@/lib/api/companies";
import { bulkUpdateCompaniesInCoverageUniverse } from "@/lib/api/coverage";
import { Button } from "@/components/ui/Button";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  universeId: string;
  onSuccess: () => void;
};

type TabId = "grid" | "paste";

export function BulkCompanyManagerModal({ isOpen, onClose, universeId, onSuccess }: Props) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabId>("grid");

  // Grid states
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("");
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Paste states
  const [rawText, setRawText] = useState("");
  const [resolving, setResolving] = useState(false);
  const [resolvedList, setResolvedList] = useState<ResolvedIdentity[]>([]);
  const [unmappedList, setUnmappedList] = useState<string[]>([]);

  // Selection form states
  const [tier, setTier] = useState("watchlist");
  const [rationale, setRationale] = useState("");

  // Reset states when modal closes/opens
  useEffect(() => {
    if (isOpen) {
      setSelectedIds(new Set());
      setRawText("");
      setResolvedList([]);
      setUnmappedList([]);
      setRationale("");
      setSearch("");
      setSector("");
      setPage(1);
    }
  }, [isOpen]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [search, sector]);

  // Queries
  const filtersQuery = useQuery({
    queryKey: ["company-filters"],
    queryFn: fetchCompanyFilters,
    enabled: isOpen,
  });

  const companiesQuery = useQuery({
    queryKey: ["companies-list-bulk", search, sector, page],
    queryFn: () =>
      fetchCompanies({
        search,
        sector_slug: sector || undefined,
        page,
        page_size: 100,
      }),
    enabled: isOpen && activeTab === "grid",
  });

  const sectors = filtersQuery.data?.mode === "desktop" ? filtersQuery.data.sectors : [];
  const companiesResult = companiesQuery.data?.mode === "desktop" ? companiesQuery.data.page : null;
  const companies = companiesResult?.items || [];
  const pagination = companiesResult?.pagination || { total_pages: 1, current_page: 1, total_items: 0 };

  const handleResolvePaste = async () => {
    if (!rawText.trim()) return;
    setResolving(true);
    try {
      // Split by comma, newline or whitespace
      const inputs = rawText
        .split(/[\n,\s]+/)
        .map((x) => x.trim())
        .filter(Boolean);
      if (inputs.length === 0) return;
      const res = await resolveCompanyIdentities(inputs);
      setResolvedList(res.resolved);
      setUnmappedList(res.unmapped);

      // Automatically check/select resolved company IDs
      const newSelected = new Set<number>();
      res.resolved.forEach((item) => newSelected.add(item.cd_cvm));
      setSelectedIds(newSelected);
    } catch (err) {
      alert("Error resolving tickers: " + String(err));
    } finally {
      setResolving(false);
    }
  };

  const bulkMutation = useMutation({
    mutationFn: () => {
      const ids = Array.from(selectedIds);
      return bulkUpdateCompaniesInCoverageUniverse({
        universe_id: universeId,
        company_ids: ids,
        tier,
        rationale,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", universeId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", universeId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-universes"] });
      onSuccess();
      onClose();
    },
    onError: (err) => {
      alert("Bulk update failed: " + String(err));
    },
  });

  const handleToggleSelectAllPage = () => {
    const pageCvmIds = companies.map((c) => c.cd_cvm);
    const allChecked = pageCvmIds.length > 0 && pageCvmIds.every((id) => selectedIds.has(id));

    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allChecked) {
        pageCvmIds.forEach((id) => next.delete(id));
      } else {
        pageCvmIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const handleToggleSingle = (cdCvm: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(cdCvm)) {
        next.delete(cdCvm);
      } else {
        next.add(cdCvm);
      }
      return next;
    });
  };

  const pageCvmIds = companies.map((c) => c.cd_cvm);
  const isAllPageChecked = pageCvmIds.length > 0 && pageCvmIds.every((id) => selectedIds.has(id));

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 font-mono text-xs select-none">
      <div
        className="w-full max-w-4xl bg-[var(--color-surface-1)] border border-[var(--color-border-default)] rounded shadow-2xl flex flex-col"
        style={{ height: "min(90vh, 700px)" }}
      >
        {/* Header */}
        <header className="p-4 border-b border-[var(--color-border-subtle)] flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-id-ticker)] uppercase tracking-wider">
              Bulk Manage Universe Companies
            </h3>
            <p className="text-3xs text-[var(--color-text-tertiary)] mt-0.5">
              Add or remove multiple companies from this workspace portfolio at once.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 focus:outline-none text-base font-sans"
          >
            &times;
          </button>
        </header>

        {/* Navigation Tabs */}
        <div className="flex border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">
          <button
            type="button"
            onClick={() => setActiveTab("grid")}
            className={`px-4 py-2 border-r border-[var(--color-border-subtle)] font-bold tracking-wider ${
              activeTab === "grid"
                ? "bg-[var(--color-surface-1)] text-cyan-400 border-b-2 border-b-cyan-500"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]"
            }`}
          >
            GRID SELECTOR
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("paste")}
            className={`px-4 py-2 border-r border-[var(--color-border-subtle)] font-bold tracking-wider ${
              activeTab === "paste"
                ? "bg-[var(--color-surface-1)] text-cyan-400 border-b-2 border-b-cyan-500"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]"
            }`}
          >
            PASTE TICKER LIST
          </button>
        </div>

        {/* Tab Contents */}
        <div className="flex-1 overflow-y-auto p-4 min-h-0 flex flex-col">
          {activeTab === "grid" ? (
            <>
              {/* Filters Panel */}
              <div className="flex flex-wrap gap-3 mb-3 bg-[var(--color-surface-2)] p-2.5 rounded border border-[var(--color-border-subtle)]">
                <input
                  type="search"
                  placeholder="Search ticker, name, cvm..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="flex-1 min-w-[200px] bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2.5 py-1 focus:outline-none placeholder:text-zinc-600"
                />
                <select
                  value={sector}
                  onChange={(e) => setSector(e.target.value)}
                  className="w-56 bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2 py-1 focus:outline-none text-zinc-300"
                >
                  <option value="">All Sectors</option>
                  {sectors.map((s) => (
                    <option key={s.sector_slug} value={s.sector_slug}>
                      {s.sector_name}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="secondary"
                  size="xs"
                  onClick={() => setSelectedIds(new Set())}
                  disabled={selectedIds.size === 0}
                >
                  Clear Selection ({selectedIds.size})
                </Button>
              </div>

              {/* Table wrapper */}
              <div className="flex-1 border border-[var(--color-border-subtle)] rounded bg-[var(--color-surface-2)] overflow-auto min-h-0">
                {companiesQuery.isLoading ? (
                  <div className="p-10 text-center text-zinc-500 animate-pulse">
                    Loading B3 company registry...
                  </div>
                ) : (
                  <table className="w-full text-left border-collapse text-[11px]">
                    <thead>
                      <tr className="bg-[var(--color-surface-1)] text-zinc-500 border-b border-[var(--color-border-subtle)] font-bold">
                        <th className="p-2 w-10 text-center">
                          <input
                            type="checkbox"
                            checked={isAllPageChecked}
                            onChange={handleToggleSelectAllPage}
                            className="cursor-pointer"
                          />
                        </th>
                        <th className="p-2 w-24">Ticker</th>
                        <th className="p-2">Company Name</th>
                        <th className="p-2 w-20">CVM Code</th>
                        <th className="p-2 w-48">Sector</th>
                      </tr>
                    </thead>
                    <tbody>
                      {companies.map((c) => {
                        const checked = selectedIds.has(c.cd_cvm);
                        return (
                          <tr
                            key={c.cd_cvm}
                            onClick={() => handleToggleSingle(c.cd_cvm)}
                            className={`border-b border-[var(--color-border-subtle)]/40 hover:bg-[var(--color-surface-3)]/30 cursor-pointer ${
                              checked ? "bg-cyan-950/20 text-cyan-200" : ""
                            }`}
                          >
                            <td className="p-2 text-center" onClick={(e) => e.stopPropagation()}>
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => handleToggleSingle(c.cd_cvm)}
                                className="cursor-pointer"
                              />
                            </td>
                            <td className="p-2 font-bold text-zinc-200">{c.ticker_b3 || "—"}</td>
                            <td className="p-2 truncate max-w-xs">{c.company_name}</td>
                            <td className="p-2 font-mono">{c.cd_cvm}</td>
                            <td className="p-2 text-zinc-400 truncate max-w-[180px]">
                              {c.gics_sector || c.setor_analitico || "—"}
                            </td>
                          </tr>
                        );
                      })}
                      {companies.length === 0 && (
                        <tr>
                          <td colSpan={5} className="p-8 text-center text-zinc-500 italic">
                            No companies match current filters.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Pagination bar */}
              <div className="flex items-center justify-between mt-3 font-mono text-[10px] text-zinc-500 px-1">
                <span>Total Items: {pagination.total_items}</span>
                <div className="flex items-center gap-3">
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    disabled={page === 1 || companiesQuery.isLoading}
                    onClick={() => setPage(page - 1)}
                  >
                    ◀ PREV
                  </Button>
                  <span>
                    Page {page} of {pagination.total_pages || 1}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    disabled={page >= pagination.total_pages || companiesQuery.isLoading}
                    onClick={() => setPage(page + 1)}
                  >
                    NEXT ▶
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col gap-3 min-h-0">
              <div className="space-y-1">
                <label className="block text-zinc-400 text-3xs uppercase tracking-wider">
                  Paste ticker/CVM/CNPJ list
                </label>
                <textarea
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  placeholder="Paste e.g.: VALE3, PETR4.SA, 19739, 33529&#10;Separated by spaces, commas or newlines..."
                  className="w-full h-32 bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded p-2 focus:outline-none text-[11px] placeholder:text-zinc-700"
                />
              </div>

              <div className="flex justify-end">
                <Button
                  type="button"
                  onClick={handleResolvePaste}
                  disabled={resolving || !rawText.trim()}
                  loading={resolving}
                >
                  Resolve Tickers
                </Button>
              </div>

              {/* Resolution Summary */}
              {(resolvedList.length > 0 || unmappedList.length > 0) && (
                <div className="flex-1 grid grid-cols-2 gap-4 border border-[var(--color-border-subtle)] rounded p-3 bg-[var(--color-surface-2)] min-h-0 overflow-hidden">
                  <div className="flex flex-col min-h-0">
                    <span className="block text-emerald-400 font-bold mb-1.5 uppercase text-3xs tracking-widest">
                      ✔ Resolved ({resolvedList.length})
                    </span>
                    <div className="flex-1 overflow-y-auto bg-zinc-950/45 border border-zinc-900 rounded p-1.5 space-y-1">
                      {resolvedList.map((item, idx) => (
                        <div key={idx} className="flex items-center justify-between text-3xs text-zinc-300">
                          <span className="font-bold text-zinc-100">{item.ticker_b3 || `CVM ${item.cd_cvm}`}</span>
                          <span className="truncate max-w-[160px] text-zinc-500">{item.company_name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-col min-h-0">
                    <span className="block text-red-400 font-bold mb-1.5 uppercase text-3xs tracking-widest">
                      ❌ Unmapped / Invalid ({unmappedList.length})
                    </span>
                    <div className="flex-1 overflow-y-auto bg-zinc-950/45 border border-zinc-900 rounded p-1.5 space-y-1">
                      {unmappedList.map((val, idx) => (
                        <div key={idx} className="text-3xs text-red-300 font-mono">
                          {val}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Form Settings */}
        <footer className="p-4 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] space-y-3 shrink-0">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-zinc-400 text-3xs uppercase tracking-wider mb-1">
                Target Coverage Tier
              </label>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value)}
                className="w-full bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded px-2 py-1.5 focus:outline-none text-zinc-200"
              >
                <option value="must_cover">Must Cover</option>
                <option value="core">Core Coverage</option>
                <option value="watchlist">Watchlist</option>
                <option value="opportunistic">Opportunistic</option>
                <option value="excluded">Excluded</option>
                <option value="inappropriate">Not Appropriate</option>
                <option value="none">⚠️ Remove from Workspace</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-zinc-400 text-3xs uppercase tracking-wider mb-1">
                Change Rationale *
              </label>
              <input
                type="text"
                required
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="Required for audit trail..."
                className={`w-full bg-[var(--color-surface-3)] border rounded px-2.5 py-1.5 focus:outline-none text-zinc-200 placeholder:text-zinc-700 ${
                  !rationale.trim() ? "border-red-900/60 focus:border-red-800" : "border-[var(--color-border-default)] focus:border-cyan-500"
                }`}
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-2">
            <span className="text-3xs text-zinc-500 font-mono">
              Selected: <strong className="text-zinc-200">{selectedIds.size}</strong> companies
            </span>
            <div className="flex items-center gap-2">
              <Button type="button" variant="ghost" onClick={onClose} disabled={bulkMutation.isPending}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                onClick={() => bulkMutation.mutate()}
                disabled={bulkMutation.isPending || selectedIds.size === 0 || !rationale.trim()}
                loading={bulkMutation.isPending}
              >
                Apply Changes
              </Button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
