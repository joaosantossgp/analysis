import { useState } from "react";

import { CompaniesTable } from "./components/CompaniesTable";
import { HealthCard } from "./components/HealthCard";

type View = "health" | "companies";

const VIEW_LABELS: Record<View, string> = {
  health: "Runtime health",
  companies: "Companies",
};

export function App() {
  const [view, setView] = useState<View>("companies");
  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col gap-6 px-6 py-8">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-widest text-zinc-500">
          Phase 1.5 prototype
        </p>
        <h1 className="text-3xl font-semibold text-zinc-50">
          CVM Analytics — desktop SPA shell
        </h1>
        <p className="max-w-xl text-sm text-zinc-400">
          Parallel Vite + React build that exercises the existing Python
          bridge. Replaces nothing in production yet; the released exe still
          ships the Next.js standalone runtime.
        </p>
      </header>

      <Nav view={view} onChange={setView} />

      <main className="space-y-6">
        {view === "health" ? <HealthCard /> : null}
        {view === "companies" ? <CompaniesTable /> : null}
      </main>

      <footer className="mt-auto pt-6 text-xs text-zinc-600">
        apps/desktop-web · proof-of-concept · not packaged yet
      </footer>
    </div>
  );
}

function Nav({
  view,
  onChange,
}: {
  view: View;
  onChange: (next: View) => void;
}) {
  return (
    <nav className="flex gap-2 border-b border-zinc-800 pb-2">
      {(Object.keys(VIEW_LABELS) as View[]).map((key) => {
        const active = key === view;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={
              active
                ? "rounded-t border border-b-0 border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-100"
                : "rounded-t border border-transparent px-4 py-2 text-sm text-zinc-500 hover:text-zinc-200"
            }
            aria-current={active ? "page" : undefined}
          >
            {VIEW_LABELS[key]}
          </button>
        );
      })}
    </nav>
  );
}
