import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";

import { whenBridgeReady } from "@/lib/bridge/adapter";
import { StateBanner } from "@/components/feedback/StateBanner";
import { fetchDatabaseDiagnostics } from "@/lib/api/updateBase";

// Configurable Workspace imports
import { WORKSPACE_REGISTRY } from "@/components/home/WorkspaceRegistry";
import { WorkspaceConfigPanel } from "@/components/home/WorkspaceConfigPanel";

const STORAGE_IDS_KEY = "cvm:home:workspace:items:v4";
const STORAGE_CONFIG_KEY = "cvm:home:workspace:config:v4";

export interface LayoutItem {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  isMinimized: boolean;
  isCompact: boolean;
}

// ─── Grid Math Helpers ────────────────────────────────────────────────────────

export function resolveLayout(items: LayoutItem[], movingItemId?: string): LayoutItem[] {
  // Sort items: the item currently being moved/resized gets highest priority
  const sorted = [...items].sort((a, b) => {
    if (a.id === movingItemId) return -1;
    if (b.id === movingItemId) return 1;
    if (a.y !== b.y) return a.y - b.y;
    return a.x - b.x;
  });

  const resolved: LayoutItem[] = [];

  for (const item of sorted) {
    let currentY = item.y;
    let currentX = item.x;
    
    // Clamp width constraints
    let w = item.w;
    if (w > 3) w = 3;
    if (w < 1) w = 1;

    // Clamp height constraints
    let h = item.h;
    if (h < 2) h = 2; // minimum height is 2 rows for expanded state
    if (h > 6) h = 6; // safety maximum height

    // Ensure it fits within the 3-column boundary
    if (currentX + w > 3) {
      currentX = 3 - w;
      if (currentX < 0) {
        currentX = 0;
        w = 3;
      }
    }

    // Keep shifting down until there are no 2D overlaps
    let iterations = 0;
    while (iterations < 100) {
      iterations++;
      let hasOverlap = false;
      const height = Math.max(1, item.isMinimized ? 1 : h);

      for (const other of resolved) {
        const otherHeight = Math.max(1, other.isMinimized ? 1 : other.h);
        // Check overlap intersection
        const overlapX = currentX < other.x + other.w && currentX + w > other.x;
        const overlapY = currentY < other.y + otherHeight && currentY + height > other.y;

        if (overlapX && overlapY) {
          hasOverlap = true;
          currentY = other.y + otherHeight; // push down below the blocking widget
          break;
        }
      }

      if (!hasOverlap) {
        break;
      }
    }

    resolved.push({
      ...item,
      x: currentX,
      y: currentY,
      w,
      h,
    });
  }

  return resolved;
}

function findFirstEmptySlot(items: LayoutItem[], w: number, h: number): { x: number; y: number } {
  let y = 0;
  while (y < 500) {
    for (let x = 0; x <= 3 - w; x++) {
      let fits = true;
      for (const other of items) {
        const otherHeight = Math.max(1, other.isMinimized ? 1 : other.h);
        const overlapX = x < other.x + other.w && x + w > other.x;
        const overlapY = y < other.y + otherHeight && y + h > other.y;
        if (overlapX && overlapY) {
          fits = false;
          break;
        }
      }
      if (fits) {
        return { x, y };
      }
    }
    y++;
  }
  return { x: 0, y: 0 };
}

export function parseLayoutItems(saved: string | null): LayoutItem[] {
  if (!saved) return [];
  try {
    const parsed = JSON.parse(saved);
    if (!Array.isArray(parsed)) return [];
    
    const validItems: LayoutItem[] = [];
    for (const item of parsed) {
      if (!item || typeof item !== "object") continue;
      const { id, x, y, w, h, isMinimized, isCompact } = item;
      
      // Ignore unknown/unregistered widget IDs
      if (typeof id !== "string" || !WORKSPACE_REGISTRY[id]) {
        continue;
      }
      
      // Parse coordinates and sizes safely
      const parsedX = typeof x === "number" && !Number.isNaN(x) ? x : 0;
      const parsedY = typeof y === "number" && !Number.isNaN(y) ? y : 0;
      const parsedW = typeof w === "number" && !Number.isNaN(w) ? w : 1;
      const parsedH = typeof h === "number" && !Number.isNaN(h) ? h : 2;
      
      // Clamp coordinates and sizes
      const clampedW = Math.min(3, Math.max(1, parsedW));
      const clampedH = Math.min(6, Math.max(2, parsedH));
      const clampedX = Math.min(3 - clampedW, Math.max(0, parsedX));
      const clampedY = Math.max(0, parsedY);
      
      validItems.push({
        id,
        x: clampedX,
        y: clampedY,
        w: clampedW,
        h: clampedH,
        isMinimized: typeof isMinimized === "boolean" ? isMinimized : false,
        isCompact: typeof isCompact === "boolean" ? isCompact : false,
      });
    }
    return resolveLayout(validItems);
  } catch (e) {
    console.error("Failed to parse layout items", e);
    return [];
  }
}

export function parseCardConfigs(saved: string | null): Record<string, any> {
  const defaults = {
    watchlist: { companyIds: [], metric: "mg_ebit" },
    "priority-queue": { universeId: "" },
    "market-price": { cdCvm: 0, ticker: "", companyName: "" },
  };
  if (!saved) return defaults;
  try {
    const parsed = JSON.parse(saved);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return {
        ...defaults,
        ...parsed,
      };
    }
    return defaults;
  } catch (e) {
    console.error("Failed to parse card configs", e);
    return defaults;
  }
}

export const RECOMMENDED_LAYOUT: LayoutItem[] = [
  { id: "database-status", x: 0, y: 0, w: 3, h: 3, isMinimized: false, isCompact: false },
  { id: "watchlist", x: 0, y: 3, w: 2, h: 2, isMinimized: false, isCompact: false },
  { id: "market-price", x: 2, y: 3, w: 1, h: 2, isMinimized: false, isCompact: false },
  { id: "priority-queue", x: 0, y: 5, w: 2, h: 2, isMinimized: false, isCompact: false },
  { id: "top-news", x: 0, y: 7, w: 2, h: 2, isMinimized: false, isCompact: false },
];


export function HomePage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [activeCards, setActiveCards] = useState<LayoutItem[]>([]);
  const [cardConfigs, setCardConfigs] = useState<Record<string, any>>({});
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [focusedCardId, setFocusedCardId] = useState<string | null>(null);

  // Dragging states
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [dragCurrentPos, setDragCurrentPos] = useState({ x: 0, y: 0 });
  const [dragStartSize, setDragStartSize] = useState({ w: 0, h: 0 });
  const [dragSnapPreview, setDragSnapPreview] = useState<{ x: number; y: number } | null>(null);

  const gridRef = useRef<HTMLDivElement>(null);

  // Keep track of active window listeners to avoid leaks if unmounted during interaction
  const activeListenersRef = useRef<{
    mousemove?: (e: MouseEvent) => void;
    mouseup?: (e: MouseEvent) => void;
  }>({});

  const cleanupListeners = () => {
    if (activeListenersRef.current.mousemove) {
      window.removeEventListener("mousemove", activeListenersRef.current.mousemove);
      activeListenersRef.current.mousemove = undefined;
    }
    if (activeListenersRef.current.mouseup) {
      window.removeEventListener("mouseup", activeListenersRef.current.mouseup);
      activeListenersRef.current.mouseup = undefined;
    }
  };

  // 1. Initialize and load configuration from localStorage safely
  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });

    try {
      const savedItems = localStorage.getItem(STORAGE_IDS_KEY);
      setActiveCards(parseLayoutItems(savedItems));

      const savedConfigs = localStorage.getItem(STORAGE_CONFIG_KEY);
      setCardConfigs(parseCardConfigs(savedConfigs));
    } catch (e) {
      console.error("Failed to load workspace layout", e);
    }

    return () => {
      cancelled = true;
      cleanupListeners();
    };
  }, []);

  // 2. Persist configurations to localStorage
  useEffect(() => {
    if (bridgeReady) {
      try {
        localStorage.setItem(STORAGE_IDS_KEY, JSON.stringify(activeCards));
      } catch (e) {
        console.error("Failed to save layout items", e);
      }
    }
  }, [activeCards, bridgeReady]);

  useEffect(() => {
    if (bridgeReady) {
      try {
        localStorage.setItem(STORAGE_CONFIG_KEY, JSON.stringify(cardConfigs));
      } catch (e) {
        console.error("Failed to save card configs", e);
      }
    }
  }, [cardConfigs, bridgeReady]);

  // 3. Status checks for top-level warning banner (Browser fallback mode check)
  const diagQuery = useQuery({
    queryKey: ["db-diagnostics-summary"],
    queryFn: () => fetchDatabaseDiagnostics({ summaryOnly: true }),
    enabled: bridgeReady,
  });

  const browserReason =
    diagQuery.data?.mode === "browser" ? diagQuery.data.reason : null;

  // 4. Toggle Card Visibility (places in the first available gap)
  const handleToggleCard = (id: string) => {
    setActiveCards((prev) => {
      const exists = prev.some((x) => x.id === id);
      if (exists) {
        return prev.filter((x) => x.id !== id);
      } else {
        const cardDef = WORKSPACE_REGISTRY[id];
        const defaultW = cardDef.defaultSize === "large" ? 3 : cardDef.defaultSize === "medium" ? 2 : 1;
        const defaultH = cardDef.defaultSize === "large" ? 3 : 2;
        const { x, y } = findFirstEmptySlot(prev, defaultW, defaultH);
        
        const newItem: LayoutItem = {
          id,
          x,
          y,
          w: defaultW,
          h: defaultH,
          isMinimized: false,
          isCompact: false,
        };
        return resolveLayout([...prev, newItem], id);
      }
    });
  };

  // 5. Toggle Compact/Minimized states
  const handleToggleProperty = (id: string, property: "isCompact" | "isMinimized") => {
    setActiveCards((prev) => {
      const updated = prev.map((item) =>
        item.id === id ? { ...item, [property]: !item[property] } : item
      );
      return resolveLayout(updated, id);
    });
  };

  // 6. Update individual card configs
  const handleUpdateConfig = (cardId: string, newConfig: any) => {
    setCardConfigs((prev) => ({
      ...prev,
      [cardId]: newConfig,
    }));
  };

  // 7. Reset Workspace Layout
  const handleResetLayout = () => {
    setActiveCards([]);
    setCardConfigs({
      watchlist: { companyIds: [], metric: "mg_ebit" },
      "priority-queue": { universeId: "" },
      "market-price": { cdCvm: 0, ticker: "", companyName: "" },
    });
  };

  // 8. Custom Mouse-based drag-and-drop repositioning
  const handleDragHeaderMouseDown = (
    mouseDownEvent: React.MouseEvent,
    id: string
  ) => {
    if (!isEditMode) return;

    const target = mouseDownEvent.target as HTMLElement;
    
    // Only allow dragging if clicking on the card's header/drag area
    const header = target.closest("header");
    if (!header) return;

    // Abort if the user clicked on a control button, link, or input inside the header
    if (
      target.closest("button") ||
      target.closest("a") ||
      target.closest("input") ||
      target.closest("select")
    ) {
      return;
    }

    mouseDownEvent.preventDefault();
    document.body.style.cursor = "grabbing";

    const gridEl = gridRef.current;
    if (!gridEl) return;

    const cardEl = mouseDownEvent.currentTarget.closest(".group\\/card");
    if (!cardEl) return;

    const rect = cardEl.getBoundingClientRect();
    const gridRect = gridEl.getBoundingClientRect();

    // Mouse offsets relative to the top-left of the card itself
    const offsetX = mouseDownEvent.clientX - rect.left;
    const offsetY = mouseDownEvent.clientY - rect.top;

    setActiveDragId(id);
    setDragStartSize({ w: rect.width, h: rect.height });
    
    // Initial absolute coordinates relative to the grid container
    const initialPosX = rect.left - gridRect.left;
    const initialPosY = rect.top - gridRect.top;
    setDragCurrentPos({ x: initialPosX, y: initialPosY });

    const targetItem = activeCards.find((c) => c.id === id);
    if (targetItem) {
      setDragSnapPreview({ x: targetItem.x, y: targetItem.y });
    }

    cleanupListeners();

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const gEl = gridRef.current;
      if (!gEl) return;

      const gRect = gEl.getBoundingClientRect();
      
      // Compute raw mouse positions relative to container
      const currentX = moveEvent.clientX - gRect.left - offsetX;
      const currentY = moveEvent.clientY - gRect.top - offsetY;

      setDragCurrentPos({ x: currentX, y: currentY });

      // Snapping math: 3 columns, 136px vertical increments (120px height + 16px gap)
      const colWidth = gRect.width / 3;
      const rowHeight = 136;

      const item = activeCards.find((c) => c.id === id);
      if (!item) return;

      const snapX = Math.min(3 - item.w, Math.max(0, Math.round(currentX / colWidth)));
      const snapY = Math.max(0, Math.round(currentY / rowHeight));

      setDragSnapPreview({ x: snapX, y: snapY });
    };

    const handleMouseUp = (upEvent: MouseEvent) => {
      cleanupListeners();
      document.body.style.cursor = "";

      const gEl = gridRef.current;
      if (!gEl) {
        setActiveDragId(null);
        setDragSnapPreview(null);
        return;
      }

      const gRect = gEl.getBoundingClientRect();
      const finalX = upEvent.clientX - gRect.left - offsetX;
      const finalY = upEvent.clientY - gRect.top - offsetY;

      const colWidth = gRect.width / 3;
      const rowHeight = 136;

      const item = activeCards.find((c) => c.id === id);
      if (item) {
        const snapX = Math.min(3 - item.w, Math.max(0, Math.round(finalX / colWidth)));
        const snapY = Math.max(0, Math.round(finalY / rowHeight));

        setActiveCards((prev) => {
          const updated = prev.map((c) =>
            c.id === id ? { ...c, x: snapX, y: snapY } : c
          );
          return resolveLayout(updated, id);
        });
      }

      setActiveDragId(null);
      setDragSnapPreview(null);
    };

    activeListenersRef.current.mousemove = handleMouseMove;
    activeListenersRef.current.mouseup = handleMouseUp;

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // 10. Resize handlers (Width: snaps to 3 column segments. Height: snaps to 120px row increments)
  const handleResizeWidthMouseDown = (
    mouseDownEvent: React.MouseEvent,
    id: string,
    currentColSpan: number
  ) => {
    mouseDownEvent.stopPropagation();
    mouseDownEvent.preventDefault();
    document.body.style.cursor = "col-resize";

    const startX = mouseDownEvent.clientX;
    const gEl = gridRef.current;
    const gridColWidth = gEl ? gEl.getBoundingClientRect().width / 3 : 320;

    cleanupListeners();

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const step = Math.round(deltaX / gridColWidth);
      let nextColSpan = currentColSpan + step;
      if (nextColSpan < 1) nextColSpan = 1;
      if (nextColSpan > 3) nextColSpan = 3;

      if (nextColSpan !== currentColSpan) {
        setActiveCards((prev) => {
          const updated = prev.map((item) =>
            item.id === id ? { ...item, w: nextColSpan } : item
          );
          return resolveLayout(updated, id);
        });
      }
    };

    const handleMouseUp = () => {
      cleanupListeners();
      document.body.style.cursor = "";
    };

    activeListenersRef.current.mousemove = handleMouseMove;
    activeListenersRef.current.mouseup = handleMouseUp;

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  const handleResizeHeightMouseDown = (
    mouseDownEvent: React.MouseEvent,
    id: string,
    currentRowSpan: number
  ) => {
    mouseDownEvent.stopPropagation();
    mouseDownEvent.preventDefault();
    document.body.style.cursor = "row-resize";

    const startY = mouseDownEvent.clientY;
    const gridRowHeight = 136; // 120px height + 16px gap

    cleanupListeners();

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const step = Math.round(deltaY / gridRowHeight);
      let nextRowSpan = currentRowSpan + step;
      if (nextRowSpan < 2) nextRowSpan = 2; // minimum height
      if (nextRowSpan > 6) nextRowSpan = 6; // maximum height

      if (nextRowSpan !== currentRowSpan) {
        setActiveCards((prev) => {
          const updated = prev.map((item) =>
            item.id === id ? { ...item, h: nextRowSpan } : item
          );
          return resolveLayout(updated, id);
        });
      }
    };

    const handleMouseUp = () => {
      cleanupListeners();
      document.body.style.cursor = "";
    };

    activeListenersRef.current.mousemove = handleMouseMove;
    activeListenersRef.current.mouseup = handleMouseUp;

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  const activeCardIds = activeCards.map((c) => c.id);
  const maxCardY = activeCards.reduce(
    (max, c) => Math.max(max, c.y + (c.isMinimized ? 1 : c.h)),
    0
  );
  const numGridRows = Math.max(12, maxCardY + 4);

  return (
    <section className="space-y-4 p-4 md:p-6 min-h-full">
      {browserReason ? (
        <StateBanner variant="browser-only" message={browserReason} />
      ) : null}

      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-900 pb-3 font-mono">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-100 flex items-center gap-2">
            Analyst Workspace
            {isEditMode && (
              <span className="animate-pulse rounded bg-orange-500/10 px-1.5 py-0.5 text-3xs font-bold text-orange-400 border border-orange-500/20">
                EDIT MODE
              </span>
            )}
          </h2>
          <p className="text-3xs text-zinc-500 mt-0.5">
            {isEditMode
              ? "Hold mouse click on card headers to drag-move cards freely · Drag borders to resize"
              : "Lock status: widgets locked. Click Edit Layout to customize"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsEditMode(!isEditMode)}
            className={`inline-flex items-center rounded-md border px-3 py-1.5 text-xs font-semibold transition-all ${
              isEditMode
                ? "border-orange-500 bg-orange-500/10 text-orange-400"
                : "border-zinc-800 bg-zinc-955 text-zinc-400 hover:border-zinc-700 hover:text-zinc-300"
            }`}
          >
            {isEditMode ? "Lock Layout" : "Edit Layout"}
          </button>
          <button
            onClick={() => setIsConfigOpen(true)}
            className="inline-flex items-center rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-xs text-zinc-400 hover:border-zinc-700 hover:text-zinc-300 transition-all"
          >
            Widgets
          </button>
          <button
            onClick={handleResetLayout}
            className="inline-flex items-center rounded-md border border-zinc-850 bg-zinc-955 px-3 py-1.5 text-xs text-zinc-650 hover:border-zinc-800 hover:text-zinc-400 transition-all"
            title="Reset workspace"
          >
            Clear Workspace
          </button>
        </div>
      </div>

      {/* Main Grid Area */}
      {activeCards.length === 0 ? (
        <div className="border border-zinc-850 rounded-lg p-6 bg-zinc-900/10 max-w-2xl mx-auto mt-10 font-mono space-y-6">
          <div className="text-center space-y-2">
            <span className="text-orange-500 text-3xl block" aria-hidden="true">⛭</span>
            <h4 className="text-sm font-semibold uppercase tracking-wider text-zinc-100">
              Analyst Workspace Initial Setup
            </h4>
            <p className="text-2xs text-zinc-400 max-w-md mx-auto leading-relaxed">
              Configure your financial terminal workspace to track Brazilian company updates, coverage priorities, stock trend charts, and news feeds.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 border-t border-b border-zinc-850/60 py-6">
            <div className="border-r border-zinc-850/60 pr-4 flex flex-col justify-between space-y-4">
              <div>
                <h5 className="text-xs font-bold text-zinc-200 uppercase tracking-wide">Recommended Layout</h5>
                <p className="text-3xs text-zinc-500 mt-1 leading-normal">
                  Pre-populate your workspace with a balanced, multi-column dashboard containing:
                </p>
                <ul className="text-3xs text-zinc-400 mt-2 list-disc list-inside space-y-1">
                  <li>Database synchronization status</li>
                  <li>Watchlist with EBIT Margin KPI charts</li>
                  <li>Target ticker quote Sparkline</li>
                  <li>Active coverage prioritization queue</li>
                  <li>CVM filings and news alerts</li>
                </ul>
              </div>
              <button
                onClick={() => {
                  setActiveCards(resolveLayout(RECOMMENDED_LAYOUT));
                }}
                className="w-full text-center rounded bg-orange-500 hover:bg-orange-400 text-zinc-950 text-2xs py-2 font-semibold transition-colors uppercase tracking-wide cursor-pointer"
              >
                Load Recommended Layout
              </button>
            </div>

            <div className="pl-4 flex flex-col justify-between space-y-4">
              <div>
                <h5 className="text-xs font-bold text-zinc-200 uppercase tracking-wide">Custom Workspace</h5>
                <p className="text-3xs text-zinc-500 mt-1 leading-normal">
                  Build your own custom layout from scratch. Pick and position individual cards manually based on your daily workflow.
                </p>
                <ul className="text-3xs text-zinc-400 mt-2 list-disc list-inside space-y-1">
                  <li>Edit mode with free grid placement</li>
                  <li>Drag-and-drop cards to snap anywhere</li>
                  <li>Resize cards vertically and horizontally</li>
                  <li>Toggle compact view modes</li>
                </ul>
              </div>
              <button
                onClick={() => {
                  setIsConfigOpen(true);
                  setIsEditMode(true);
                }}
                className="w-full text-center rounded border border-zinc-800 bg-zinc-950 hover:bg-zinc-900 text-zinc-300 text-2xs py-2 font-semibold transition-colors uppercase tracking-wide cursor-pointer"
              >
                Choose Widgets Manually
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-3xs font-semibold text-zinc-550 uppercase tracking-wider">Key Widget Integrations</p>
            <div className="grid grid-cols-3 gap-3 text-3xs text-zinc-500">
              <div className="bg-zinc-950/45 p-2 rounded border border-zinc-850/40">
                <span className="font-semibold text-zinc-300 block mb-0.5">Database Monitor</span>
                Tracks local CVM database updates, status checks, and data health percentages.
              </div>
              <div className="bg-zinc-950/45 p-2 rounded border border-zinc-850/40">
                <span className="font-semibold text-zinc-300 block mb-0.5">Watchlist & KPIs</span>
                Monitors custom corporate watchlists and visualizes margin and stock trend sparklines.
              </div>
              <div className="bg-zinc-950/45 p-2 rounded border border-zinc-850/40">
                <span className="font-semibold text-zinc-300 block mb-0.5">Priority Queue</span>
                Highlights gaps and priorities inside selected company sectors and tiers.
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div
          ref={gridRef}
          className="relative w-full"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gridAutoRows: "120px",
            gap: "16px",
            minHeight: `${numGridRows * 120 + (numGridRows - 1) * 16}px`,
          }}
        >
          {/* 10.1 Background grid cells grid layout (Only in Edit Mode) */}
          {isEditMode && (
            <div
              className="absolute inset-0 grid grid-cols-3 gap-4 pointer-events-none"
              style={{ gridAutoRows: "120px" }}
            >
              {Array.from({ length: numGridRows }).map((_, y) =>
                [0, 1, 2].map((x) => (
                  <div
                    key={`${x}-${y}`}
                    className="border border-dashed border-zinc-800/10 rounded flex items-end justify-end p-1.5 text-3xs font-mono text-zinc-800/60"
                  >
                    {x},{y}
                  </div>
                ))
              )}
            </div>
          )}

          {/* 10.2 Snap indicator zone (Dashed border where card will land) */}
          {activeDragId && dragSnapPreview && (
            (() => {
              const item = activeCards.find((c) => c.id === activeDragId);
              if (!item) return null;
              return (
                <div
                  className="absolute border-2 border-dashed border-orange-500/40 bg-orange-500/5 rounded transition-all duration-75 z-sticky"
                  style={{
                    gridColumnStart: dragSnapPreview.x + 1,
                    gridColumnEnd: dragSnapPreview.x + 1 + item.w,
                    gridRowStart: dragSnapPreview.y + 1,
                    gridRowEnd: dragSnapPreview.y + 1 + (item.isMinimized ? 1 : item.h),
                  }}
                />
              );
            })()
          )}

          {/* 10.3 Workspace Widgets */}
          {activeCards.map((item) => {
            const cardDef = WORKSPACE_REGISTRY[item.id];
            if (!cardDef) return null;

            const CardComponent = cardDef.component;
            const config = cardConfigs[item.id];
            const isDragging = activeDragId === item.id;

            const headerControls = (
              <div className="flex items-center gap-1.5 font-mono text-3xs text-zinc-500">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleToggleProperty(item.id, "isCompact");
                  }}
                  className={`rounded border px-1 py-0.5 transition-colors ${
                    item.isCompact
                      ? "border-orange-500 bg-orange-500/10 text-orange-400"
                      : "border-zinc-850 bg-zinc-900 hover:text-zinc-350"
                  }`}
                  title="Toggle Compact Style"
                >
                  ☰
                </button>
                {!item.isMinimized && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setFocusedCardId(item.id);
                    }}
                    className="rounded border border-zinc-850 bg-zinc-900 px-1 py-0.5 hover:text-orange-400 transition-colors"
                    title="Maximize Focus Mode"
                  >
                    ↗
                  </button>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleToggleProperty(item.id, "isMinimized");
                  }}
                  className="rounded border border-zinc-850 bg-zinc-900 px-1 py-0.5 hover:text-zinc-355 transition-colors"
                  title={item.isMinimized ? "Restore widget" : "Minimize widget"}
                >
                  {item.isMinimized ? "⛶" : "_"}
                </button>
              </div>
            );

            // Absolute styling when actively dragging
            const dragStyle: React.CSSProperties = isDragging
              ? {
                  position: "absolute",
                  left: dragCurrentPos.x,
                  top: dragCurrentPos.y,
                  width: dragStartSize.w,
                  height: dragStartSize.h,
                  zIndex: 1000,
                  pointerEvents: "none",
                  opacity: 0.8,
                  boxShadow: "var(--shadow-overlay)",
                }
              : {
                  gridColumnStart: item.x + 1,
                  gridColumnEnd: item.x + 1 + item.w,
                  gridRowStart: item.y + 1,
                  gridRowEnd: item.y + 1 + (item.isMinimized ? 1 : item.h),
                };

            return (
              <div
                key={item.id}
                onMouseDown={(e) => handleDragHeaderMouseDown(e, item.id)}
                onDoubleClick={(e) => {
                  const target = e.target as HTMLElement;
                  if (target.closest("header") && !target.closest("button") && !target.closest("a") && !target.closest("input") && !target.closest("select")) {
                    setFocusedCardId(item.id);
                  }
                }}
                className={`relative group/card transition-all flex flex-col ${
                  isDragging ? "" : isEditMode ? "[&_header]:cursor-grab" : ""
                } ${isEditMode && !isDragging ? "border border-zinc-800/15 bg-zinc-950/20" : ""}`}
                style={dragStyle}
              >


                <CardComponent
                  config={config}
                  onConfigure={(newCfg) => handleUpdateConfig(item.id, newCfg)}
                  onRemove={() => handleToggleCard(item.id)}
                  isCompact={item.isCompact}
                  isMinimized={item.isMinimized}
                  headerControls={headerControls}
                />

                {/* 2D Resize handles (Visible only in Edit Mode) */}
                {isEditMode && !isDragging && (
                  <>
                    {/* Width Resize Handle (Right border) */}
                    <div
                      draggable={false}
                      onDragStart={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                      }}
                      onMouseDown={(e) => handleResizeWidthMouseDown(e, item.id, item.w)}
                      className="resize-handle absolute right-0 top-0 bottom-0 w-1.5 hover:w-2.5 bg-transparent hover:bg-orange-500/25 cursor-col-resize z-sticky transition-all rounded-r"
                      title="Drag right edge to resize width"
                    />

                    {/* Height Resize Handle (Bottom border, only if not minimized) */}
                    {!item.isMinimized && (
                      <div
                        draggable={false}
                        onDragStart={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                        }}
                        onMouseDown={(e) => handleResizeHeightMouseDown(e, item.id, item.h)}
                        className="resize-handle absolute bottom-0 left-0 right-0 h-1.5 hover:h-2.5 bg-transparent hover:bg-orange-500/25 cursor-row-resize z-sticky transition-all rounded-b"
                        title="Drag bottom edge to resize height"
                      />
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 10.4 Maximized Focus Mode Overlay Modal */}
      {focusedCardId && (
        (() => {
          const item = activeCards.find((c) => c.id === focusedCardId);
          if (!item) return null;
          const cardDef = WORKSPACE_REGISTRY[item.id];
          if (!cardDef) return null;
          const CardComponent = cardDef.component;
          const config = cardConfigs[item.id];

          const focusHeaderControls = (
            <div className="flex items-center gap-1.5 font-mono text-3xs text-zinc-550">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggleProperty(item.id, "isCompact");
                }}
                className={`rounded border px-1 py-0.5 transition-colors ${
                  item.isCompact
                    ? "border-orange-500 bg-orange-500/10 text-orange-400"
                    : "border-zinc-850 bg-zinc-900 hover:text-zinc-350"
                }`}
                title="Toggle Compact Style"
              >
                ☰
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setFocusedCardId(null);
                }}
                className="rounded border border-zinc-850 bg-zinc-900 px-1.5 py-0.5 text-orange-400 hover:text-orange-300 hover:border-zinc-700 transition-colors"
                title="Exit Focus Mode"
              >
                ↙
              </button>
            </div>
          );

          return (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm p-4 md:p-12 font-mono"
              onClick={() => setFocusedCardId(null)}
            >
              <div
                className="w-full max-w-5xl h-full max-h-[85vh] bg-zinc-950 border border-zinc-850 rounded-lg shadow-2xl flex flex-col p-2 overflow-hidden"
                onClick={(e) => e.stopPropagation()}
                onDoubleClick={(e) => {
                  const target = e.target as HTMLElement;
                  if (target.closest("header") && !target.closest("button") && !target.closest("a") && !target.closest("input") && !target.closest("select")) {
                    setFocusedCardId(null);
                  }
                }}
              >
                <CardComponent
                  config={config}
                  onConfigure={(newCfg) => handleUpdateConfig(item.id, newCfg)}
                  onRemove={() => {
                    handleToggleCard(item.id);
                    setFocusedCardId(null);
                  }}
                  isCompact={item.isCompact}
                  isMinimized={false}
                  isFocused={true}
                  headerControls={focusHeaderControls}
                />
              </div>
            </div>
          );
        })()
      )}

      {/* Slide-out Config drawer */}
      <WorkspaceConfigPanel
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        activeCardIds={activeCardIds}
        onToggleCard={handleToggleCard}
      />
    </section>
  );
}
