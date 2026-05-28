import { NavLink, useLocation } from "react-router-dom";

/**
 * Top-level module navigation. 4 pills representing the workspace areas of
 * the CVMAnalytics Terminal. The active module is computed from the current
 * route prefix so deep links (`/empresas/9512/indicadores`) still highlight
 * the parent "Empresas" pill.
 */

type ModuleId = "companies" | "empresas" | "sectors" | "database" | "diagnostics";

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
    id: "database",
    label: "Updates",
    to: "/atualizar-base",
    matches: (p) =>
      p.startsWith("/atualizar-base") || p.startsWith("/data-coverage"),
  },
  {
    id: "diagnostics",
    label: "System",
    to: "/status",
    matches: (p) => p.startsWith("/status"),
  },
];

export function ModuleNav() {
  const { pathname } = useLocation();
  const activeId = MODULES.find((m) => m.matches(pathname))?.id ?? null;

  return (
    <nav
      aria-label="Modules"
      className="flex h-full items-stretch"
      role="navigation"
    >
      {MODULES.map((m) => {
        const isActive = m.id === activeId;
        return (
          <NavLink
            key={m.id}
            to={m.to}
            className="relative flex items-center px-4 font-mono text-xs uppercase tracking-wider"
            style={{
              color: isActive
                ? "var(--color-action-primary)"
                : "var(--color-text-secondary)",
              background: isActive ? "var(--color-surface-3)" : "transparent",
              borderBottom: isActive
                ? "2px solid var(--color-action-primary)"
                : "2px solid transparent",
            }}
          >
            {m.label}
          </NavLink>
        );
      })}
    </nav>
  );
}
