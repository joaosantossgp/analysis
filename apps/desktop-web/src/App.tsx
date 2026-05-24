import { HashRouter, Route, Routes } from "react-router-dom";

import { CommandBar } from "./components/command/CommandBar";
import { useCommandPalette } from "./components/command/useCommandPalette";
import { TerminalShell } from "./components/shell/TerminalShell";
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
export function App() {
  return (
    <HashRouter>
      <AppShellWithPalette />
    </HashRouter>
  );
}

function AppShellWithPalette() {
  const palette = useCommandPalette();
  return (
    <>
      <TerminalShell onOpenPalette={palette.open_}>
        <Routes>
          <Route path="/" element={<CompaniesPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="/atualizar-base" element={<UpdateBasePage />} />
          <Route path="/setores" element={<SectorsPage />} />
          <Route path="/setores/:slug" element={<SectorDetailPage />} />
          <Route
            path="/setores/:sectorSlug/:subSectorSlug"
            element={<SubSectorDetailPage />}
          />
          <Route path="/empresas/:cdCvm" element={<CompanyDetailPage />} />
          <Route
            path="/empresas/:cdCvm/demonstrativos"
            element={<CompanyStatementsPage />}
          />
          <Route
            path="/empresas/:cdCvm/indicadores"
            element={<CompanyKpisPage />}
          />
        </Routes>
      </TerminalShell>
      <CommandBar
        open={palette.open}
        primed={palette.primed}
        onClose={palette.close_}
      />
    </>
  );
}
