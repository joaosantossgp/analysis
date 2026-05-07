import type { Metadata } from "next";

import { CompareDesktopLoader } from "@/components/compare/compare-desktop-loader";
import { ComparePageView } from "@/components/compare/compare-page-view";
import { fetchCompanySuggestions, type CompanySuggestionItem } from "@/lib/api";
import {
  loadComparePageData,
  type CompareCompanyOption,
} from "@/lib/compare-page-data";
import { getSectorNameFromSlug } from "@/lib/constants";
import { isDesktopServerMode } from "@/lib/desktop-mode";
import { getFirstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Comparar",
  description:
    "Comparacao lado a lado de empresas com base nos KPIs anuais da API V2.",
};

export const dynamic = "force-dynamic";

type ComparePageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

function toQuickOption(item: CompanySuggestionItem): CompareCompanyOption {
  return {
    cd_cvm: item.cd_cvm,
    company_name: item.company_name,
    ticker_b3: item.ticker_b3,
    sector_name: getSectorNameFromSlug(item.sector_slug) ?? "Setor nao informado",
  };
}

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const resolvedSearchParams = await searchParams;
  const ids = getFirstParam(resolvedSearchParams.ids);
  const years = getFirstParam(resolvedSearchParams.anos);

  if (isDesktopServerMode()) {
    return <CompareDesktopLoader ids={ids} years={years} />;
  }

  const [compareData, quickPayload] = await Promise.all([
    loadComparePageData(ids, years),
    fetchCompanySuggestions("", 8, { readyOnly: true }).catch(() => null),
  ]);

  const quickCompanies = (quickPayload?.items ?? []).map(toQuickOption);
  const saneQuickCompanies = quickCompanies.filter(
    (company) =>
      Number.isFinite(company.cd_cvm) &&
      company.cd_cvm > 0 &&
      company.company_name.trim() !== "--",
  );

  return (
    <ComparePageView
      compareData={compareData}
      quickCompanies={saneQuickCompanies}
    />
  );
}
