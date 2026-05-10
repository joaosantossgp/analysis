import Link from "next/link";
import { ArrowUpRightIcon, Building2Icon } from "lucide-react";

import {
  InfoChip,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { buttonVariants } from "@/components/ui/button";
import type { SectorDirectoryItem } from "@/lib/api";
import { formatCompactInteger, formatKpiValue } from "@/lib/formatters";
import { cn } from "@/lib/utils";

type SectorDirectoryListProps = {
  items: SectorDirectoryItem[];
  groupBy?: "sector" | "sub_sector";
};

const SNAPSHOT_METRICS = [
  { key: "roe", label: "ROE" },
  { key: "mg_ebit", label: "Margem EBIT" },
  { key: "mg_liq", label: "Margem Liquida" },
] as const;

export function SectorDirectoryList({ items, groupBy = "sector" }: SectorDirectoryListProps) {
  if (items.length === 0) {
    return (
      <SurfaceCard
        tone="muted"
        padding="hero"
        className="items-center text-center"
      >
        <p className="font-heading text-2xl text-foreground">
          Nenhum setor disponivel.
        </p>
        <p className="max-w-2xl text-sm leading-7 text-muted-foreground">
          A API nao retornou setores prontos para leitura agora. Tente novamente
          em instantes.
        </p>
      </SurfaceCard>
    );
  }

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <SurfaceCard
          key={item.sector_slug}
          tone="default"
          padding="lg"
          className="flex h-full flex-col justify-between gap-6"
        >
          <div className="space-y-5">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="font-heading text-2xl leading-tight text-foreground">
                    {item.sector_name}
                  </h2>
                  <InfoChip tone="muted">
                    {formatCompactInteger(item.company_count)} empresas
                  </InfoChip>
                </div>
                <p className="text-sm leading-7 text-muted-foreground">
                  {item.group_type === "unclassified"
                    ? "Empresas do universo sem campos GICS persistidos."
                    : groupBy === "sub_sector"
                      ? `Sub-setor GICS${item.parent_sector_name ? ` em ${item.parent_sector_name}` : ""}.`
                      : "Setor GICS com sub-setores e empresas do universo."}
                </p>
                {item.sub_industry_breakdown && item.sub_industry_breakdown.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {item.sub_industry_breakdown.slice(0, 8).map((row) => (
                      <span
                        key={row.name}
                        className="rounded-full border border-border/55 bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground"
                      >
                        {row.name}{" "}
                        <span className="tabular-nums text-foreground/90">
                          ({formatCompactInteger(row.count)})
                        </span>
                      </span>
                    ))}
                    {item.sub_industry_breakdown.length > 8 ? (
                      <span className="rounded-full border border-border/55 bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground">
                        +{item.sub_industry_breakdown.length - 8} sub-setores
                      </span>
                    ) : null}
                  </div>
                ) : item.sub_industries.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {item.sub_industries.slice(0, 3).map((subIndustry) => (
                      <span
                        key={subIndustry}
                        className="rounded-full border border-border/55 bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground"
                      >
                        {subIndustry}
                      </span>
                    ))}
                    {item.sub_industries.length > 3 ? (
                      <span className="rounded-full border border-border/55 bg-muted/35 px-2.5 py-1 text-xs text-muted-foreground">
                        +{item.sub_industries.length - 3}
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </div>

              <div className="flex size-11 shrink-0 items-center justify-center rounded-full border border-border/70 bg-muted/45 text-muted-foreground">
                <Building2Icon className="size-5" />
              </div>
            </div>

            {item.companies && item.companies.length > 0 ? (
              <div className="rounded-[1rem] border border-border/55 bg-background/55 p-3">
                <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
                  Empresas no grupo
                </p>
                <div className="flex flex-col gap-1">
                  {item.companies.slice(0, 8).map((company) => (
                    <Link
                      key={company.cd_cvm}
                      href={`/empresas/${company.cd_cvm}`}
                      className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-muted/50"
                    >
                      <span className="truncate">{company.company_name}</span>
                      <span className="ml-2 shrink-0 text-xs text-muted-foreground">
                        {company.ticker_b3 ?? `CVM ${company.cd_cvm}`}
                      </span>
                    </Link>
                  ))}
                  {item.company_count > item.companies.length ? (
                    <p className="px-2 pt-1 text-xs text-muted-foreground">
                      +{formatCompactInteger(item.company_count - item.companies.length)} empresas no grupo
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}

            <div className="grid gap-3">
              {SNAPSHOT_METRICS.map((metric) => (
                <div
                  key={metric.key}
                  className="flex items-center justify-between gap-3 rounded-[1.2rem] border border-border/55 bg-muted/35 px-4 py-3"
                >
                  <span className="text-sm text-muted-foreground">
                    {metric.label}
                  </span>
                  <span className="font-medium text-foreground">
                    {formatKpiValue(item.snapshot[metric.key], "pct")}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-border/55 pt-5">
            <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">
              Base {item.latest_year ?? "-"}
            </p>
            {item.latest_year != null && item.group_type !== "sub_sector" && item.group_type !== "unclassified" ? (
              <Link
                href={`/setores/${item.sector_slug}`}
                data-testid="sector-card-link"
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "rounded-full px-5",
                )}
              >
                Abrir setor
                <ArrowUpRightIcon className="size-4" />
              </Link>
            ) : (
              <span className="rounded-full border border-border/65 px-4 py-2 text-xs text-muted-foreground">
                {item.group_type === "unclassified" ? "Sem GICS" : "Sem historico ainda"}
              </span>
            )}
          </div>
        </SurfaceCard>
      ))}
    </section>
  );
}
