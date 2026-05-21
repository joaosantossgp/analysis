import { HashRouter, NavLink, Route, Routes } from "react-router-dom";

import { CompaniesPage } from "./routes/CompaniesPage";
import { CompanyDetailPage } from "./routes/CompanyDetailPage";
import { HealthPage } from "./routes/HealthPage";

// HashRouter (not BrowserRouter) for portability across pywebview origins:
// file:// (PyInstaller _MEIPASS), http://127.0.0.1:<port> (Vite dev), and
// pywebview's built-in http_server=True all play nicely with hash routing.
// Phase 2 can switch to BrowserRouter once we standardise on http_server.
export function App() {
  return (
    <HashRouter>
      <div className="mx-auto flex min-h-full max-w-5xl flex-col gap-6 px-6 py-8">
        <header className="space-y-2">
          <p className="text-xs uppercase tracking-widest text-zinc-500">
            Phase 1.6 prototype
          </p>
          <h1 className="text-3xl font-semibold text-zinc-50">
            CVM Analytics — desktop SPA shell
          </h1>
          <p className="max-w-xl text-sm text-zinc-400">
            Parallel Vite + React build exercising the existing Python bridge.
            Replaces nothing in production yet; the released exe still ships
            the Next.js standalone runtime.
          </p>
        </header>

        <Nav />

        <main className="space-y-6">
          <Routes>
            <Route path="/" element={<CompaniesPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route
              path="/empresas/:cdCvm"
              element={<CompanyDetailPage />}
            />
          </Routes>
        </main>

        <footer className="mt-auto pt-6 text-xs text-zinc-600">
          apps/desktop-web · proof-of-concept · not packaged yet
        </footer>
      </div>
    </HashRouter>
  );
}

function Nav() {
  return (
    <nav className="flex gap-2 border-b border-zinc-800 pb-2">
      <NavTab to="/" label="Companies" end />
      <NavTab to="/health" label="Runtime health" />
    </nav>
  );
}

function NavTab({
  to,
  label,
  end = false,
}: {
  to: string;
  label: string;
  end?: boolean;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        isActive
          ? "rounded-t border border-b-0 border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-100"
          : "rounded-t border border-transparent px-4 py-2 text-sm text-zinc-500 hover:text-zinc-200"
      }
    >
      {label}
    </NavLink>
  );
}
