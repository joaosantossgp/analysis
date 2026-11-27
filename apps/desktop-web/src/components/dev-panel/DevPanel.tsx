import { useEffect, useReducer, useRef, useState } from "react";
import type { CSSProperties, PointerEvent } from "react";

import { IconButton } from "@/components/ui/IconButton";
import { Kbd } from "@/components/ui/Kbd";
import { useGlobalHotkeys } from "@/lib/keyboard/useGlobalHotkeys";

import { devPanelOpenReducer, resolveDevPanelKey } from "./devPanelState";
import { DEV_PANEL_SECTIONS } from "./sections";

const POSITION_KEY = "cvm_dev_panel_dot";
const DOT = 20;
const GAP = 8;
const MARGIN = 12;
/** Default corner: bottom right, above the status strip. */
const DEFAULT_BOTTOM = 32;
const DRAG_THRESHOLD = 4;

type Position = { x: number; y: number };

function loadPosition(): Position | null {
  try {
    const saved = JSON.parse(window.localStorage.getItem(POSITION_KEY) ?? "null");
    return typeof saved?.x === "number" && typeof saved?.y === "number" ? { x: saved.x, y: saved.y } : null;
  } catch {
    return null; // no window (static render), storage blocked, or a malformed value
  }
}

/**
 * Dev panel: a floating dot that opens the owner's dev functions. Dev mode
 * only; mounted through `./index`, which resolves to nothing in a production
 * build. Sections live in `./sections/*Section.tsx`.
 */
export function DevPanel({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, dispatch] = useReducer(devPanelOpenReducer, defaultOpen);
  const [position, setPosition] = useState<Position | null>(loadPosition);
  const dotRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ startX: number; startY: number; offsetX: number; offsetY: number; moved: boolean } | null>(null);
  const wasOpen = useRef(open);

  useGlobalHotkeys(
    ["ctrl+shift+d", "escape"],
    (event) => {
      const action = resolveDevPanelKey(event, open);
      if (!action) return;
      if (action === "toggle") event.preventDefault();
      dispatch(action);
    },
    { enabledInInputs: true },
  );

  // Keyboard focus follows the panel: into it on open, back to the dot on close.
  useEffect(() => {
    if (open) panelRef.current?.focus();
    else if (wasOpen.current) dotRef.current?.focus();
    wasOpen.current = open;
  }, [open]);

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    drag.current = {
      startX: event.clientX,
      startY: event.clientY,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
    if (!current.moved && Math.hypot(event.clientX - current.startX, event.clientY - current.startY) < DRAG_THRESHOLD) return;
    current.moved = true;
    setPosition({
      x: Math.max(0, Math.min(event.clientX - current.offsetX, window.innerWidth - DOT)),
      y: Math.max(0, Math.min(event.clientY - current.offsetY, window.innerHeight - DOT)),
    });
  }

  function onPointerUp() {
    if (!drag.current?.moved || !position) return;
    try {
      window.localStorage.setItem(POSITION_KEY, JSON.stringify(position));
    } catch {
      // The dot still moves; it only returns to its corner on the next load.
    }
  }

  function onClick() {
    const dragged = drag.current?.moved;
    drag.current = null;
    if (!dragged) dispatch("toggle"); // a drag ends in a click event too
  }

  // The panel opens towards the larger side of the window. `min()` keeps a
  // saved position reachable after the window shrinks.
  const alignLeft = position ? position.x < window.innerWidth / 2 : false;
  const below = position ? position.y < window.innerHeight / 2 : false;
  const anchor: CSSProperties = position
    ? {
        left: `min(${position.x}px, calc(100vw - ${DOT}px))`,
        top: `min(${position.y}px, calc(100vh - ${DOT}px))`,
      }
    : { right: MARGIN, bottom: DEFAULT_BOTTOM };
  const reserved = DOT + GAP + MARGIN;
  const maxHeight = !position
    ? `calc(100vh - ${DEFAULT_BOTTOM + reserved}px)`
    : below
      ? `calc(100vh - ${position.y + reserved}px)`
      : `${position.y - GAP - MARGIN}px`;

  return (
    <div style={{ position: "fixed", zIndex: "var(--z-toast)" as unknown as number, ...anchor }}>
      <button
        ref={dotRef}
        type="button"
        aria-label="Dev panel"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="dev-panel"
        title="Dev panel (Ctrl+Shift+D). Drag to move."
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="grid place-items-center rounded-full opacity-70 hover:opacity-100 focus-visible:opacity-100"
        style={{
          width: DOT,
          height: DOT,
          padding: 0,
          background: "var(--color-surface-3)",
          border: `1px solid ${open ? "var(--color-action-primary)" : "var(--color-border-strong)"}`,
          cursor: "grab",
          touchAction: "none",
          opacity: open ? 1 : undefined,
        }}
      >
        <span
          aria-hidden="true"
          className="rounded-full"
          style={{ width: 8, height: 8, background: "var(--color-action-primary)" }}
        />
      </button>
      {open ? (
        <div
          id="dev-panel"
          ref={panelRef}
          role="dialog"
          aria-label="Dev panel"
          tabIndex={-1}
          style={{
            position: "absolute",
            [alignLeft ? "left" : "right"]: 0,
            [below ? "top" : "bottom"]: DOT + GAP,
            width: `min(380px, calc(100vw - ${2 * MARGIN}px))`,
            maxHeight,
            overflow: "auto",
            background: "var(--color-surface-2)",
            border: "1px solid var(--color-border-default)",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--shadow-overlay)",
          }}
        >
          <div className="flex items-center gap-2 px-3 py-2">
            <h2 className="text-sm font-semibold" style={{ color: "var(--color-text-primary)", margin: 0 }}>
              Dev panel
            </h2>
            <span
              className="rounded-sm border px-1 font-mono text-2xs uppercase tracking-wider"
              style={{ borderColor: "var(--color-border-strong)", color: "var(--color-text-tertiary)" }}
            >
              Dev mode only
            </span>
            <span className="ml-auto flex items-center gap-2">
              <Kbd>Ctrl+Shift+D</Kbd>
              <IconButton aria-label="Close dev panel" title="Close (Esc)" onClick={() => dispatch("close")}>
                ×
              </IconButton>
            </span>
          </div>
          {DEV_PANEL_SECTIONS.map(({ id, Component }) => (
            <Component key={id} closePanel={() => dispatch("close")} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
