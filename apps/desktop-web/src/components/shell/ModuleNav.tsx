import { NavLink, useLocation } from "react-router-dom";

/** Primary workspaces and system settings. */

type ModuleId = "companies" | "empresas" | "sectors" | "macro" | "system";

type ModuleDef = {
  id: ModuleId;
  label: string;
  /** Route the pill clicks navigate to. */
  to: string;
  /** Route-prefix predicate for active state matching. */
  matches: (pathname: string) => boolean;
};

const MODULES: ModuleDef[] = [
  {
    id: "companies",
    label: "Home",
    to: "/",
    matches: (p) => p === "/",
  },
  {
    id: "empresas",
    label: "Companies",
    to: "/empresas",
    matches: (p) => p.startsWith("/empresas"),
  },
  {
    id: "sectors",
    label: "Sectors",
    to: "/setores",
    matches: (p) => p.startsWith("/setores"),
  },
  {
    id: "macro",
    label: "Indicators",
    to: "/indicators",
    matches: (p) => p.startsWith("/indicators") || p.startsWith("/country-kpis"),
  },
  {
    id: "system",
    label: "Settings",
    to: "/settings",
    matches: (p) =>
      p.startsWith("/settings") ||
      p.startsWith("/status") ||
      p.startsWith("/data-coverage") ||
      p.startsWith("/atualizar-base"),
  },
];

export function ModuleNav() {
  const { pathname } = useLocation();
  const activeId = MODULES.find((m) => m.matches(pathname))?.id ?? null;
  return (
    <nav aria-label="Modules" className="flex h-full shrink-0 items-stretch">
      {MODULES.map((m) => (
        <NavLink key={m.id} to={m.to} end={m.to === "/"}
          className="relative flex items-center px-2 lg:px-3 font-mono text-xs uppercase tracking-wider focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
          style={{
            color: m.id === activeId ? "var(--color-action-primary)" : "var(--color-text-secondary)",
            background: m.id === activeId ? "var(--color-surface-3)" : "transparent",
            borderBottom: m.id === activeId ? "2px solid var(--color-action-primary)" : "2px solid transparent",
          }}
        >{m.label}</NavLink>
      ))}
    </nav>
  );
}
