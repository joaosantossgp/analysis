import { useState, useMemo } from "react";
import type { CoverageUniverse } from "@/lib/api/coverage";
import { Button } from "@/components/ui/Button";

type Props = {
  universes: CoverageUniverse[];
  activeUniverseId: string;
  onSelectUniverse: (id: string) => void;
  onOpenCreateModal: () => void;
};

export function UniverseSidebar({
  universes,
  activeUniverseId,
  onSelectUniverse,
  onOpenCreateModal,
}: Props) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return universes;
    const q = search.toLowerCase();
    return universes.filter(
      (u) =>
        u.name.toLowerCase().includes(q) ||
        (u.benchmark && u.benchmark.toLowerCase().includes(q))
    );
  }, [universes, search]);

  const grouped = useMemo(() => {
    return {
      active: filtered.filter((u) => u.status === "active"),
      draft: filtered.filter((u) => u.status === "draft"),
      archived: filtered.filter((u) => u.status === "archived"),
    };
  }, [filtered]);

  function getAnalysisTypeBadge(type: string) {
    const label = type === "Portfolio Monitoring" ? "PORT" : type === "Sector Watch" ? "SECT" : type.toUpperCase().slice(0, 4);
    let color = "text-zinc-400 border-zinc-700 bg-zinc-950";
    if (type === "Equity") color = "text-cyan-400 border-cyan-900 bg-cyan-950/40";
    if (type === "Credit") color = "text-emerald-400 border-emerald-900 bg-emerald-950/40";
    if (type === "IB") color = "text-pink-400 border-pink-900 bg-pink-950/40";
    if (type === "Portfolio Monitoring") color = "text-amber-400 border-amber-900 bg-amber-950/40";
    if (type === "Sector Watch") color = "text-sky-400 border-sky-900 bg-sky-950/40";

    return (
      <span className={`font-mono text-[9px] font-bold border px-1 rounded-sm uppercase tracking-wider ${color}`}>
        {label}
      </span>
    );
  }

  if (isCollapsed) {
    return (
      <aside
        className="flex flex-col items-center py-4 border-r border-[var(--color-border-subtle)] h-full bg-[#0d0f12] select-none"
        style={{ width: 48, transition: "width 180ms ease-out" }}
      >
        <button
          type="button"
          onClick={() => setIsCollapsed(false)}
          className="p-1 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] focus:outline-none mb-4"
          title="Expand Explorer"
        >
          ▶
        </button>
        <button
          type="button"
          onClick={onOpenCreateModal}
          className="w-8 h-8 flex items-center justify-center rounded bg-[var(--color-surface-3)] text-cyan-400 hover:bg-cyan-950 hover:text-cyan-300 font-bold focus:outline-none border border-cyan-900/60"
          title="New Universe"
        >
          +
        </button>
        <div className="flex-1 w-full flex flex-col gap-3 mt-6 items-center overflow-y-auto">
          {universes.map((u) => {
            const isActive = u.id === activeUniverseId;
            return (
              <button
                key={u.id}
                type="button"
                onClick={() => onSelectUniverse(u.id)}
                className={`w-7 h-7 flex items-center justify-center text-xs font-mono font-bold rounded-sm border ${
                  isActive
                    ? "bg-cyan-950 text-cyan-400 border-cyan-600"
                    : "bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] border-[var(--color-border-subtle)] hover:text-text-primary"
                }`}
                title={`${u.name} (${u.company_count} cos)`}
              >
                {u.name.slice(0, 2).toUpperCase()}
              </button>
            );
          })}
        </div>
      </aside>
    );
  }

  return (
    <aside
      className="flex flex-col border-r border-[var(--color-border-subtle)] h-full bg-[#0d0f12] select-none text-xs font-mono"
      style={{ width: 280, transition: "width 180ms ease-out" }}
    >
      {/* Explorer Header */}
      <header className="p-3 border-b border-[var(--color-border-subtle)] flex items-center justify-between">
        <span className="font-bold tracking-wider text-[var(--color-text-primary)] uppercase text-[10px]">
          WORKSPACE EXPLORER
        </span>
        <button
          type="button"
          onClick={() => setIsCollapsed(true)}
          className="text-zinc-500 hover:text-zinc-200 focus:outline-none text-[10px]"
          title="Collapse Explorer"
        >
          ◀
        </button>
      </header>

      {/* Search & Actions */}
      <div className="p-3 border-b border-[var(--color-border-subtle)] space-y-2">
        <input
          type="search"
          placeholder="Search workspace..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-[var(--color-surface-2)] border border-[var(--color-border-default)] rounded px-2.5 py-1 focus:outline-none text-[11px] text-zinc-200 placeholder:text-zinc-600"
        />
        <Button
          type="button"
          variant="secondary"
          size="xs"
          block
          onClick={onOpenCreateModal}
          style={{ borderColor: "rgba(34,211,238,0.3)", color: "var(--color-id-ticker)" }}
        >
          + NEW UNIVERSE
        </Button>
      </div>

      {/* Universes List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-4">
        {(["active", "draft", "archived"] as const).map((group) => {
          const list = grouped[group];
          if (list.length === 0) return null;

          return (
            <div key={group} className="space-y-1">
              <div className="px-2 py-0.5 text-4xs font-bold text-zinc-600 uppercase tracking-widest flex items-center justify-between">
                <span>{group}</span>
                <span className="bg-zinc-950 px-1 rounded border border-zinc-900 text-3xs text-zinc-500">
                  {list.length}
                </span>
              </div>
              <div className="space-y-0.5">
                {list.map((u) => {
                  const isActive = u.id === activeUniverseId;
                  return (
                    <button
                      key={u.id}
                      type="button"
                      onClick={() => onSelectUniverse(u.id)}
                      className={`w-full text-left px-2 py-1.5 rounded flex items-center justify-between gap-2 transition-colors ${
                        isActive
                          ? "bg-[var(--color-surface-3)] border border-cyan-800 text-[var(--color-text-primary)]"
                          : "hover:bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] border border-transparent"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <span className={`block font-medium truncate text-2xs ${isActive ? "text-cyan-400" : ""}`}>
                          {u.name}
                        </span>
                        {u.benchmark && (
                          <span className="block text-4xs text-zinc-500 truncate mt-0.5">
                            Bench: {u.benchmark}
                          </span>
                        )}
                      </div>
                      <div className="shrink-0 flex items-center gap-1.5 text-right font-mono">
                        {getAnalysisTypeBadge(u.analysis_type)}
                        <span className="text-3xs text-zinc-500 px-1 bg-zinc-950/65 rounded border border-zinc-900/60 font-semibold min-w-[32px] text-center">
                          {u.company_count}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center py-6 text-zinc-600 text-3xs italic">
            No workspaces found.
          </div>
        )}
      </div>
    </aside>
  );
}
