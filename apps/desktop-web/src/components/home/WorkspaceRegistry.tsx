import type React from "react";
import { DatabaseStatusCard } from "./widgets/DatabaseStatusCard";
import { WatchlistCard } from "./widgets/WatchlistCard";
import { PriorityQueueCard } from "./widgets/PriorityQueueCard";
import { RetiredNewsCard } from "./widgets/RetiredNewsCard";
import { MarketPriceCard } from "./widgets/MarketPriceCard";

export type CardDef = {
  id: string;
  title: string;
  description: string;
  defaultSize: "large" | "medium" | "small";
  component: React.ComponentType<{
    config: any;
    onConfigure: (newCfg: any) => void;
    onRemove: () => void;
    isCompact?: boolean;
    isMinimized?: boolean;
    isFocused?: boolean;
    headerControls?: React.ReactNode;
  }>;
};

export const WORKSPACE_REGISTRY: Record<string, CardDef> = {
  "database-status": {
    id: "database-status",
    title: "Database Monitor",
    description: "CVM updates, diagnostics, base integrity status.",
    defaultSize: "large",
    component: DatabaseStatusCard as any,
  },
  watchlist: {
    id: "watchlist",
    title: "Watchlist & KPIs",
    description: "Trend lines of margins or prices for favorited companies.",
    defaultSize: "medium",
    component: WatchlistCard as any,
  },
  "priority-queue": {
    id: "priority-queue",
    title: "Priority Queue",
    description: "Coverage checklist updates and prioritization queue.",
    defaultSize: "medium",
    component: PriorityQueueCard as any,
  },
  "top-news": {
    id: "top-news",
    title: "News (retired)",
    description: "Saved News configuration is preserved; this widget no longer loads news.",
    defaultSize: "medium",
    component: RetiredNewsCard as any,
  },
  "market-price": {
    id: "market-price",
    title: "Market Price Sparkline",
    description: "Standalone performance sparkline of a target ticker.",
    defaultSize: "small",
    component: MarketPriceCard as any,
  },
};
