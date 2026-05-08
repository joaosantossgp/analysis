"use client";

import { useEffect, useState } from "react";

import { TrustStrip } from "@/components/home/trust-strip";
import { fetchHealth, type HealthResponse } from "@/lib/api";
import { isDesktopMode } from "@/lib/desktop-bridge";

type HomeTrustStripProps = {
  totalCompanies: number | null;
  disableHealthCheck?: boolean;
};

export function HomeTrustStrip({
  totalCompanies,
  disableHealthCheck = false,
}: HomeTrustStripProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(!disableHealthCheck);

  useEffect(() => {
    if (disableHealthCheck) {
      setHealth(null);
      setHealthLoading(false);
      return;
    }

    const controller = new AbortController();

    const loadHealth = async () => {
      if (isDesktopMode()) {
        setHealthLoading(false);
        return;
      }

      try {
        const payload = await fetchHealth();
        if (!controller.signal.aborted) {
          setHealth(payload);
        }
      } catch {
        if (!controller.signal.aborted) {
          setHealth(null);
        }
      } finally {
        if (!controller.signal.aborted) {
          setHealthLoading(false);
        }
      }
    };

    void loadHealth();

    return () => {
      controller.abort();
    };
  }, [disableHealthCheck]);

  return (
    <TrustStrip
      health={health}
      totalCompanies={totalCompanies}
      healthLoading={healthLoading}
    />
  );
}
