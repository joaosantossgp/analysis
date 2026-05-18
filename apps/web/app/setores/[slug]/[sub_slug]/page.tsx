import Link from "next/link";
import type { Metadata } from "next";
import { ChevronRightIcon } from "lucide-react";
import { notFound } from "next/navigation";

import { SectorCompanyTable } from "@/components/sectors/sector-company-table";
import { SectorDetailDesktopLoader } from "@/components/sectors/sector-detail-desktop-loader";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { fetchSubSectorDetail } from "@/lib/api";
import { formatCompactInteger } from "@/lib/formatters";
import { isDesktopServerMode } from "@/lib/desktop-mode";
import { getFirstParam } from "@/lib/search-params";
import { loadSubSectorDetailPageData } from "@/lib/sectors-page-data";
import { cn } from "@/lib/utils";

type SubSectorDetailPageProps = {
  params: Promise<{ slug: string; sub_slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

const SECTOR_TABS = [
  { value: "visao-geral", label: "Visao Geral" },
  { value: "empresas", label: "Empresas" },
] as const;

export const dynamic = "force-dynamic";

function SubSectorDetailError({ message }: { message: string }) {
  return (
    <PageShell density="relaxed" className="max-w-4xl">
      <SurfaceCard tone="hero" padding="hero" className="space-y-6">
        <SectionHeading
          eyebrow="PG-06 - Detalhe da sub-industria"
          title="Leitura setorial indisponivel"
          titleAs="h1"
          description="O detalhe da sub-industria nao conseguiu concluir a leitura agora."
        />
        <Alert variant="destructive-soft">
          <AlertTitle>Falha controlada do detalhe setorial</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/setores"
            className={cn(buttonVariants({ size: "lg" }), "rounded-full px-5")}
          >
            Voltar para setores
          </Link>
        </div>
      </SurfaceCard>
    </PageShell>
  );
}

export async function generateMetadata({
  params,
}: SubSectorDetailPageProps): Promise<Metadata> {
  const { slug, sub_slug } = await params;

  if (isDesktopServerMode()) {
    return {
      title: `Sub-setor ${sub_slug}`,
      description:
        "Leitura local da sub-industria GICS via bridge desktop.",
    };
  }

  try {
    const detail = await fetchSubSectorDetail(slug, sub_slug);
    if (!detail) {
      return { title: "Sub-setor nao encontrado" };
    }
    return {
      title: `${detail.sector_name} (${detail.parent_sector_name ?? slug})`,
      description: `Leitura da sub-industria GICS ${detail.sector_name} dentro de ${detail.parent_sector_name ?? slug}.`,
    };
  } catch {
    return { title: "Leitura setorial indisponivel" };
  }
}

export default async function SubSectorDetailPage({
  params,
  searchParams,
}: SubSectorDetailPageProps) {
  const { slug, sub_slug } = await params;
  const resolvedSearchParams = await searchParams;
  const rawYear = getFirstParam(resolvedSearchParams.ano);
  const rawTab = getFirstParam(resolvedSearchParams.aba);
  const pathname = `/setores/${slug}/${sub_slug}`;

  if (isDesktopServerMode()) {
    return (
      <SectorDetailDesktopLoader
        slug={slug}
        rawYear={rawYear}
        rawTab={rawTab}
        subIndustrySlug={sub_slug}
      />
    );
  }

  const { detail, currentTab, detailError } = await loadSubSectorDetailPageData(
    slug,
    sub_slug,
    rawYear,
    rawTab,
  );

  if (!detail) {
    if (!detailError) {
      notFound();
    }
    return <SubSectorDetailError message={detailError} />;
  }

  // Cross-check: parent slug returned by backend must match the URL segment.
  // Defensive — backend already enforces this, but a mismatch here is a 404.
  if (detail.parent_sector_slug && detail.parent_sector_slug !== slug) {
    notFound();
  }

  const parentSectorName = detail.parent_sector_name ?? slug;
  const parentSectorSlug = detail.parent_sector_slug ?? slug;
  const companiesBySectorHref = `/empresas?setor=${encodeURIComponent(parentSectorSlug)}&anos=${detail.selected_year}`;

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
            <li className="flex items-center gap-2">
              <ChevronRightIcon className="size-4" />
              <Link
                href={`/setores/${parentSectorSlug}`}
                className="hover:text-foreground"
              >
                {parentSectorName}
              </Link>
            </li>
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
                <InfoChip tone="brand">Sub-industria GICS</InfoChip>
                <InfoChip>{formatCompactInteger(detail.company_count)} empresas</InfoChip>
                <InfoChip tone="muted">Base {detail.selected_year}</InfoChip>
              </div>

              <div className="space-y-3">
                <h1 className="font-heading text-4xl tracking-[-0.05em] text-foreground sm:text-5xl">
                  {detail.sector_name}
                </h1>
                <p className="max-w-3xl text-sm leading-7 text-muted-foreground">
                  Sub-industria GICS dentro de{" "}
                  <Link
                    href={`/setores/${parentSectorSlug}`}
                    className="font-medium text-foreground hover:underline"
                  >
                    {parentSectorName}
                  </Link>
                  . As metricas e o ranking respeitam o ano selecionado.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href={companiesBySectorHref}
                className={cn(
                  buttonVariants({ variant: "outline", size: "lg" }),
                  "rounded-full px-5",
                )}
              >
                Filtrar empresas do setor pai
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
              Ano invalido ou ausente cai automaticamente para o periodo mais
              recente disponivel da sub-industria.
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

      <SectorUrlTabs
        pathname={pathname}
        currentValue={currentTab}
        options={Array.from(SECTOR_TABS)}
      />

      {currentTab === "visao-geral" ? (
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
