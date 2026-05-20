"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronRightIcon } from "lucide-react";

import { SectorCompanyTable } from "@/components/sectors/sector-company-table";
import { SectorDetailTracker } from "@/components/sectors/sector-detail-tracker";
import { SectorOverview } from "@/components/sectors/sector-overview";
import { SectorUrlTabs } from "@/components/sectors/sector-url-tabs";
import { SectorYearSelector } from "@/components/sectors/sector-year-selector";
import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { ProblemStateCard } from "@/components/shared/problem-state-card";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
import { buttonVariants } from "@/components/ui/button";
import type { SectorDetail } from "@/lib/api";
import {
  bridgeFetchSectorDetail,
  bridgeFetchSubSectorDetail,
} from "@/lib/desktop-bridge";
import { formatCompactInteger } from "@/lib/formatters";
import {
  coerceSectorTab,
  resolveSectorYear,
  type SectorPageTab,
} from "@/lib/sectors-params";
import { cn } from "@/lib/utils";

const SECTOR_TABS = [
  { value: "visao-geral", label: "Visao Geral" },
  { value: "empresas", label: "Empresas" },
] as const;

type SectorDetailDesktopLoaderProps = {
  slug: string;
  rawYear: string | undefined;
  rawTab: string | undefined;
  // When set, the loader resolves the GICS sub-industry inside `slug` instead
  // of the top-level sector.
  subIndustrySlug?: string;
};

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Nao foi possivel carregar os dados locais agora.";
}

export function SectorDetailDesktopLoader({
  slug,
  rawYear,
  rawTab,
  subIndustrySlug,
}: SectorDetailDesktopLoaderProps) {
  const loadKey = `${slug}|${subIndustrySlug ?? ""}|${rawYear ?? ""}|${rawTab ?? ""}`;
  const currentTab = coerceSectorTab(rawTab);
  const pathname = subIndustrySlug
    ? `/setores/${slug}/${subIndustrySlug}`
    : `/setores/${slug}`;
  const bridgeReady = useDesktopBridgeReady(loadKey);
  const fetchDetail = useCallback(
    (year?: number) =>
      subIndustrySlug
        ? bridgeFetchSubSectorDetail(slug, subIndustrySlug, year)
        : bridgeFetchSectorDetail(slug, year),
    [slug, subIndustrySlug],
  );

  const [state, setState] = useState<{
    key: string;
    phase:
      | "loading"
      | "bridge_timeout"
      | "error"
      | "not_found"
      | "ready";
    errorMessageText?: string;
    detail?: SectorDetail;
    resolvedTab?: SectorPageTab;
  } | null>(null);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function load() {
      if (cancelled) return;

      setState({ key: loadKey, phase: "loading", resolvedTab: currentTab });

      try {
        const latestDetail = await fetchDetail();

        if (cancelled) return;

        if (!latestDetail) {
          setState({
            key: loadKey,
            phase: "not_found",
            resolvedTab: currentTab,
          });
          return;
        }

        if (
          subIndustrySlug &&
          latestDetail.parent_sector_slug &&
          latestDetail.parent_sector_slug !== slug
        ) {
          setState({
            key: loadKey,
            phase: "not_found",
            resolvedTab: currentTab,
          });
          return;
        }

        const resolvedYear = resolveSectorYear(
          latestDetail.available_years,
          rawYear,
          latestDetail.selected_year,
        );

        let detail: SectorDetail | null = latestDetail;

        if (resolvedYear !== latestDetail.selected_year) {
          try {
            const scoped = await fetchDetail(resolvedYear);
            detail = scoped ?? latestDetail;
          } catch {
            detail = latestDetail;
          }
        }

        if (cancelled) return;

        setState({
          key: loadKey,
          phase: "ready",
          detail: detail ?? latestDetail,
          resolvedTab: currentTab,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          key: loadKey,
          phase: "error",
          errorMessageText: errorMessage(error),
          resolvedTab: currentTab,
        });
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [
    bridgeReady,
    loadKey,
    slug,
    subIndustrySlug,
    rawYear,
    rawTab,
    currentTab,
    fetchDetail,
  ]);

  if (bridgeReady === "timeout" && (!state || state.key !== loadKey)) {
    return (
      <ProblemStateCard
        eyebrow="PG-06 - Detalhe do setor"
        title="Leitura setorial indisponivel"
        description="O detalhe do setor nao conseguiu concluir a leitura agora."
        alertTitle="Falha controlada do detalhe setorial"
        alertDescription="Bridge local do desktop indisponivel. Reabra o aplicativo para carregar os dados locais."
        actions={[
          { href: "/setores", label: "Voltar para setores" },
          { href: "/empresas", label: "Abrir empresas", variant: "outline" },
        ]}
      />
    );
  }

  if (!state || state.key !== loadKey) {
    return (
      <PageShell density="relaxed">
        <SurfaceCard tone="hero" padding="hero" className="animate-pulse space-y-4">
          <div className="h-12 w-72 rounded-full bg-muted/70" />
          <div className="h-40 rounded-2xl bg-muted/50" />
        </SurfaceCard>
      </PageShell>
    );
  }

  if (state.phase === "loading") {
    return (
      <PageShell density="relaxed">
        <SurfaceCard tone="hero" padding="hero" className="animate-pulse space-y-4">
          <div className="h-12 w-72 rounded-full bg-muted/70" />
          <div className="h-40 rounded-2xl bg-muted/50" />
        </SurfaceCard>
      </PageShell>
    );
  }

  if (state.phase === "bridge_timeout" || state.phase === "error") {
    return (
      <ProblemStateCard
        eyebrow="PG-06 - Detalhe do setor"
        title="Leitura setorial indisponivel"
        description="O detalhe do setor nao conseguiu concluir a leitura agora."
        alertTitle="Falha controlada do detalhe setorial"
        alertDescription={state.errorMessageText}
        actions={[
          { href: "/setores", label: "Voltar para setores" },
          { href: "/empresas", label: "Abrir empresas", variant: "outline" },
        ]}
      />
    );
  }

  if (state.phase === "not_found") {
    return (
      <ProblemStateCard
        eyebrow="PG-06 - Detalhe do setor"
        title="Setor nao encontrado"
        description="Nao ha dados locais para este slug de setor na base empacotada."
        actions={[{ href: "/setores", label: "Voltar para setores" }]}
      />
    );
  }

  const detail = state.detail!;
  const tab = state.resolvedTab ?? currentTab;
  const isSubIndustry = Boolean(subIndustrySlug);
  const parentSectorName = detail.parent_sector_name ?? slug;
  const parentSectorSlug = detail.parent_sector_slug ?? slug;

  return (
    <PageShell density="default">
      <SectorDetailTracker
        sectorSlug={detail.sector_slug}
        sectorName={detail.sector_name}
        selectedYear={detail.selected_year}
        companyCount={detail.company_count}
      />

      <div className="space-y-5">
        <nav aria-label="breadcrumb">
          <ol className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <li>
              <Link href="/" className="hover:text-foreground">
                Home
              </Link>
            </li>
            <li className="flex items-center gap-2">
              <ChevronRightIcon className="size-4" />
              <Link href="/setores" className="hover:text-foreground">
                Setores
              </Link>
            </li>
            {isSubIndustry ? (
              <li className="flex items-center gap-2">
                <ChevronRightIcon className="size-4" />
                <Link
                  href={`/setores/${parentSectorSlug}`}
                  className="hover:text-foreground"
                >
                  {parentSectorName}
                </Link>
              </li>
            ) : null}
            <li className="flex items-center gap-2 text-foreground">
              <ChevronRightIcon className="size-4 text-muted-foreground" />
              <span>{detail.sector_name}</span>
            </li>
          </ol>
        </nav>

        <SurfaceCard tone="default" padding="lg">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <InfoChip tone="brand">PG-06 - Detalhe do setor</InfoChip>
                <InfoChip>{formatCompactInteger(detail.company_count)} empresas</InfoChip>
                <InfoChip tone="muted">Base {detail.selected_year}</InfoChip>
              </div>

              <div className="space-y-3">
                <h1 className="font-heading text-4xl tracking-[-0.05em] text-foreground sm:text-5xl">
                  {detail.sector_name}
                </h1>
                <p className="max-w-3xl text-sm leading-7 text-muted-foreground">
                  O detalhe setorial combina leitura agregada por ano e ranking anual de empresas,
                  sempre sobre o mesmo slug canonico da base local.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href={`/empresas?setor=${detail.sector_slug}`}
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "rounded-full px-5",
                )}
              >
                Filtrar empresas deste setor
              </Link>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard tone="subtle" padding="md" className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-[0.26em] text-muted-foreground">
              Recorte anual
            </p>
            <p className="text-sm leading-7 text-muted-foreground">
              Ano invalido ou ausente cai automaticamente para o periodo mais recente disponivel do
              setor.
            </p>
          </div>
          <SectorYearSelector
            pathname={pathname}
            sectorSlug={detail.sector_slug}
            availableYears={detail.available_years}
            selectedYear={detail.selected_year}
          />
        </div>
      </SurfaceCard>

      <SectorUrlTabs pathname={pathname} currentValue={tab} options={Array.from(SECTOR_TABS)} />

      {tab === "visao-geral" ? (
        <SectorOverview detail={detail} />
      ) : (
        <SectorCompanyTable
          companies={detail.companies}
          sectorSlug={detail.sector_slug}
          selectedYear={detail.selected_year}
        />
      )}
    </PageShell>
  );
}
