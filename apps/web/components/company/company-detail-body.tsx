import type {
  CompanyInfo,
  KPIBundle,
  StatementMatrix,
} from "@/lib/api";

import { CompanyDetailTracker } from "@/components/company/company-detail-tracker";
import { CompanyHeader } from "@/components/company/company-header";
import { CompanyOverview } from "@/components/company/company-overview";
import { CompanyPeriodPreset } from "@/components/company/company-period-preset";
import { CompanyStatementsLazy } from "@/components/company/company-statements-lazy";
import { CompanyUrlTabs } from "@/components/company/company-url-tabs";
import { CompanyYearsListWarning } from "@/components/company/company-years-list-warning";
import {
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { ApiUnavailableState } from "@/components/ui/api-unavailable-state";
import { DETAIL_TABS, STATEMENT_OPTIONS } from "@/lib/constants";

type CompanyDetailBodyProps = {
  company: CompanyInfo;
  pathname: string;
  currentTab: "visao-geral" | "demonstracoes";
  currentStatement: string;
  readableYears: number[];
  selectedYears: number[];
  bundle: KPIBundle | null;
  statement: StatementMatrix | null;
  contentError: string | null;
  yearsListUnreachable?: boolean;
};

export function CompanyDetailBody({
  company,
  pathname,
  currentTab,
  currentStatement,
  readableYears,
  selectedYears,
  bundle,
  statement,
  contentError,
  yearsListUnreachable = false,
}: CompanyDetailBodyProps) {
  return (
    <PageShell density="default">
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

      {yearsListUnreachable ? (
        <CompanyYearsListWarning context="detail_fallback" />
      ) : null}

      {currentTab === "visao-geral" ? (
        bundle ? (
          <CompanyOverview
            company={company}
            bundle={bundle}
            pathname={pathname}
            availableYears={readableYears}
            selectedYears={selectedYears}
          />
        ) : (
          <ApiUnavailableState
            title="Visao geral indisponivel"
            description={
              contentError ??
              "Nao foi possivel carregar os KPIs desta empresa agora."
            }
            retryHref={pathname}
          />
        )
      ) : (
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
      )}
    </PageShell>
  );
}
