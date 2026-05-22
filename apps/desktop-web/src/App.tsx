import { HashRouter, NavLink, Route, Routes } from "react-router-dom";

import { BridgeStatus } from "./components/BridgeStatus";
import { CompaniesPage } from "./routes/CompaniesPage";
import { CompanyDetailPage } from "./routes/CompanyDetailPage";
import { CompanyKpisPage } from "./routes/CompanyKpisPage";
import { CompanyStatementsPage } from "./routes/CompanyStatementsPage";
import { HealthPage } from "./routes/HealthPage";
import { SectorDetailPage } from "./routes/SectorDetailPage";
import { SectorsPage } from "./routes/SectorsPage";
import { SubSectorDetailPage } from "./routes/SubSectorDetailPage";
import { StatusPage } from "./routes/StatusPage";
import { UpdateBasePage } from "./routes/UpdateBasePage";

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
            Vite desktop runtime
          </p>
          <h1 className="text-3xl font-semibold text-zinc-50">
            CVM Analytics
          </h1>
          <p className="max-w-xl text-sm text-zinc-400">
            Local CVM company analysis with directory search, KPIs, and
            financial statements.
          </p>
        </header>

        <Nav />

        <main className="space-y-6">
          <Routes>
            <Route path="/" element={<CompaniesPage />} />
            <Route path="/status" element={<StatusPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/atualizar-base" element={<UpdateBasePage />} />
            <Route path="/setores" element={<SectorsPage />} />
            <Route path="/setores/:slug" element={<SectorDetailPage />} />
            <Route path="/setores/:sectorSlug/:subSectorSlug" element={<SubSectorDetailPage />} />
            <Route
              path="/empresas/:cdCvm"
              element={<CompanyDetailPage />}
            />
            <Route
              path="/empresas/:cdCvm/demonstrativos"
              element={<CompanyStatementsPage />}
            />
            <Route
              path="/empresas/:cdCvm/indicadores"
              element={<CompanyKpisPage />}
            />
          </Routes>
        </main>

        <footer className="mt-auto space-y-2 pt-6 text-xs text-zinc-600">
          <BridgeStatus />
          <p>apps/desktop-web · packaged Vite runtime</p>
        </footer>
      </div>
    </HashRouter>
  );
}

function Nav() {
  return (
    <nav className="flex flex-wrap gap-2 border-b border-zinc-800 pb-2">
      <NavTab to="/" label="Companies" end />
      <NavTab to="/setores" label="Sectors" />
      <NavTab to="/status" label="Status" />
      <NavTab to="/health" label="Runtime health" />
      <NavTab to="/atualizar-base" label="Update base" />
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
