import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HashRouter, Route, Routes } from "react-router-dom";

import { CommandBar } from "./components/command/CommandBar";
import { useCommandPalette } from "./components/command/useCommandPalette";
import { StateBanner } from "./components/feedback/StateBanner";
import { FirstRunOnboarding } from "./components/onboarding/FirstRunOnboarding";
import { TerminalShell } from "./components/shell/TerminalShell";
import { fetchOnboardingState } from "./lib/api/onboarding";
import { whenBridgeReady } from "./lib/bridge/adapter";

// Route pages are lazy-loaded so the initial bundle only ships the shell,
// command palette, and routing logic. Each route chunk is fetched on first
// navigation, which dramatically reduces first-load parse time.
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
const CompanyStatementsPage = lazy(() =>
  import("./routes/CompanyStatementsPage").then((m) => ({ default: m.CompanyStatementsPage })),
);
const HealthPage = lazy(() =>
  import("./routes/HealthPage").then((m) => ({ default: m.HealthPage })),
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
const StatusPage = lazy(() =>
  import("./routes/StatusPage").then((m) => ({ default: m.StatusPage })),
);
const UpdateBasePage = lazy(() =>
  import("./routes/UpdateBasePage").then((m) => ({ default: m.UpdateBasePage })),
);
const DataCoveragePage = lazy(() =>
  import("./routes/DataCoveragePage").then((m) => ({ default: m.DataCoveragePage })),
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

  if (!bridgeReady || onboardingQuery.isLoading) {
    return (
      <div style={{ padding: "24px 20px" }}>
        <StateBanner variant="loading" title="Preparing workspace…" />
      </div>
    );
  }

  if (onboardingQuery.isError) {
    return (
      <div style={{ padding: "24px 20px" }}>
        <StateBanner
          variant="error"
          title="Could not load setup"
          message={
            onboardingQuery.error instanceof Error
              ? onboardingQuery.error.message
              : String(onboardingQuery.error)
          }
          onRetry={() => { void onboardingQuery.refetch(); }}
        />
      </div>
    );
  }

  const onboardingState =
    onboardingQuery.data?.mode === "desktop" ? onboardingQuery.data.state : null;
  if (onboardingState?.should_show && !onboardingDismissed) {
    return (
      <FirstRunOnboarding
        initialState={onboardingState}
        onDone={() => setOnboardingDismissed(true)}
      />
    );
  }

  return (
    <>
      <TerminalShell onOpenPalette={palette.open_}>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<CompaniesPage />} />
            <Route path="/status" element={<StatusPage />} />
            <Route path="/health" element={<HealthPage />} />
            <Route path="/atualizar-base" element={<UpdateBasePage />} />
            <Route path="/data-coverage" element={<DataCoveragePage />} />
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
          </Routes>
        </Suspense>
      </TerminalShell>
      <CommandBar
        open={palette.open}
        primed={palette.primed}
        onClose={palette.close_}
      />
    </>
  );
}
