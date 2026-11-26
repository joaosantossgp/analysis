import { lazy, Suspense } from "react";
import { HashRouter, Navigate, Route, Routes, useNavigate, useLocation } from "react-router-dom";

import { useCommandPalette } from "./components/command/useCommandPalette";
import { StateBanner } from "./components/feedback/StateBanner";
import { TerminalShell } from "./components/shell/TerminalShell";
import { isExcelMappingWindow } from "./lib/windowMode";
import { SETTINGS_REDIRECTS } from "./lib/settingsNav";
import { useGlobalHotkeys } from "./lib/keyboard/useGlobalHotkeys";
import { DEV_DESIGN_SYSTEM_PATH, resolveDevDesignSystemShortcut } from "./lib/keyboard/devDesignSystemShortcut";

// Route pages are lazy-loaded so the initial bundle only ships the shell,
// command palette, and routing logic. Each route chunk is fetched on first
// navigation, which dramatically reduces first-load parse time.
const HomePage = lazy(() =>
  import("./routes/HomePage").then((m) => ({ default: m.HomePage })),
);
const CompaniesPage = lazy(() =>
  import("./routes/CompaniesPage").then((m) => ({ default: m.CompaniesPage })),
);
const CompanyDetailPage = lazy(() =>
  import("./routes/CompanyDetailPage").then((m) => ({ default: m.CompanyDetailPage })),
);
const CompanyKpisPage = lazy(() =>
  import("./routes/CompanyKpisPage").then((m) => ({ default: m.CompanyKpisPage })),
);
const CompanyModelMappingPage = lazy(() =>
  import("./routes/CompanyModelMappingPage").then((m) => ({ default: m.CompanyModelMappingPage })),
);
const CompanyStatementsPage = lazy(() =>
  import("./routes/CompanyStatementsPage").then((m) => ({ default: m.CompanyStatementsPage })),
);
const SectorDetailPage = lazy(() =>
  import("./routes/SectorDetailPage").then((m) => ({ default: m.SectorDetailPage })),
);
const SectorsPage = lazy(() =>
  import("./routes/SectorsPage").then((m) => ({ default: m.SectorsPage })),
);
const SubSectorDetailPage = lazy(() =>
  import("./routes/SubSectorDetailPage").then((m) => ({ default: m.SubSectorDetailPage })),
);
const SettingsModule = lazy(() =>
  import("./routes/SettingsModule").then((m) => ({ default: m.SettingsModule })),
);
const DevDataOpsPage = lazy(() =>
  import("./routes/DevDataOpsPage").then((m) => ({ default: m.DevDataOpsPage })),
);
const DevDesignSystemPage = import.meta.env.DEV
  ? lazy(() => import("./routes/DevDesignSystemPage").then((m) => ({ default: m.DevDesignSystemPage })))
  : null;
const CountryKpisPage = lazy(() =>
  import("./routes/CountryKpisPage").then((m) => ({ default: m.CountryKpisPage })),
);
const CoveragePage = lazy(() =>
  import("./routes/CoveragePage").then((m) => ({ default: m.CoveragePage })),
);
const CompanyCoveragePage = lazy(() =>
  import("./routes/CompanyCoveragePage").then((m) => ({ default: m.CompanyCoveragePage })),
);
const RetiredNewsPage = lazy(() => import("./routes/RetiredNewsPage").then(m => ({default: m.RetiredNewsPage})));
const CompaniesAssetsPage = lazy(() => import("./routes/CountryKpisPage").then(m => ({default: m.CompaniesAssetsPage})));
const CommandBar = lazy(() =>
  import("./components/command/CommandBar").then((m) => ({ default: m.CommandBar })),
);

function RouteFallback() {
  return (
    <div style={{ padding: "24px 20px" }}>
      <StateBanner variant="loading" />
    </div>
  );
}

// HashRouter (not BrowserRouter) for portability across pywebview origins:
// file:// (PyInstaller _MEIPASS), http://127.0.0.1:<port> (Vite dev), and
// pywebview's built-in http_server=True all play nicely with hash routing.
export function App() {
  return (
    <HashRouter>
      {isExcelMappingWindow(window.location.search) ? <ExcelMappingWindowApp /> : <AppShellWithPalette />}
    </HashRouter>
  );
}

function ExcelMappingWindowApp() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route
          path="/empresas/:cdCvm/model-mapping"
          element={<CompanyModelMappingPage windowMode />}
        />
        <Route path="*" element={<Navigate to="/empresas" replace />} />
      </Routes>
    </Suspense>
  );
}

function AppShellWithPalette() {
  const palette = useCommandPalette();

  return (
    <>
      {import.meta.env.DEV ? <DevDesignSystemShortcut /> : null}
      <TerminalShell onOpenPalette={palette.open_}>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/empresas" element={<CompaniesPage />} />
            <Route path="/empresas/assets" element={<CompaniesAssetsPage />} />
            <Route path="/settings" element={<SettingsModule section="overview" />} />
            <Route path="/settings/data" element={<SettingsModule section="data" />} />
            <Route path="/settings/storage" element={<SettingsModule section="storage" />} />
            <Route path="/settings/sources" element={<SettingsModule section="sources" />} />
            <Route path="/settings/imports" element={<SettingsModule section="imports" />} />
            <Route path="/settings/indicator-sources" element={<SettingsModule section="indicator-sources" />} />
            <Route path="/settings/app" element={<SettingsModule section="app" />} />
            <Route path="/settings/diagnostics" element={<SettingsModule section="diagnostics" />} />
            {/* Backwards compatibility redirects */}
            {Object.entries(SETTINGS_REDIRECTS).map(([from, to]) => (
              <Route key={from} path={from} element={<Navigate to={to} replace />} />
            ))}
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
            <Route
              path="/empresas/:cdCvm/model-mapping"
              element={<CompanyModelMappingPage />}
            />
            <Route
              path="/empresas/:cdCvm/coverage"
              element={<CompanyCoveragePage />}
            />
            <Route path="/empresas/coverage" element={<CoveragePage section="universes" />} />
            <Route path="/empresas/coverage/prioritization" element={<CoveragePage section="prioritization" />} />
            <Route path="/empresas/coverage/work-queue" element={<CoveragePage section="work-queue" />} />
            <Route path="/empresas/coverage/capacity" element={<CoveragePage section="capacity" />} />
            <Route path="/coverage/*" element={<CoverageRedirect />} />
            <Route path="/news/*" element={<RetiredNewsPage />} />
            <Route path="/indicators" element={<CountryKpisPage />} />
            {/* Backwards-compat: old bookmarks/deep links to the macro module. */}
            <Route path="/country-kpis" element={<Navigate to="/indicators" replace />} />
            <Route path="/dev/data-ops" element={<DevDataOpsPage />} />
            {DevDesignSystemPage ? <Route path={DEV_DESIGN_SYSTEM_PATH} element={<DevDesignSystemPage />} /> : null}
          </Routes>
        </Suspense>
      </TerminalShell>
      {palette.primed ? (
        <Suspense fallback={null}>
          <CommandBar
            open={palette.open}
            primed={palette.primed}
            onClose={palette.close_}
          />
        </Suspense>
      ) : null}
    </>
  );
}

function DevDesignSystemShortcut() {
  const navigate = useNavigate();

  useGlobalHotkeys("ctrl+alt+d", (event) => {
    const destination = resolveDevDesignSystemShortcut(event);
    if (!destination) return;
    event.preventDefault();
    navigate(destination);
  });

  return null;
}

function CoverageRedirect() {
  const location = useLocation();
  return <Navigate replace to={{ pathname: `/empresas${location.pathname}`, search: location.search, hash: location.hash }} />;
}
