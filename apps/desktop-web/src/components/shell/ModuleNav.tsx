import { NavLink, useLocation } from "react-router-dom";

/**
 * Top-level module navigation. 4 pills representing the workspace areas of
 * the CVMAnalytics Terminal. The active module is computed from the current
 * route prefix so deep links (`/empresas/9512/indicadores`) still highlight
 * the parent "Empresas" pill.
 */

type ModuleId = "companies" | "sectors" | "database" | "diagnostics";

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
    label: "Empresas",
    to: "/",
    matches: (p) => p === "/" || p.startsWith("/empresas"),
  },
  {
    id: "sectors",
    label: "Setores",
    to: "/setores",
    matches: (p) => p.startsWith("/setores"),
  },
  {
    id: "database",
    label: "Database",
    to: "/atualizar-base",
    matches: (p) => p.startsWith("/atualizar-base") || p.startsWith("/company-universe"),
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    to: "/status",
    matches: (p) => p.startsWith("/status") || p.startsWith("/health"),
  },
];

export function ModuleNav() {
  const { pathname } = useLocation();
  const activeId = MODULES.find((m) => m.matches(pathname))?.id ?? null;

  return (
    <nav
      aria-label="Módulos"
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
