import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import { useCommandPalette } from "./components/command/useCommandPalette";
import { StateBanner } from "./components/feedback/StateBanner";
import { TerminalShell } from "./components/shell/TerminalShell";
import { fetchOnboardingState } from "./lib/api/onboarding";
import { whenBridgeReady } from "./lib/bridge/adapter";

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
const CompanyUniversePage = lazy(() =>
  import("./routes/CompanyUniversePage").then((m) => ({ default: m.CompanyUniversePage })),
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
const CountryKpisPage = lazy(() =>
  import("./routes/CountryKpisPage").then((m) => ({ default: m.CountryKpisPage })),
);
const CoveragePage = lazy(() =>
  import("./routes/CoveragePage").then((m) => ({ default: m.CoveragePage })),
);
const CompanyCoveragePage = lazy(() =>
  import("./routes/CompanyCoveragePage").then((m) => ({ default: m.CompanyCoveragePage })),
);
const NewsPage = lazy(() =>
  import("./routes/NewsPage").then((m) => ({ default: m.NewsPage })),
);
const CommandBar = lazy(() =>
  import("./components/command/CommandBar").then((m) => ({ default: m.CommandBar })),
);
const FirstRunOnboarding = lazy(() =>
  import("./components/onboarding/FirstRunOnboarding").then((m) => ({ default: m.FirstRunOnboarding })),
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
      <AppShellWithPalette />
    </HashRouter>
  );
}

function AppShellWithPalette() {
  const palette = useCommandPalette();
  const [bridgeReady, setBridgeReady] = useState(false);
  const [onboardingDismissed, setOnboardingDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const onboardingQuery = useQuery({
    queryKey: ["onboarding-state"],
    queryFn: fetchOnboardingState,
    enabled: bridgeReady && !onboardingDismissed,
    staleTime: 5_000,
  });

  const onboardingState =
    onboardingQuery.data?.mode === "desktop" ? onboardingQuery.data.state : null;
  if (onboardingState?.should_show && !onboardingDismissed) {
    return (
      <Suspense
        fallback={
          <div style={{ padding: "24px 20px" }}>
            <StateBanner variant="loading" title="Loading setup…" />
          </div>
        }
      >
        <FirstRunOnboarding
          initialState={onboardingState}
          onDone={() => setOnboardingDismissed(true)}
        />
      </Suspense>
    );
  }

  const setupError = onboardingQuery.isError ? (
    <StateBanner
      variant="warning"
      title="Setup status unavailable"
      message={
        onboardingQuery.error instanceof Error
          ? onboardingQuery.error.message
          : String(onboardingQuery.error)
      }
      size="dense"
    />
  ) : null;

  return (
    <>
      <TerminalShell onOpenPalette={palette.open_}>
        {setupError}
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/empresas" element={<CompaniesPage />} />
            <Route path="/settings" element={<SettingsModule section="overview" />} />
            <Route path="/settings/health" element={<SettingsModule section="health" />} />
            <Route path="/settings/storage" element={<SettingsModule section="storage" />} />
            <Route path="/settings/sources" element={<SettingsModule section="sources" />} />
            <Route path="/settings/imports" element={<SettingsModule section="imports" />} />
            <Route path="/settings/updates" element={<SettingsModule section="updates" />} />
            <Route path="/settings/coverage" element={<SettingsModule section="coverage" />} />
            <Route path="/settings/app" element={<SettingsModule section="app" />} />
            <Route path="/settings/diagnostics" element={<SettingsModule section="diagnostics" />} />
            {/* Backwards compatibility redirects */}
            <Route path="/atualizar-base" element={<Navigate to="/settings/updates" replace />} />
            <Route path="/data-coverage" element={<Navigate to="/settings/coverage" replace />} />
            <Route path="/status" element={<Navigate to="/settings/diagnostics" replace />} />
            <Route path="/company-universe" element={<CompanyUniversePage />} />
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
            <Route path="/coverage" element={<CoveragePage section="universes" />} />
            <Route path="/coverage/prioritization" element={<CoveragePage section="prioritization" />} />
            <Route path="/coverage/work-queue" element={<CoveragePage section="work-queue" />} />
            <Route path="/coverage/capacity" element={<CoveragePage section="capacity" />} />
            <Route path="/news" element={<NewsPage />} />
            <Route path="/news/latest" element={<NewsPage />} />
            <Route path="/indicators" element={<CountryKpisPage />} />
            {/* Backwards-compat: old bookmarks/deep links to the macro module. */}
            <Route path="/country-kpis" element={<Navigate to="/indicators" replace />} />
            <Route path="/dev/data-ops" element={<DevDataOpsPage />} />
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
