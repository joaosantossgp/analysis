import { getBridgeMode } from "./adapter";

export type RuntimeBridgeMode = "desktop" | "mock" | "browser" | "offline";

export function resolveBridgeMode(): RuntimeBridgeMode {
  const mode = getBridgeMode();
  if (mode === "mock") return "mock";
  if (mode === "browser") return "browser";
  return "desktop";
}

export type WidgetDataState = "ready" | "empty" | "no_import" | "stale" | "error" | "loading";

export interface DataStateResolverParams {
  isLoading: boolean;
  error: any;
  hasData: boolean;
  isOffline?: boolean;
  isStale?: boolean;
}

export function resolveWidgetDataState(params: DataStateResolverParams): WidgetDataState {
  if (params.isLoading) return "loading";
  if (params.error) return "error";
  if (!params.hasData) {
    if (params.isOffline) return "no_import";
    return "empty";
  }
  if (params.isStale) return "stale";
  return "ready";
}

export function getBridgeBadgeStyles(mode: RuntimeBridgeMode): { className: string; text: string } {
  switch (mode) {
    case "mock":
      return {
        className: "bg-purple-500/10 text-purple-400 border-purple-500/20",
        text: "MOCK · FIXTURE",
      };
    case "browser":
      return {
        className: "bg-amber-500/10 text-amber-400 border-amber-500/20",
        text: "BROWSER · FALLBACK",
      };
    case "desktop":
      return {
        className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
        text: "LIVE · DESKTOP",
      };
    case "offline":
    default:
      return {
        className: "bg-red-500/10 text-red-400 border-red-500/20",
        text: "OFFLINE",
      };
  }
}

export function getDataStateBadgeStyles(state: WidgetDataState): { className: string; text: string } | null {
  switch (state) {
    case "loading":
      return {
        className: "bg-zinc-800 text-zinc-400 border-zinc-700 animate-pulse",
        text: "LOADING",
      };
    case "error":
      return {
        className: "bg-red-500/10 text-red-400 border-red-500/20",
        text: "ERROR",
      };
    case "empty":
      return {
        className: "bg-zinc-950 text-zinc-500 border-zinc-900",
        text: "EMPTY",
      };
    case "no_import":
      return {
        className: "bg-amber-500/10 text-amber-400 border-amber-500/20",
        text: "NO IMPORT",
      };
    case "stale":
      return {
        className: "bg-amber-500/10 text-amber-400 border-amber-500/20",
        text: "STALE",
      };
    case "ready":
      return {
        className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
        text: "READY",
      };
    default:
      return null;
  }
}
