// PROTOTYPE (throwaway, dev-only): data shell variants. Do not import from production code paths except the gated slots.
import { useEffect } from "react";

import {
  cycleState,
  cycleVariant,
  DATA_SHELL_STATES,
  exitPrototype,
  useDataShellPrototype,
  VARIANT_NAMES,
} from "./store";

const btn = "rounded px-2 py-0.5 hover:bg-black/10";

export function PrototypeSwitcher() {
  const s = useDataShellPrototype();

  useEffect(() => {
    if (!s.active) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.closest("input, textarea, select, [contenteditable='true']") || t.isContentEditable)) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const map: Record<string, () => void> = {
        ArrowLeft: () => cycleVariant(-1),
        ArrowRight: () => cycleVariant(1),
        ArrowUp: () => cycleState(-1),
        ArrowDown: () => cycleState(1),
      };
      const fn = map[e.key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.active]);

  if (!s.active) return null;
  const stateLabel = DATA_SHELL_STATES.find((x) => x.key === s.state)?.label ?? s.state;

  return (
    <div
      role="toolbar"
      aria-label="Prototype switcher"
      className="flex items-center gap-3 font-mono text-xs"
      style={{
        position: "fixed",
        left: "50%",
        bottom: 36,
        transform: "translateX(-50%)",
        zIndex: 90,
        background: "#f5f5f5",
        color: "#000",
        border: "1px solid #000",
        borderRadius: 6,
        padding: "6px 10px",
        boxShadow: "0 6px 20px rgba(0,0,0,.5)",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ fontWeight: 700 }}>PROTOTYPE · simulated data</span>
      <span aria-hidden="true">|</span>
      <button type="button" className={btn} onClick={() => cycleVariant(-1)} aria-label="Previous variant">‹</button>
      <span style={{ minWidth: 250, textAlign: "center" }}>
        <b>{s.variant}</b> · {VARIANT_NAMES[s.variant]}
      </span>
      <button type="button" className={btn} onClick={() => cycleVariant(1)} aria-label="Next variant">›</button>
      <span aria-hidden="true">|</span>
      <button type="button" className={btn} onClick={() => cycleState(-1)} aria-label="Previous state">‹</button>
      <span style={{ minWidth: 170, textAlign: "center" }}>State: {stateLabel}</span>
      <button type="button" className={btn} onClick={() => cycleState(1)} aria-label="Next state">›</button>
      <span aria-hidden="true">|</span>
      <span style={{ color: "#555" }}>← → variant · ↑ ↓ state</span>
      <button type="button" className={btn} onClick={exitPrototype} style={{ textDecoration: "underline" }}>Exit</button>
    </div>
  );
}
