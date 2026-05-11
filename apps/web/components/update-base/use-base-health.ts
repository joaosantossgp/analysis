"use client";

import { useEffect, useState } from "react";

import { fetchBaseHealth } from "@/lib/api";
import { type DataLoadState, getDefaultBaseHealthWindow } from "@/lib/update-base-admin";

type BaseHealth = Awaited<ReturnType<typeof fetchBaseHealth>> | null;

type UseBaseHealthResult = {
  baseHealth: BaseHealth;
  baseHealthState: DataLoadState;
};

export function useBaseHealth(): UseBaseHealthResult {
  const [baseHealth, setBaseHealth] = useState<BaseHealth>(null);
  const [baseHealthState, setBaseHealthState] = useState<DataLoadState>("loading");

  useEffect(() => {
    let alive = true;
    const window = getDefaultBaseHealthWindow();

    void fetchBaseHealth(window)
      .then((health) => {
        if (!alive) return;
        setBaseHealth(health);
        setBaseHealthState("available");
      })
      .catch(() => {
        if (!alive) return;
        setBaseHealth(null);
        setBaseHealthState("unavailable");
      });

    return () => {
      alive = false;
    };
  }, []);

  return { baseHealth, baseHealthState };
}
