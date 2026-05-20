import type { Metadata } from "next";
import { Suspense } from "react";

import { CompanyDetailDesktopLoader } from "@/components/company/company-detail-desktop-loader";
import {
  CompanyContentSection,
  CompanyContentSkeleton,
  CompanyHeaderYearsSection,
  CompanyHeaderYearsSkeleton,
  loadCompanyDetailScaffold,
} from "@/components/company/company-detail-page-helpers";
import { PageShell } from "@/components/shared/design-system-recipes";
import { fetchCompanyInfo } from "@/lib/api";
import { isDesktopServerMode } from "@/lib/desktop-mode";
import {
  coerceDetailTab,
  coerceStatement,
  getFirstParam,
} from "@/lib/search-params";

type EmpresaDetailPageProps = {
  params: Promise<{ cd_cvm: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: EmpresaDetailPageProps): Promise<Metadata> {
  const { cd_cvm } = await params;

  if (isDesktopServerMode()) {
    return {
      title: `Empresa ${cd_cvm}`,
      description:
        "Leitura detalhada local via bridge desktop com KPIs anuais e demonstrações financeiras.",
    };
  }

  let company = null;

  try {
    company = await fetchCompanyInfo(Number(cd_cvm));
  } catch {
    return {
      title: "Leitura de empresa indisponivel",
    };
  }

  if (!company) {
    return {
      title: "Empresa nao encontrada",
    };
  }

  return {
    title: company.company_name,
    description: `Leitura detalhada de ${company.company_name} com KPIs anuais, seleção de anos e demonstrações financeiras da CVM.`,
  };
}

export default async function EmpresaDetailPage({
  params,
  searchParams,
}: EmpresaDetailPageProps) {
  const { cd_cvm } = await params;
  const resolvedSearchParams = await searchParams;
  const cdCvm = Number(cd_cvm);

  if (isDesktopServerMode()) {
    return (
      <CompanyDetailDesktopLoader
        cdCvm={cdCvm}
        searchParams={resolvedSearchParams}
      />
    );
  }

  const pathname = `/empresas/${cdCvm}`;
  const currentTab = coerceDetailTab(getFirstParam(resolvedSearchParams.aba));
  const currentStatement = coerceStatement(getFirstParam(resolvedSearchParams.stmt));
  const requestedYearsParam = getFirstParam(resolvedSearchParams.anos);
  const scaffoldPromise = loadCompanyDetailScaffold(cdCvm);

  return (
    <PageShell density="default">
      <Suspense fallback={<CompanyHeaderYearsSkeleton />}>
        <CompanyHeaderYearsSection
          scaffoldPromise={scaffoldPromise}
          pathname={pathname}
          currentTab={currentTab}
          currentStatement={currentStatement}
          requestedYearsParam={requestedYearsParam}
        />
      </Suspense>
      <Suspense fallback={<CompanyContentSkeleton />}>
        <CompanyContentSection
          scaffoldPromise={scaffoldPromise}
          cdCvm={cdCvm}
          pathname={pathname}
          currentTab={currentTab}
          currentStatement={currentStatement}
          requestedYearsParam={requestedYearsParam}
        />
      </Suspense>
    </PageShell>
  );
}
