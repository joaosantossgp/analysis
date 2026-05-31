import { useEffect, useRef, useState } from "react";

import { Checkbox } from "@/components/ui/Checkbox";
import { formatUnit } from "@/lib/formatters";
import { groupIndicators } from "@/lib/indicators/catalog";
import type { IndicatorDef } from "@/lib/indicators/types";

interface IndicatorPickerProps {
  defs: IndicatorDef[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  /** Max number of indicators that can be selected at once. */
  maxSelected?: number;
}

/**
 * Dropdown multi-select for indicators, grouped by category. Unavailable or
 * placeholder indicators are shown but disabled, with an explicit reason, so
 * the user understands why a metric cannot be plotted instead of it silently
 * missing.
 */
export function IndicatorPicker({
  defs,
  selectedIds,
  onToggle,
  maxSelected = 6,
}: IndicatorPickerProps) {
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

  const groups = groupIndicators(defs);
  const selectedSet = new Set(selectedIds);
  const atLimit = selectedIds.length >= maxSelected;

  return (
    <div ref={rootRef} style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="font-mono focus-visible:outline focus-visible:outline-1"
        style={{
          background: "var(--color-surface-1)",
          border: "1px solid var(--color-border-default)",
          borderRadius: "var(--radius-md)",
          color: "var(--color-text-secondary)",
          cursor: "pointer",
          fontSize: "var(--text-xs)",
          height: 26,
          outlineColor: "var(--color-border-focus)",
          padding: "0 10px",
        }}
      >
        Indicators · {selectedIds.length}
        <span aria-hidden="true" style={{ marginLeft: 6, color: "var(--color-text-tertiary)" }}>
          ▾
        </span>
      </button>

      {open ? (
        <>
          {/* Click-outside capture */}
          <button
            type="button"
            aria-label="Close indicator picker"
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
              width: 300,
              maxHeight: 360,
              overflowY: "auto",
              background: "var(--color-surface-2)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--shadow-overlay)",
              padding: 8,
              zIndex: 50,
            }}
          >
            <div
              style={{
                color: "var(--color-text-tertiary)",
                fontSize: "var(--text-2xs)",
                marginBottom: 6,
                padding: "0 2px",
              }}
            >
              {selectedIds.length}/{maxSelected} selected
            </div>
            {groups.map((group) => (
              <div key={group.category} style={{ marginBottom: 8 }}>
                <div
                  style={{
                    color: "var(--color-text-tertiary)",
                    fontSize: "var(--text-2xs)",
                    letterSpacing: "0.04em",
                    margin: "4px 2px",
                    textTransform: "uppercase",
                  }}
                >
                  {group.label}
                </div>
                {group.items.map((def) => {
                  const checked = selectedSet.has(def.id);
                  const blockedByLimit = !checked && atLimit;
                  const disabled = !def.available || blockedByLimit;
                  const reason = !def.available
                    ? def.isPlaceholder
                      ? "planned"
                      : "n/a"
                    : blockedByLimit
                      ? "max"
                      : null;
                  return (
                    <label
                      key={def.id}
                      style={{
                        alignItems: "center",
                        borderRadius: "var(--radius-sm)",
                        cursor: disabled ? "not-allowed" : "pointer",
                        display: "flex",
                        gap: 8,
                        justifyContent: "space-between",
                        opacity: disabled ? 0.45 : 1,
                        padding: "3px 4px",
                      }}
                    >
                      <span style={{ alignItems: "center", display: "flex", gap: 8, minWidth: 0 }}>
                        <Checkbox
                          checked={checked}
                          disabled={disabled}
                          onChange={() => onToggle(def.id)}
                        />
                        <span
                          className="truncate"
                          style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)" }}
                          title={def.label}
                        >
                          {def.label}
                        </span>
                      </span>
                      <span
                        className="font-mono"
                        style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
                      >
                        {reason ?? formatUnit(def.unit)}
                      </span>
                    </label>
                  );
                })}
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
