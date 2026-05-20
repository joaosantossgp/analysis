import { notFound } from "next/navigation";

import { CompanyDetailErrorPage } from "@/components/company/company-detail-error";
import { CompanyDetailTracker } from "@/components/company/company-detail-tracker";
import { CompanyHeader } from "@/components/company/company-header";
import { CompanyNoDataPage } from "@/components/company/company-no-data";
import { CompanyOverview } from "@/components/company/company-overview";
import { CompanyPeriodPreset } from "@/components/company/company-period-preset";
import { CompanyStatementsLazy } from "@/components/company/company-statements-lazy";
import { CompanyUrlTabs } from "@/components/company/company-url-tabs";
import { CompanyYearsListWarning } from "@/components/company/company-years-list-warning";
import { SectionHeading, SurfaceCard } from "@/components/shared/design-system-recipes";
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
import { normalizeSelectedYears } from "@/lib/search-params";

const DETAIL_PAGE_MUTABLE_API_READ = {
  cache: "no-store",
} as const;

type CompanyDetailScaffold = {
  company: CompanyInfo;
  readableYears: number[];
  /** `/years` failed unexpectedly (network/upstream); metadata fallback may be incomplete */
  yearsListUnreachable: boolean;
};

export type CompanyDetailScaffoldResult =
  | { kind: "ok"; value: CompanyDetailScaffold }
  | { kind: "not-found" }
  | { kind: "error"; message: string };

export function CompanyHeaderYearsSkeleton() {
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

export function CompanyContentSkeleton() {
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

export async function loadCompanyDetailScaffold(
  cdCvm: number,
): Promise<CompanyDetailScaffoldResult> {
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

export async function CompanyHeaderYearsSection({
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
        variant="full"
      />
    </>
  );
}

export async function CompanyContentSection({
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

    return <CompanyOverview company={company} bundle={bundle} />;
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
