import { NavLink, useLocation, useParams } from "react-router-dom";

/**
 * Contextual sub-navigation under the top bar. Renders a horizontal tab
 * strip when the current route belongs to a module that has intra-module
 * navigation; otherwise renders an empty placeholder so the shell grid
 * geometry stays stable.
 *
 * One place owns the route→tabs config: extend `subNavFor` below to add
 * tabs for a new module.
 */

type Tab = { to: string; label: string; end?: boolean };

function subNavFor(pathname: string, params: Record<string, string | undefined>): Tab[] {
  // Company detail subtabs (Overview / Indicadores / Demonstrativos).
  const cdMatch = pathname.match(/^\/empresas\/([^/]+)/);
  if (cdMatch) {
    const cdCvm = params.cdCvm ?? cdMatch[1];
    return [
      { to: `/empresas/${cdCvm}`, label: "Overview", end: true },
      { to: `/empresas/${cdCvm}/demonstrativos`, label: "Financial Statements" },
      { to: `/empresas/${cdCvm}/indicadores`, label: "Indicators" },
      { to: `/empresas/${cdCvm}/model-mapping`, label: "Model Mapping" },
    ];
  }

  if (
    pathname.startsWith("/settings") ||
    pathname.startsWith("/status") ||
    pathname.startsWith("/data-coverage") ||
    pathname.startsWith("/atualizar-base")
  ) {
    return [
      { to: "/settings", label: "Settings", end: true },
      { to: "/settings/imports", label: "User Imports" },
      { to: "/settings/updates", label: "Database Updates" },
      { to: "/settings/coverage", label: "Data Coverage" },
      { to: "/settings/diagnostics", label: "Diagnostics" },
    ];
  }

  // Setores hub keeps breadcrumb-based navigation inside the page itself;
  // no top-level sub-nav for now.
  return [];
}

export function SubNav() {
  const { pathname } = useLocation();
  const params = useParams();
  const tabs = subNavFor(pathname, params);

  if (tabs.length === 0) {
    return (
      <div
        aria-hidden="true"
        className="h-full"
        style={{
          background: "var(--color-surface-1)",
          borderBottom: "1px solid var(--color-border-subtle)",
        }}
      />
    );
  }

  return (
    <nav
      aria-label="Sub-navegação do módulo"
      className="flex h-full items-stretch px-4"
      style={{
        background: "var(--color-surface-1)",
        borderBottom: "1px solid var(--color-border-subtle)",
      }}
    >
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.end}
          className="flex items-center px-3 text-xs font-medium"
          style={({ isActive }) => ({
            color: isActive
              ? "var(--color-text-primary)"
              : "var(--color-text-tertiary)",
            borderBottom: isActive
              ? "2px solid var(--color-action-primary)"
              : "2px solid transparent",
          })}
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
