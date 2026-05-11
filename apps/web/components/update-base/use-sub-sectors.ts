"use client";

import { useEffect, useState } from "react";

import { fetchSectorDirectory } from "@/lib/api";

type SubSector = { name: string; count: number };

export function useSubSectors(): SubSector[] {
  const [subSectors, setSubSectors] = useState<SubSector[]>([]);

  useEffect(() => {
    let alive = true;

    void fetchSectorDirectory({ groupBy: "sub_sector" })
      .then((directory) => {
        if (!alive) return;
        setSubSectors(
          directory.items
            .filter((item) => item.group_type === "sub_sector")
            .map((item) => ({ name: item.sector_name, count: item.company_count })),
        );
      })
      .catch(() => {
        if (!alive) return;
        setSubSectors([]);
      });

    return () => {
      alive = false;
    };
  }, []);

  return subSectors;
}
