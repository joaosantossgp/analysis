import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createCoverageUniverse, deleteCoverageUniverse, duplicateCoverageUniverse, type CoverageUniverse } from "@/lib/api/coverage";
import { Button } from "@/components/ui/Button";

// --- Delete Universe Button ---
export function DeleteUniverseButton({ universeId, onSuccess }: { universeId: string; onSuccess: () => void }) {
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
export function CreateUniverseModal({
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
export function DuplicateUniverseModal({
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
export function DashboardHub({
  universes,
  showArchived,
  onShowArchivedChange,
  onSelectUniverse,
  onOpenCreateModal,
  onOpenDuplicateModal,
  onArchiveUniverse,
}: {
  universes: CoverageUniverse[];
  showArchived: boolean;
  onShowArchivedChange: (val: boolean) => void;
  onSelectUniverse: (id: string) => void;
  onOpenCreateModal: () => void;
  onOpenDuplicateModal: (id: string) => void;
  onArchiveUniverse: (id: string, currentStatus: string) => void;
}) {
  return (
    <div className="space-y-6 font-mono text-xs select-none">
      <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-4">
        <div className="flex items-center gap-6">
          <div>
            <h1 className="text-lg font-bold text-zinc-150 uppercase tracking-wider">COVERAGE WORKSPACES</h1>
            <p className="text-3xs text-[var(--color-text-tertiary)] mt-1">
              Manage your stock coverage lists, priority weights, and checklists.
            </p>
          </div>
          <label className="flex items-center gap-1.5 cursor-pointer text-2xs text-[var(--color-text-secondary)] font-mono select-none">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => onShowArchivedChange(e.target.checked)}
              className="bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded accent-cyan-600"
            />
            Show Archived
          </label>
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
                  {u.status === "archived" ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onArchiveUniverse(u.id, "archived");
                      }}
                      className="p-1 px-2 border border-transparent rounded hover:border-emerald-900 hover:bg-emerald-950/30 text-emerald-400 transition-all text-2xs font-bold"
                    >
                      Restore
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onArchiveUniverse(u.id, u.status);
                      }}
                      className="p-1 px-2 border border-transparent rounded hover:border-zinc-700 hover:bg-zinc-800 text-zinc-400 transition-all text-2xs"
                    >
                      Archive
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
