// PROTOTYPE (throwaway, dev-only): data shell variants. Do not import from production code paths except the gated slots.
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { useDataShellPrototype } from "./store";
import { VARIANTS } from "./variants";

function useActiveVariant() {
  const s = useDataShellPrototype();
  return { s, v: s.active ? VARIANTS[s.variant] : null };
}

export function DataShellTopBarSlot() {
  const { s, v } = useActiveVariant();
  return v?.TopBarSlot ? <v.TopBarSlot state={s.state} panelOpen={s.panelOpen} /> : null;
}

export function DataShellStatusSlot() {
  const { s, v } = useActiveVariant();
  return v?.StatusSlot ? <v.StatusSlot state={s.state} panelOpen={s.panelOpen} /> : null;
}

export function useDataShellHidesStatusBrand(): boolean {
  return Boolean(useActiveVariant().v?.hidesStatusBrandLabel);
}

export function DataShellAside() {
  const { s, v } = useActiveVariant();
  return v?.Aside ? <v.Aside state={s.state} panelOpen={s.panelOpen} /> : null;
}

/** Push width for the shell grid (B only, >= 1024px, panel open). */
export function useDataShellAsideWidth(): number | null {
  const { s, v } = useActiveVariant();
  const [wide, setWide] = useState(() => window.innerWidth >= 1024);
  useEffect(() => {
    const onResize = () => setWide(window.innerWidth >= 1024);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return v?.asideWidthPx && s.panelOpen && wide ? v.asideWidthPx : null;
}

/** Home: lead block plus whether the normal chips / chooser are replaced. */
export function useDataShellHome(): { active: boolean; hideChooser: boolean; lead: ReactNode; leadBelowHeader: ReactNode } {
  const { s, v } = useActiveVariant();
  if (!v) return { active: false, hideChooser: false, lead: null, leadBelowHeader: null };
  const hideChooser = ["empty", "files", "failed", "offline"].includes(s.state);
  const lead = <v.HomeLead state={s.state} panelOpen={s.panelOpen} />;
  return v.homeLeadBelowHeader
    ? { active: true, hideChooser, lead: null, leadBelowHeader: lead }
    : { active: true, hideChooser, lead, leadBelowHeader: null };
}

/** Companies: replacement empty state, status line and row badge override. */
export function useDataShellCompanies(): {
  empty: ReactNode | null;
  statusLine: ReactNode | null;
  rowBadge: (cdCvm: number) => ReactNode | null;
} {
  const { s, v } = useActiveVariant();
  if (!v) return { empty: null, statusLine: null, rowBadge: () => null };
  const empty = s.state === "empty" || s.state === "offline" ? <v.CompaniesEmpty state={s.state} panelOpen={s.panelOpen} /> : null;
  const statusLine =
    v.CompaniesStatusLine && ["files", "updating", "partial"].includes(s.state) ? (
      <v.CompaniesStatusLine state={s.state} panelOpen={s.panelOpen} />
    ) : null;
  return { empty, statusLine, rowBadge: (cdCvm) => v.rowBadge?.(cdCvm, s.state) ?? null };
}
