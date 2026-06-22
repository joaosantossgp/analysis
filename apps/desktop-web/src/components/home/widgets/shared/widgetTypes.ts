import type React from "react";

export type WatchlistConfig = {
  companyIds: Array<{ cdCvm: number; name: string; ticker: string }>;
  metric: "mg_ebit" | "stock_price" | "roe" | "mg_liq";
};

export type PriorityQueueConfig = {
  universeId: string;
};

export type MarketPriceConfig = {
  cdCvm: number;
  ticker: string;
  companyName: string;
  period?: string;
};

export interface WidgetCommonProps {
  onRemove: () => void;
  isCompact?: boolean;
  isMinimized?: boolean;
  isFocused?: boolean;
  headerControls?: React.ReactNode;
}
