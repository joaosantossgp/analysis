import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { CompanyDetailDesktopLoader } from "@/components/company/company-detail-desktop-loader";
import { CompanyYearsListWarning } from "@/components/company/company-years-list-warning";
import { CompanyDetailErrorPage } from "@/components/company/company-detail-error";
import { CompanyNoDataPage } from "@/components/company/company-no-data";
import { CompanyDetailTracker } from "@/components/company/company-detail-tracker";
import { CompanyHeader } from "@/components/company/company-header";
import { CompanyOverview } from "@/components/company/company-overview";
import { CompanyPeriodPreset } from "@/components/company/company-period-preset";
import { CompanyStatementsLazy } from "@/components/company/company-statements-lazy";
import { CompanyUrlTabs } from "@/components/company/company-url-tabs";
import {
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { ApiUnavailableState } from "@/components/ui/api-unavailable-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type CompanyInfo,
  fetchCompanyInfo,
  fetchCompanyKpis,
  fetchCompanyStatement,
  fetchCompanyYears,
  getUserFacingErrorMessage,
  isApiClientError,
} from "@/lib/api";
import { getReadableCompanyYears } from "@/lib/company-detail-handoff";
import { DETAIL_TABS, STATEMENT_OPTIONS } from "@/lib/constants";
import { isDesktopServerMode } from "@/lib/desktop-mode";
import {
  coerceDetailTab,
  coerceStatement,
  getFirstParam,
  normalizeSelectedYears,
} from "@/lib/search-params";

type EmpresaDetailPageProps = {
  params: Promise<{ cd_cvm: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export const dynamic = "force-dynamic";

const DETAIL_PAGE_MUTABLE_API_READ = {
  cache: "no-store",
} as const;

type CompanyDetailScaffold = {
  company: CompanyInfo;
  readableYears: number[];
  /** `/years` failed unexpectedly (network/upstream); metadata fallback may be incomplete */
  yearsListUnreachable: boolean;
};

type CompanyDetailScaffoldResult =
  | { kind: "ok"; value: CompanyDetailScaffold }
  | { kind: "not-found" }
  | { kind: "error"; message: string };

function CompanyHeaderYearsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <Skeleton className="h-4 w-64 rounded-full" />
        <Skeleton className="h-32 rounded-3xl" />
      </div>
      <Skeleton className="h-10 w-60 rounded-full" />
      <Skeleton className="h-12 rounded-[1.2rem]" />
    </div>
  );
}

function CompanyContentSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Skeleton className="h-36 rounded-[1.4rem]" />
        <Skeleton className="h-36 rounded-[1.4rem]" />
        <Skeleton className="h-36 rounded-[1.4rem]" />
        <Skeleton className="h-36 rounded-[1.4rem]" />
      </div>
      <Skeleton className="h-96 rounded-3xl" />
    </div>
  );
}

async function loadCompanyDetailScaffold(
  cdCvm: number,
) : Promise<CompanyDetailScaffoldResult> {
  let company: CompanyInfo | null = null;

  try {
    company = await fetchCompanyInfo(cdCvm, {
      request: DETAIL_PAGE_MUTABLE_API_READ,
    });
  } catch (error) {
    if (isApiClientError(error) && error.code === "not_found") {
      return { kind: "not-found" };
    }
    return { kind: "error", message: getUserFacingErrorMessage(error) };
  }

  if (!company) {
    return { kind: "not-found" };
  }

  let availableYears: number[] = [];
  let yearsListUnreachable = false;
  try {
    availableYears = await fetchCompanyYears(cdCvm, {
      request: DETAIL_PAGE_MUTABLE_API_READ,
    });
  } catch (error) {
    availableYears = [];
    if (!isApiClientError(error) || error.code !== "not_found") {
      yearsListUnreachable = true;
    }
  }

  return {
    kind: "ok",
    value: {
      company,
      readableYears: getReadableCompanyYears(company, availableYears),
      yearsListUnreachable,
    },
  };
}

async function CompanyHeaderYearsSection({
  scaffoldPromise,
  pathname,
  currentTab,
  currentStatement,
  requestedYearsParam,
}: {
  scaffoldPromise: Promise<CompanyDetailScaffoldResult>;
  pathname: string;
  currentTab: "visao-geral" | "demonstracoes";
  currentStatement: string;
  requestedYearsParam: string | undefined;
}) {
  const scaffold = await scaffoldPromise;
  if (scaffold.kind === "not-found") {
    notFound();
  }
  if (scaffold.kind === "error") {
    return <CompanyDetailErrorPage message={scaffold.message} />;
  }
  const { company, readableYears, yearsListUnreachable } = scaffold.value;
  const selectedYears = normalizeSelectedYears(readableYears, requestedYearsParam);

  if (readableYears.length === 0) {
    return (
      <CompanyNoDataPage
        company={company}
        yearsListUnreachable={yearsListUnreachable}
      />
    );
  }

  return (
    <>
      {yearsListUnreachable ? (
        <CompanyYearsListWarning context="detail_fallback" />
      ) : null}
      <CompanyDetailTracker
        cdCvm={company.cd_cvm}
        companyName={company.company_name}
        years={selectedYears}
        tab={currentTab}
        statementType={currentStatement}
      />
      <CompanyHeader company={company} selectedYears={selectedYears} />
      <CompanyUrlTabs
        pathname={pathname}
        currentValue={currentTab}
        paramName="aba"
        options={Array.from(DETAIL_TABS)}
      />
      <CompanyPeriodPreset
        pathname={pathname}
        availableYears={readableYears}
        selectedYears={selectedYears}
        variant="custom-only"
      />
    </>
  );
}

async function CompanyContentSection({
  scaffoldPromise,
  cdCvm,
  pathname,
  currentTab,
  currentStatement,
  requestedYearsParam,
}: {
  scaffoldPromise: Promise<CompanyDetailScaffoldResult>;
  cdCvm: number;
  pathname: string;
  currentTab: "visao-geral" | "demonstracoes";
  currentStatement: string;
  requestedYearsParam: string | undefined;
}) {
  const scaffold = await scaffoldPromise;
  if (scaffold.kind !== "ok") {
    return null;
  }
  const { company, readableYears } = scaffold.value;
  const selectedYears = normalizeSelectedYears(readableYears, requestedYearsParam);

  if (readableYears.length === 0) {
    return null;
  }

  let bundle = null;
  let statement = null;
  let contentError: string | null = null;

  if (currentTab === "visao-geral") {
    try {
      bundle = await fetchCompanyKpis(cdCvm, selectedYears, {
        request: DETAIL_PAGE_MUTABLE_API_READ,
      });
    } catch (error) {
      contentError = getUserFacingErrorMessage(error);
    }

    if (!bundle) {
      return (
        <ApiUnavailableState
          title="Visao geral indisponivel"
          description={
            contentError ?? "Nao foi possivel carregar os KPIs desta empresa agora."
          }
          retryHref={pathname}
        />
      );
    }

    return (
      <CompanyOverview
        company={company}
        bundle={bundle}
        pathname={pathname}
        availableYears={readableYears}
        selectedYears={selectedYears}
      />
    );
  }

  try {
    statement = await fetchCompanyStatement(
      cdCvm,
      selectedYears,
      currentStatement,
      {
        request: DETAIL_PAGE_MUTABLE_API_READ,
      },
    );
  } catch (error) {
    contentError = getUserFacingErrorMessage(error);
  }

  return (
    <SurfaceCard tone="default" padding="lg" className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <SectionHeading
          eyebrow="Tipo de demonstracao"
          title="Escolha a visao contabil"
          titleAs="h3"
          description="A tabela respeita os anos selecionados e troca apenas a demonstracao ativa."
          descriptionClassName="text-sm leading-7"
        />
        <CompanyUrlTabs
          pathname={pathname}
          currentValue={currentStatement}
          paramName="stmt"
          options={Array.from(STATEMENT_OPTIONS)}
          eventName="company_statement_changed"
        />
      </div>
      {statement ? (
        <CompanyStatementsLazy matrix={statement} />
      ) : (
        <ApiUnavailableState
          title="Demonstracao indisponivel"
          description={
            contentError ??
            "Nao foi possivel carregar esta demonstracao agora."
          }
          retryHref={pathname}
        />
      )}
    </SurfaceCard>
  );
}

export async function generateMetadata({
  params,
}: EmpresaDetailPageProps): Promise<Metadata> {
  const { cd_cvm } = await params;

  if (isDesktopServerMode()) {
    return {
      title: `Empresa ${cd_cvm}`,
      description:
        "Leitura detalhada local via bridge desktop com KPIs anuais e demonstracoes financeiras.",
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
    description: `Leitura detalhada de ${company.company_name} com KPIs anuais, selecao de anos e demonstracoes financeiras da CVM.`,
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
