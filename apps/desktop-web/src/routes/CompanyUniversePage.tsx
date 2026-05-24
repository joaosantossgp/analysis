import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { StateBanner } from "@/components/feedback/StateBanner";
import { FirstRunOnboarding } from "@/components/onboarding/FirstRunOnboarding";
import { fetchOnboardingState } from "@/lib/api/onboarding";
import { whenBridgeReady } from "@/lib/bridge/adapter";

export function CompanyUniversePage() {
  const navigate = useNavigate();
  const [bridgeReady, setBridgeReady] = useState(false);

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
    queryKey: ["onboarding-state", "manual"],
    queryFn: fetchOnboardingState,
    enabled: bridgeReady,
    staleTime: 5_000,
  });

  if (!bridgeReady || onboardingQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading company universe setup..." />;
  }

  if (onboardingQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load company universe setup"
        message={
          onboardingQuery.error instanceof Error
            ? onboardingQuery.error.message
            : String(onboardingQuery.error)
        }
        onRetry={() => {
          void onboardingQuery.refetch();
        }}
      />
    );
  }

  const result = onboardingQuery.data;
  if (!result) {
    return <StateBanner variant="loading" title="Loading company universe setup..." />;
  }

  if (result.mode === "browser") {
    return (
      <StateBanner
        variant="browser-only"
        message={result.reason}
      />
    );
  }

  return (
    <section className="space-y-6">
      <FirstRunOnboarding
        initialState={result.state}
        surface="page"
        cancelLabel="Back to database"
        onCancel={() => navigate("/atualizar-base")}
        onDone={() => navigate("/atualizar-base")}
      />
    </section>
  );
}
