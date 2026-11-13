import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { fetchSectors, type SectorDirectoryResult, type SectorGroupBy } from "@/lib/api/sectors";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";

function normalizeGroupBy(value: string | null): SectorGroupBy {
  if (value === "sub_sector") return "sub_sector";
  if (value === "cvm_sector") return "cvm_sector";
  return "sector";
}

export function SectorsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const groupBy = normalizeGroupBy(searchParams.get("visao"));
  const includeSnapshots = false;
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
    queryKey: ["sectors", groupBy, { includeSnapshots }],
    queryFn: () => fetchSectors(groupBy, { includeSnapshots }),
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
    else if (next === "cvm_sector") params.set("visao", "cvm_sector");
    else params.delete("visao");
    setSearchParams(params, { replace: true });
  };

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-4">
      <PageHeader
        title="Sectors directory"
        actions={
          <Status query={query} groups={items.length} totalCompanies={totalCompanies} />
        }
      />

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
        <select
          aria-label="Alternative classification"
          value={groupBy === "cvm_sector" ? "cvm_sector" : ""}
          onChange={(event) => setGroupBy(event.target.value === "cvm_sector" ? "cvm_sector" : "sector")}
          className="ml-auto rounded border border-zinc-800 bg-zinc-900 px-2 py-1 text-xs text-zinc-400"
        >
          <option value="">Other classification</option>
          <option value="cvm_sector">CVM Sectors</option>
        </select>
      </div>

      <Body query={query} items={items} groupBy={groupBy} showLatestYear={includeSnapshots} />
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
  if (query.isLoading) return <span className="text-xs text-zinc-500">◌ Loading…</span>;
  if (query.isFetching) return <span className="text-xs text-amber-300">↻ Refreshing…</span>;
  if (query.isError) return <span className="text-xs text-rose-400">! Error</span>;
  if (query.data?.mode === "browser")
    return <span className="text-xs text-amber-300">▲ Browser mode</span>;
  return (
    <span className="font-mono text-xs text-zinc-400">
      {groups.toLocaleString("en-US")} groups · {totalCompanies.toLocaleString("en-US")} companies
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
          ? "rounded border border-zinc-600 bg-zinc-800 px-3 py-1 text-xs font-medium text-zinc-100 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1"
          : "rounded border border-zinc-800 bg-transparent px-3 py-1 text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1"
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
  showLatestYear,
}: {
  query: ReturnType<typeof useQuery<SectorDirectoryResult>>;
  items: SectorDirectoryResult extends { items: infer T } ? (T extends Array<infer I> ? I[] : never) : never;
  groupBy: SectorGroupBy;
  showLatestYear: boolean;
}) {
  if (query.isError) {
    return (
      <StateBanner
        variant="error"
        message={query.error instanceof Error ? query.error.message : String(query.error)}
        onRetry={() => { void query.refetch(); }}
      />
    );
  }
  if (query.data?.mode === "browser") {
    return (
      <StateBanner
        variant="browser-only"
        message={query.data.reason}
      />
    );
  }
  if (query.isLoading || query.data?.mode !== "desktop") {
    return <StateBanner variant="loading" />;
  }
  if (items.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No sector classifications"
        message="No companies have this classification in the local directory. Check company coverage and classification in Companies."
      />
    );
  }
  return <SectorsTable items={items} groupBy={groupBy} showLatestYear={showLatestYear} />;
}

function SectorsTable({
  items,
  groupBy,
  showLatestYear,
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
  showLatestYear: boolean;
}) {
  return (
    <div className="overflow-hidden rounded border border-zinc-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
            <th scope="col" className="px-3 py-2 font-medium">
              {groupBy === "sub_sector" ? "Sub-industry" : "Sector"}
            </th>
            {groupBy === "sub_sector" ? (
              <th scope="col" className="px-3 py-2 font-medium">Parent sector</th>
            ) : groupBy === "sector" ? (
              <th scope="col" className="px-3 py-2 font-medium">Sub-industries</th>
            ) : null}
            <th scope="col" className="px-3 py-2 text-right font-medium">Companies</th>
            {showLatestYear ? <th scope="col" className="px-3 py-2 text-right font-medium">Latest year</th> : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
          {items.map((item) => (
            <SectorRow
              key={`${item.sector_slug}-${item.parent_sector_slug ?? "root"}`}
              item={item}
              groupBy={groupBy}
              showLatestYear={showLatestYear}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectorRow({
  item,
  groupBy,
  showLatestYear,
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
  showLatestYear: boolean;
}) {
  // Detail page is keyed by GICS hub sector slug. Sub-industries point at
  // their parent sector so the user lands somewhere meaningful.
  const linkTo =
    groupBy === "sub_sector"
      ? item.parent_sector_slug && item.sector_slug
        ? `/setores/${item.parent_sector_slug}/${item.sector_slug}`
        : null
      : groupBy === "sector"
      ? item.sector_slug
        ? `/setores/${item.sector_slug}`
        : null
      : `/empresas?sector=${encodeURIComponent(item.sector_slug)}`;
  const subIndustryCount = item.sub_industries?.length ?? 0;
  return (
    <tr className="group hover:bg-zinc-900/50">
      <td className="px-3 py-2">
        {linkTo ? (
          <Link
            to={linkTo}
            className="font-medium text-zinc-100 group-hover:text-cyan-300"
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
      ) : groupBy === "sector" ? (
        <td className="px-3 py-2 text-xs text-zinc-500">
          {subIndustryCount > 0
            ? `${subIndustryCount.toLocaleString("en-US")} sub-industries`
            : "—"}
        </td>
      ) : null}
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-300">
        {item.company_count.toLocaleString("en-US")}
      </td>
      {showLatestYear ? (
        <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
          {item.latest_year ?? "—"}
        </td>
      ) : null}
    </tr>
  );
}
