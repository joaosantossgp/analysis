import { useEffect, useRef } from "react";
import { NavLink, useLocation } from "react-router-dom";

/** Primary workspaces and a disclosure for supporting modules. */

type ModuleId = "companies" | "empresas" | "sectors" | "macro" | "system" | "coverage" | "news";

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
    id: "coverage",
    label: "Coverage",
    to: "/coverage",
    matches: (p) => p.startsWith("/coverage"),
  },
  {
    id: "news",
    label: "News",
    to: "/news",
    matches: (p) => p.startsWith("/news"),
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
  const disclosure = useRef<HTMLDetailsElement>(null);
  const summary = useRef<HTMLElement>(null);
  const secondary = MODULES.filter((m) => m.id === "coverage" || m.id === "news");
  const secondaryActive = secondary.find((m) => m.id === activeId);

  useEffect(() => {
    if (disclosure.current) disclosure.current.open = false;
  }, [pathname]);

  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (disclosure.current && !disclosure.current.contains(event.target as Node)) {
        disclosure.current.open = false;
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  const link = (m: ModuleDef, supporting = false) => (
    <NavLink
      key={m.id}
      to={m.to}
      end={m.to === "/"}
      onClick={supporting ? () => {
        if (disclosure.current) disclosure.current.open = false;
        summary.current?.focus();
      } : undefined}
      className="relative flex items-center px-2 lg:px-3 font-mono text-xs uppercase tracking-wider focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
      style={{
        color: m.id === activeId ? "var(--color-action-primary)" : "var(--color-text-secondary)",
        background: m.id === activeId ? "var(--color-surface-3)" : "transparent",
        borderBottom: m.id === activeId ? "2px solid var(--color-action-primary)" : "2px solid transparent",
      }}
    >{m.label}</NavLink>
  );

  return (
    <nav aria-label="Modules" className="flex h-full shrink-0 items-stretch">
      {MODULES.filter((m) => !["coverage", "news", "system"].includes(m.id)).map((m) => link(m))}
      <details
        ref={disclosure}
        className="relative"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            if (disclosure.current) disclosure.current.open = false;
            summary.current?.focus();
          }
        }}
        onBlur={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) event.currentTarget.open = false;
        }}
      >
        <summary
          ref={summary}
          className="flex h-full cursor-pointer list-none items-center gap-1 px-2 lg:px-3 font-mono text-xs uppercase tracking-wider focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-500"
          style={{ color: secondaryActive ? "var(--color-action-primary)" : "var(--color-text-secondary)" }}
        >
          More{secondaryActive ? ` · ${secondaryActive.label}` : ""}<span aria-hidden="true">▾</span>
        </summary>
        <div className="absolute right-0 top-full z-50 grid min-w-40 gap-1 rounded-b border border-default bg-surface-1 py-2 shadow-lg [&>a]:py-2">
          {secondary.map((m) => link(m, true))}
        </div>
      </details>
      {MODULES.filter((m) => m.id === "system").map((m) => link(m))}
    </nav>
  );
}
