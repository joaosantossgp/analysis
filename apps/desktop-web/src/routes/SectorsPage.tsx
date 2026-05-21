import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { fetchSectors, type SectorDirectoryResult, type SectorGroupBy } from "@/lib/api/sectors";
import { whenBridgeReady } from "@/lib/bridge/adapter";

function normalizeGroupBy(value: string | null): SectorGroupBy {
  return value === "sub_sector" ? "sub_sector" : "sector";
}

export function SectorsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const groupBy = normalizeGroupBy(searchParams.get("visao"));
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

  const query = useQuery<SectorDirectoryResult>({
    queryKey: ["sectors", groupBy],
    queryFn: () => fetchSectors(groupBy),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const items = query.data?.mode === "desktop" ? query.data.items : [];
  const totalCompanies = useMemo(
    () => items.reduce((acc, item) => acc + (item.company_count || 0), 0),
    [items],
  );

  const setGroupBy = (next: SectorGroupBy) => {
    const params = new URLSearchParams(searchParams);
    if (next === "sub_sector") params.set("visao", "sub_sector");
    else params.delete("visao");
    setSearchParams(params, { replace: true });
  };

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            Sectors directory
          </h2>
          <p className="text-xs text-zinc-500">
            GICS hub view — counts and coverage from the local CVM database.
          </p>
        </div>
        <Status query={query} groups={items.length} totalCompanies={totalCompanies} />
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <GroupTab
          active={groupBy === "sector"}
          label="GICS Sectors"
          onClick={() => setGroupBy("sector")}
        />
        <GroupTab
          active={groupBy === "sub_sector"}
          label="GICS Sub-industries"
          onClick={() => setGroupBy("sub_sector")}
        />
      </div>

      <Body query={query} items={items} groupBy={groupBy} />
    </section>
  );
}

function Status({
  query,
  groups,
  totalCompanies,
}: {
  query: ReturnType<typeof useQuery<SectorDirectoryResult>>;
  groups: number;
  totalCompanies: number;
}) {
  if (query.isLoading) return <span className="text-xs text-zinc-500">Loading…</span>;
  if (query.isFetching) return <span className="text-xs text-amber-300">Refreshing…</span>;
  if (query.isError) return <span className="text-xs text-rose-400">Error</span>;
  if (query.data?.mode === "browser")
    return <span className="text-xs text-amber-300">Browser mode</span>;
  return (
    <span className="font-mono text-xs text-zinc-400">
      {groups.toLocaleString("pt-BR")} groups · {totalCompanies.toLocaleString("pt-BR")} companies
    </span>
  );
}

function GroupTab({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded border border-zinc-600 bg-zinc-800 px-3 py-1 text-xs font-medium text-zinc-100"
          : "rounded border border-zinc-800 bg-transparent px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
      }
    >
      {label}
    </button>
  );
}

function Body({
  query,
  items,
  groupBy,
}: {
  query: ReturnType<typeof useQuery<SectorDirectoryResult>>;
  items: SectorDirectoryResult extends { items: infer T } ? (T extends Array<infer I> ? I[] : never) : never;
  groupBy: SectorGroupBy;
}) {
  if (query.isError) {
    return (
      <p
        role="alert"
        className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300"
      >
        {query.error instanceof Error ? query.error.message : String(query.error)}
      </p>
    );
  }
  if (query.data?.mode === "browser") {
    return (
      <div className="space-y-2 rounded border border-amber-900/60 bg-amber-950/30 p-3 text-sm text-amber-200">
        <p className="font-medium">Browser-mode preview</p>
        <p className="text-amber-200/80">{query.data.reason}</p>
      </div>
    );
  }
  if (query.isLoading || query.data?.mode !== "desktop") {
    return <p className="text-sm text-zinc-500">Loading sectors…</p>;
  }
  if (items.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        No sectors available. Run Update Base to populate company data, then
        return to this screen.
      </p>
    );
  }
  return <SectorsTable items={items} groupBy={groupBy} />;
}

function SectorsTable({
  items,
  groupBy,
}: {
  items: Array<{
    sector_name: string;
    sector_slug: string;
    company_count: number;
    latest_year: number | null;
    sub_industries: string[];
    parent_sector_name: string | null;
    parent_sector_slug: string | null;
  }>;
  groupBy: SectorGroupBy;
}) {
  return (
    <div className="overflow-hidden rounded border border-zinc-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
            <th className="px-3 py-2 font-medium">
              {groupBy === "sub_sector" ? "Sub-industry" : "Sector"}
            </th>
            {groupBy === "sub_sector" ? (
              <th className="px-3 py-2 font-medium">Parent sector</th>
            ) : (
              <th className="px-3 py-2 font-medium">Sub-industries</th>
            )}
            <th className="px-3 py-2 text-right font-medium">Companies</th>
            <th className="px-3 py-2 text-right font-medium">Latest year</th>
            <th className="px-3 py-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
          {items.map((item) => (
            <SectorRow key={`${item.sector_slug}-${item.parent_sector_slug ?? "root"}`} item={item} groupBy={groupBy} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectorRow({
  item,
  groupBy,
}: {
  item: {
    sector_name: string;
    sector_slug: string;
    company_count: number;
    latest_year: number | null;
    sub_industries: string[];
    parent_sector_name: string | null;
    parent_sector_slug: string | null;
  };
  groupBy: SectorGroupBy;
}) {
  // Detail page is keyed by GICS hub sector slug. Sub-industries point at
  // their parent sector so the user lands somewhere meaningful.
  const detailSlug =
    groupBy === "sub_sector" ? item.parent_sector_slug : item.sector_slug;
  const subIndustryCount = item.sub_industries?.length ?? 0;
  return (
    <tr className="group hover:bg-zinc-900/50">
      <td className="px-3 py-2">
        {detailSlug ? (
          <Link
            to={`/setores/${detailSlug}`}
            className="font-medium text-zinc-100 group-hover:text-emerald-300"
          >
            {item.sector_name}
          </Link>
        ) : (
          <span className="font-medium text-zinc-100">{item.sector_name}</span>
        )}
      </td>
      {groupBy === "sub_sector" ? (
        <td className="px-3 py-2 text-xs text-zinc-400">
          {item.parent_sector_name ?? "—"}
        </td>
      ) : (
        <td className="px-3 py-2 text-xs text-zinc-500">
          {subIndustryCount > 0
            ? `${subIndustryCount.toLocaleString("pt-BR")} sub-industries`
            : "—"}
        </td>
      )}
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-300">
        {item.company_count.toLocaleString("pt-BR")}
      </td>
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
        {item.latest_year ?? "—"}
      </td>
      <td className="px-3 py-2 text-xs">
        <Link
          to={`/?sector=${encodeURIComponent(item.sector_slug)}`}
          className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-300 hover:border-emerald-700 hover:text-emerald-300"
        >
          View companies →
        </Link>
      </td>
    </tr>
  );
}
