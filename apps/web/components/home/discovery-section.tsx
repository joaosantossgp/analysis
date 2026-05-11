"use client";

import Link from "next/link";
import { TrendingUpIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { CompanyDirectoryItem, CompanySectorFilter } from "@/lib/api";
import { getAvailabilityBadgeClassName } from "@/lib/badge-classes";
import { getCompanyAvailability } from "@/lib/company-discovery";
import { getSectorColor } from "@/lib/constants";
import { buildSparklinePoints } from "@/lib/sparkline";
import { cn } from "@/lib/utils";

type Tab = "destaque" | "setores";

const TABS: { id: Tab; label: string }[] = [
  { id: "destaque", label: "Em destaque" },
  { id: "setores", label: "Setores" },
];

type DiscoverySectionProps = {
  destaqueCompanies: CompanyDirectoryItem[];
  gicsSectors: CompanySectorFilter[];
  initialTab?: Tab;
};

function DestaquCard({ co, rank }: { co: CompanyDirectoryItem; rank: number }) {
  const color = getSectorColor(co.sector_name);
  const anos = co.anos_disponiveis ?? [];
  const sparkPts = buildSparklinePoints(anos, 54, 22);
  const availability = getCompanyAvailability(co);
  const sparkColor = availability.kind === "ready" ? "var(--chart-1)" : color;

  return (
    <button
      type="button"
      onClick={() => window.location.assign(`/empresas/${co.cd_cvm}`)}
      className="flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left transition-colors hover:bg-accent/60"
    >
      <span className="w-5 shrink-0 font-mono text-sm text-muted-foreground tabular-nums">
        {rank}
      </span>
      <span
        className="shrink-0 rounded-[0.35rem] px-1.5 py-0.5 font-mono text-xs font-medium"
        style={{
          background: `color-mix(in oklch, ${color} 12%, transparent)`,
          border: `1px solid color-mix(in oklch, ${color} 25%, transparent)`,
          color,
        }}
      >
        {co.ticker_b3 ?? `${co.cd_cvm}`}
      </span>
      <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-sm text-foreground">
        {co.company_name}
      </span>
      {sparkPts ? (
        <svg width={54} height={22} viewBox="0 0 54 22" aria-hidden className="shrink-0">
          <polyline
            points={sparkPts}
            fill="none"
            stroke={sparkColor}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ) : null}
      <span
        className={cn(
          "shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium uppercase tracking-[0.14em]",
          getAvailabilityBadgeClassName(availability.kind),
        )}
      >
        {availability.badge}
      </span>
    </button>
  );
}

export function DiscoverySection({
  destaqueCompanies,
  gicsSectors,
  initialTab,
}: DiscoverySectionProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab: Tab =
    initialTab ??
    (tabParam === "setores" ? "setores" : "destaque");

  function selectTab(tab: Tab) {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("tab", tab);
    router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
  }

  return (
    <section className="w-full max-w-5xl mx-auto space-y-6 text-left">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-[0.26em] text-muted-foreground">
            Descobrir
          </p>
          <h2 className="font-heading text-[2rem] font-medium leading-tight tracking-[-0.04em] text-foreground">
            Por onde comecar
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-7 text-muted-foreground">
            Comece pelas empresas em foco ou navegue pelos setores GICS
            disponiveis no cadastro da aplicacao.
          </p>
        </div>
        <div className="inline-flex items-center gap-0.5 rounded-full border border-border bg-muted p-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => selectTab(tab.id)}
              className={cn(
                "rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-150",
                activeTab === tab.id
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "destaque" ? (
        <div className="rounded-[1.25rem] border border-border/60 bg-card p-5">
          <div className="mb-3 flex items-center gap-2">
            <TrendingUpIcon className="size-4 text-[color:var(--chart-1)]" />
            <span className="text-base font-semibold">Mais visitadas</span>
          </div>
          <div className="flex flex-col gap-0.5">
            {destaqueCompanies.length > 0 ? (
              destaqueCompanies.map((co, i) => (
                <DestaquCard key={co.cd_cvm} co={co} rank={i + 1} />
              ))
            ) : (
              <p className="px-3 py-2 text-sm leading-6 text-muted-foreground">
                Ainda sem visitas registradas. Abra qualquer empresa para comecar o ranking.
              </p>
            )}
          </div>
        </div>
      ) : null}

      {activeTab === "setores" ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {gicsSectors.map((sector) => {
            const color = getSectorColor(sector.gics_sector ?? sector.sector_name);
            return (
            <Link
              key={sector.sector_slug}
              href={`/empresas?setor=${encodeURIComponent(sector.sector_slug)}`}
              className="group flex items-center gap-3 rounded-[1rem] border border-border/60 bg-card px-4 py-3.5 transition-all duration-150 hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-sm"
            >
              <div
                className="flex size-11 shrink-0 items-center justify-center rounded-[12px]"
                style={{
                  background: `color-mix(in oklch, ${color} 14%, transparent)`,
                }}
              >
                <div className="size-3 rounded-full" style={{ backgroundColor: color }} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-foreground leading-tight">
                  {sector.sector_name}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {sector.company_count} empresas
                  {sector.gics_sub_industry ? ` - ${sector.gics_sub_industry}` : ""}
                </p>
              </div>
            </Link>
            );
          })}
          {gicsSectors.length === 0 ? (
            <p className="col-span-full rounded-[1rem] border border-border/60 bg-card px-4 py-3 text-sm text-muted-foreground">
              Sem classificacao GICS disponivel no universo atual. Empresas sem GICS nao sao misturadas aos setores GICS.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
