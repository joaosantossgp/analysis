"use client";

import { useEffect, useState } from "react";

import { type CompanySectorFilter, fetchCompanyFilters } from "@/lib/api";
import { type DataLoadState } from "@/lib/update-base-admin";

type UseSectorsCatalogResult = {
  sectors: CompanySectorFilter[];
  sectorState: DataLoadState;
};

export function useSectorsCatalog(
  initialSectors: CompanySectorFilter[],
): UseSectorsCatalogResult {
  const [sectors, setSectors] = useState<CompanySectorFilter[]>(initialSectors);
  const [sectorState, setSectorState] = useState<DataLoadState>(
    initialSectors.length ? "available" : "loading",
  );

  useEffect(() => {
    if (initialSectors.length) {
      setSectorState("available");
    }

    let alive = true;
    const sectorsPromise = initialSectors.length
      ? Promise.resolve({ sectors: initialSectors })
      : fetchCompanyFilters();

    void sectorsPromise
      .then((filters) => {
        if (!alive) return;
        setSectors(filters.sectors);
        setSectorState("available");
      })
      .catch(() => {
        if (!alive) return;
        setSectors([]);
        setSectorState("unavailable");
      });

    return () => {
      alive = false;
    };
  }, [initialSectors]);

  return { sectors, sectorState };
}
