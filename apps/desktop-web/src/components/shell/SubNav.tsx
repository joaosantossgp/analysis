import { useEffect, useState } from "react";
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

type Tab = { to: string; label: string; end?: boolean; activeOn?: string[] };

export function subNavFor(pathname: string, params: Record<string, string | undefined>, activeUniverseId: string | null): Tab[] {
  if (pathname === "/empresas" || pathname.startsWith("/empresas/coverage") || pathname.startsWith("/empresas/assets")) {
    const tabs: Tab[] = [
      { to: "/empresas", label: "Directory", end: true },
      { to: "/empresas/coverage", label: "Coverage", end: true },
      { to: "/empresas/assets", label: "Assets & Mapping" },
    ];
    if (pathname.startsWith("/empresas/coverage") && activeUniverseId) tabs.push(
      { to: "/empresas/coverage/prioritization", label: "Prioritization" },
      { to: "/empresas/coverage/work-queue", label: "Work Queue" },
      { to: "/empresas/coverage/capacity", label: "Capacity" },
    );
    return tabs;
  }
  const cdMatch = pathname.match(/^\/empresas\/(\d+)(?:\/|$)/);
  if (cdMatch) {
    const cdCvm = params.cdCvm ?? cdMatch[1];
    return [
      { to: "/empresas", label: "Directory", end: true },
      { to: `/empresas/${cdCvm}`, label: "Overview", end: true },
      { to: `/empresas/${cdCvm}/demonstrativos`, label: "Financial Statements" },
      { to: `/empresas/${cdCvm}/coverage`, label: "Coverage Status" },
    ];
  }

  if (
    pathname.startsWith("/settings") ||
    pathname.startsWith("/status") ||
    pathname.startsWith("/data-coverage") ||
    pathname.startsWith("/atualizar-base")
  ) {
    return [
      { to: "/settings", label: "Overview", end: true },
      { to: "/settings/health", label: "Data", activeOn: ["/settings/coverage", "/settings/updates"] },
      { to: "/settings/sources", label: "Sources", activeOn: ["/settings/imports"] },
      { to: "/settings/indicator-sources", label: "Indicator Sources" },
      { to: "/settings/storage", label: "Storage" },
      { to: "/settings/app", label: "App" },
      { to: "/settings/diagnostics", label: "Advanced" },
    ];
  }

  // Setores hub keeps breadcrumb-based navigation inside the page itself;
  // no top-level sub-nav for now.
  return [];
}

export function SubNav() {
  const { pathname } = useLocation();
  const params = useParams();
  const [activeUniverseId, setActiveUniverseId] = useState<string | null>(() => {
    return localStorage.getItem("active_coverage_universe_id");
  });

  useEffect(() => {
    setActiveUniverseId(localStorage.getItem("active_coverage_universe_id"));
  }, [pathname]);

  useEffect(() => {
    const handleStorage = () => {
      setActiveUniverseId(localStorage.getItem("active_coverage_universe_id"));
    };
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  const tabs = subNavFor(pathname, params, activeUniverseId);

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
      aria-label="Module navigation"
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
          style={({ isActive }) => {
            const active =
              isActive || t.activeOn?.some((prefix) => pathname.startsWith(prefix));

            return {
              color: active
                ? "var(--color-text-primary)"
                : "var(--color-text-tertiary)",
              borderBottom: active
                ? "2px solid var(--color-action-primary)"
                : "2px solid transparent",
            };
          }}
        >
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}
