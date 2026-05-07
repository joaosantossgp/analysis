import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CompanyDetailBody } from "@/components/company/company-detail-body";
import { CompanyDetailDesktopLoader } from "@/components/company/company-detail-desktop-loader";
import { CompanyDetailErrorPage } from "@/components/company/company-detail-error";
import { CompanyNoDataPage } from "@/components/company/company-no-data";
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

  let company: CompanyInfo | null = null;
  let availableYears: number[] = [];

  try {
    [company, availableYears] = await Promise.all([
      fetchCompanyInfo(cdCvm, { request: DETAIL_PAGE_MUTABLE_API_READ }),
      fetchCompanyYears(cdCvm, { request: DETAIL_PAGE_MUTABLE_API_READ }).catch(
        (error) => {
          if (isApiClientError(error) && error.code === "not_found") {
            return [];
          }

          throw error;
        },
      ),
    ]);
  } catch (error) {
    if (isApiClientError(error) && error.code === "not_found") {
      notFound();
    }
    return <CompanyDetailErrorPage message={getUserFacingErrorMessage(error)} />;
  }

  if (!company) {
    notFound();
  }

  const readableYears = getReadableCompanyYears(company, availableYears);

  if (readableYears.length === 0) {
    return <CompanyNoDataPage company={company} />;
  }

  const currentTab = coerceDetailTab(getFirstParam(resolvedSearchParams.aba));
  const currentStatement = coerceStatement(getFirstParam(resolvedSearchParams.stmt));
  const selectedYears = normalizeSelectedYears(
    readableYears,
    getFirstParam(resolvedSearchParams.anos),
  );

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
  } else {
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
  }

  return (
    <CompanyDetailBody
      company={company}
      pathname={pathname}
      currentTab={currentTab}
      currentStatement={currentStatement}
      readableYears={readableYears}
      selectedYears={selectedYears}
      bundle={bundle}
      statement={statement}
      contentError={contentError}
    />
  );
}
