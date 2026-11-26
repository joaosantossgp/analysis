// PROTOTYPE (throwaway, dev-only): data shell variants. Do not import from production code paths except the gated slots.
import { useSyncExternalStore } from "react";

export type DataShellState =
  | "empty"
  | "files"
  | "updating"
  | "current"
  | "stale"
  | "partial"
  | "failed"
  | "offline";

export type VariantKey = "A" | "B" | "C" | "D" | "E";

export const VARIANT_KEYS: VariantKey[] = ["E", "A", "B", "C", "D"];

export const VARIANT_NAMES: Record<VariantKey, string> = {
  A: "Status strip native",
  B: "Top bar pill + side drawer",
  C: "Inline-first",
  D: "A+ hybrid (top bar trigger, A rules)",
  E: "Chosen: C hero below workspace header + A+ header",
};

export const DATA_SHELL_STATES: { key: DataShellState; label: string }[] = [
  { key: "empty", label: "Empty" },
  { key: "files", label: "Downloading files" },
  { key: "updating", label: "Updating 37%" },
  { key: "current", label: "Up to date" },
  { key: "stale", label: "Stale" },
  { key: "partial", label: "Completed with failures" },
  { key: "failed", label: "Failed" },
  { key: "offline", label: "Offline (empty, no connection)" },
];

type Snapshot = {
  active: boolean;
  variant: VariantKey;
  state: DataShellState;
  panelOpen: boolean;
};

const ENABLED = import.meta.env.DEV && typeof window !== "undefined" && import.meta.env.MODE !== "test";
const STORAGE_KEY = "prototype:data-shell";
const INACTIVE: Snapshot = { active: false, variant: "A", state: "empty", panelOpen: false };

function isVariant(v: string | null): v is VariantKey {
  return v != null && (VARIANT_KEYS as string[]).includes(v);
}
function isState(s: string | null): s is DataShellState {
  return s != null && DATA_SHELL_STATES.some((x) => x.key === s);
}

function readUrl(): Snapshot | null {
  const hash = window.location.hash;
  const q = hash.indexOf("?");
  if (q < 0) return null;
  const params = new URLSearchParams(hash.slice(q + 1));
  if (params.get("prototype") !== "data-shell") return null;
  const variant = params.get("variant");
  const state = params.get("state");
  return {
    active: true,
    variant: isVariant(variant) ? variant : "E",
    state: isState(state) ? state : "empty",
    panelOpen: false,
  };
}

function readStorage(): Snapshot | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? ({ ...INACTIVE, ...JSON.parse(raw), panelOpen: false } as Snapshot) : null;
  } catch {
    return null;
  }
}

let snapshot: Snapshot = ENABLED ? readUrl() ?? readStorage() ?? INACTIVE : INACTIVE;
const listeners = new Set<() => void>();

function writeUrl(s: Snapshot) {
  const hash = window.location.hash || "#/";
  const q = hash.indexOf("?");
  const path = q < 0 ? hash : hash.slice(0, q);
  const params = new URLSearchParams(q < 0 ? "" : hash.slice(q + 1));
  params.delete("prototype");
  params.delete("variant");
  params.delete("state");
  if (s.active) {
    params.set("prototype", "data-shell");
    params.set("variant", s.variant);
    params.set("state", s.state);
  }
  const query = params.toString();
  const next = `${path}${query ? `?${query}` : ""}`;
  if (next !== hash) window.history.replaceState(window.history.state, "", next);
}

function set(next: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...next };
  if (snapshot.active) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  else sessionStorage.removeItem(STORAGE_KEY);
  writeUrl(snapshot);
  listeners.forEach((l) => l());
}

if (ENABLED) {
  window.addEventListener("hashchange", () => {
    const fromUrl = readUrl();
    if (fromUrl) {
      if (fromUrl.variant !== snapshot.variant || fromUrl.state !== snapshot.state || !snapshot.active) {
        set({ ...fromUrl, panelOpen: fromUrl.variant === snapshot.variant ? snapshot.panelOpen : false });
      }
    } else if (snapshot.active) {
      // Router navigation drops the query; keep the prototype URL shareable.
      writeUrl(snapshot);
    }
  });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useDataShellPrototype(): Snapshot {
  const s = useSyncExternalStore(subscribe, () => snapshot, () => INACTIVE);
  return ENABLED ? s : INACTIVE;
}

export function setVariant(variant: VariantKey) {
  set({ variant, panelOpen: false });
}
export function setState(state: DataShellState) {
  set({ state });
}
export function setPanelOpen(panelOpen: boolean) {
  set({ panelOpen });
}
export function cycleVariant(delta: number) {
  const i = VARIANT_KEYS.indexOf(snapshot.variant);
  setVariant(VARIANT_KEYS[(i + delta + VARIANT_KEYS.length) % VARIANT_KEYS.length]);
}
export function cycleState(delta: number) {
  const i = DATA_SHELL_STATES.findIndex((s) => s.key === snapshot.state);
  const n = DATA_SHELL_STATES.length;
  setState(DATA_SHELL_STATES[(i + delta + n) % n].key);
}
export function exitPrototype() {
  set({ ...INACTIVE });
}
