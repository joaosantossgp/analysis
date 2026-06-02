import { useEffect, useRef, useState } from "react";

import { Checkbox } from "@/components/ui/Checkbox";
import type { ExplorerFilters, Facets, FacetOption, SortKey } from "@/lib/indicators/registry";
import { SORT_OPTIONS } from "@/lib/indicators/registry";

/** Which `ExplorerFilters` array a facet dropdown writes to. */
export type FilterDimension = keyof ExplorerFilters;

interface ExplorerToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  facets: Facets;
  filters: ExplorerFilters;
  onToggleFilter: (dimension: FilterDimension, key: string) => void;
  onClearFilters: () => void;
  hasActiveFilters: boolean;
  sort: SortKey;
  onSortChange: (sort: SortKey) => void;
  favoritesOnly: boolean;
  onToggleFavoritesOnly: () => void;
  favoritesCount: number;
  resultCount: number;
  totalCount: number;
}

const DIMENSIONS: Array<{ id: FilterDimension; label: string; pick: (f: Facets) => FacetOption[] }> = [
  { id: "themes", label: "Theme", pick: (f) => f.themes },
  { id: "sources", label: "Source", pick: (f) => f.sources },
  { id: "frequencies", label: "Frequency", pick: (f) => f.frequencies },
  { id: "geographies", label: "Geography", pick: (f) => f.geographies },
  { id: "statuses", label: "Status", pick: (f) => f.statuses },
  { id: "valueTypes", label: "Type", pick: (f) => f.valueTypes },
];

export function ExplorerToolbar({
  search,
  onSearchChange,
  facets,
  filters,
  onToggleFilter,
  onClearFilters,
  hasActiveFilters,
  sort,
  onSortChange,
  favoritesOnly,
  onToggleFavoritesOnly,
  favoritesCount,
  resultCount,
  totalCount,
}: ExplorerToolbarProps) {
  // Local text state debounced (300ms) up to the parent — keeps typing snappy.
  const [text, setText] = useState(search);
  useEffect(() => setText(search), [search]);
  useEffect(() => {
    const t = setTimeout(() => onSearchChange(text), 300);
    return () => clearTimeout(t);
  }, [text, onSearchChange]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div style={{ position: "relative", flex: "1 1 240px", minWidth: 200 }}>
          <span
            aria-hidden="true"
            className="font-mono"
            style={{
              position: "absolute",
              left: 10,
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-sm)",
              pointerEvents: "none",
            }}
          >
            ⌕
          </span>
          <input
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search name, source, theme, unit, geography…"
            aria-label="Search indicators"
            className="focus-visible:outline focus-visible:outline-1"
            style={{
              width: "100%",
              background: "var(--color-surface-1)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-text-primary)",
              fontSize: "var(--text-sm)",
              height: 30,
              outlineColor: "var(--color-border-focus)",
              padding: "0 10px 0 28px",
            }}
          />
        </div>

        <div className="flex items-center gap-1.5">
          <label
            style={{
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-2xs)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            Sort
          </label>
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as SortKey)}
            aria-label="Sort indicators"
            className="font-mono focus-visible:outline focus-visible:outline-1"
            style={{
              background: "var(--color-surface-1)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-xs)",
              height: 30,
              outlineColor: "var(--color-border-focus)",
              padding: "0 8px",
            }}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {DIMENSIONS.map((dim) => (
          <FacetDropdown
            key={dim.id}
            label={dim.label}
            options={dim.pick(facets)}
            selected={filters[dim.id]}
            onToggle={(key) => onToggleFilter(dim.id, key)}
          />
        ))}

        <ToggleButton active={favoritesOnly} onClick={onToggleFavoritesOnly}>
          ★ Favorites{favoritesCount > 0 ? ` · ${favoritesCount}` : ""}
        </ToggleButton>

        {hasActiveFilters || favoritesOnly ? (
          <button
            type="button"
            onClick={onClearFilters}
            className="font-mono focus-visible:outline focus-visible:outline-1"
            style={{
              background: "transparent",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-text-tertiary)",
              cursor: "pointer",
              fontSize: "var(--text-xs)",
              height: 26,
              outlineColor: "var(--color-border-focus)",
              padding: "0 10px",
            }}
          >
            Clear filters
          </button>
        ) : null}

        <span
          className="font-mono"
          style={{
            color: "var(--color-text-tertiary)",
            fontSize: "var(--text-2xs)",
            marginLeft: "auto",
          }}
        >
          {resultCount} of {totalCount}
        </span>
      </div>
    </div>
  );
}

function ToggleButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className="font-mono focus-visible:outline focus-visible:outline-1"
      style={{
        background: active ? "var(--color-surface-3)" : "var(--color-surface-1)",
        border: `1px solid ${active ? "var(--color-action-primary)" : "var(--color-border-default)"}`,
        borderRadius: "var(--radius-md)",
        color: active ? "var(--color-action-primary)" : "var(--color-text-secondary)",
        cursor: "pointer",
        fontSize: "var(--text-xs)",
        height: 26,
        outlineColor: "var(--color-border-focus)",
        padding: "0 10px",
      }}
    >
      {children}
    </button>
  );
}

function FacetDropdown({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: FacetOption[];
  selected: string[];
  onToggle: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const count = selected.length;
  const disabled = options.length === 0;

  return (
    <div ref={rootRef} style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="font-mono focus-visible:outline focus-visible:outline-1"
        style={{
          background: count > 0 ? "var(--color-surface-3)" : "var(--color-surface-1)",
          border: `1px solid ${count > 0 ? "var(--color-action-primary)" : "var(--color-border-default)"}`,
          borderRadius: "var(--radius-md)",
          color: disabled
            ? "var(--color-text-disabled)"
            : count > 0
              ? "var(--color-action-primary)"
              : "var(--color-text-secondary)",
          cursor: disabled ? "not-allowed" : "pointer",
          fontSize: "var(--text-xs)",
          height: 26,
          outlineColor: "var(--color-border-focus)",
          padding: "0 10px",
        }}
      >
        {label}
        {count > 0 ? ` · ${count}` : ""}
        <span aria-hidden="true" style={{ marginLeft: 6, color: "var(--color-text-tertiary)" }}>
          ▾
        </span>
      </button>

      {open ? (
        <>
          <button
            type="button"
            aria-label={`Close ${label} filter`}
            tabIndex={-1}
            onClick={() => setOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "transparent",
              border: "none",
              cursor: "default",
              zIndex: 40,
            }}
          />
          <div
            role="listbox"
            aria-multiselectable="true"
            style={{
              position: "absolute",
              top: "calc(100% + 4px)",
              left: 0,
              width: 240,
              maxHeight: 320,
              overflowY: "auto",
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-overlay)",
              padding: 8,
              zIndex: 50,
            }}
          >
            {options.map((opt) => (
              <label
                key={opt.key}
                style={{
                  alignItems: "center",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  display: "flex",
                  gap: 8,
                  justifyContent: "space-between",
                  padding: "4px 4px",
                }}
              >
                <span style={{ alignItems: "center", display: "flex", gap: 8, minWidth: 0 }}>
                  <Checkbox
                    checked={selected.includes(opt.key)}
                    onChange={() => onToggle(opt.key)}
                  />
                  <span
                    className="truncate"
                    style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)" }}
                    title={opt.label}
                  >
                    {opt.label}
                  </span>
                </span>
                <span
                  className="font-mono"
                  style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
                >
                  {opt.count}
                </span>
              </label>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
