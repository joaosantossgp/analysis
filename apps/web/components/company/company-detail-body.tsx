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
import {
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
          <Alert variant="destructive-soft">
            <AlertTitle>Visao geral indisponivel</AlertTitle>
            <AlertDescription>
              {contentError ??
                "Nao foi possivel carregar os KPIs desta empresa agora."}
            </AlertDescription>
          </Alert>
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
          <CompanyPeriodPreset
            pathname={pathname}
            availableYears={readableYears}
            selectedYears={selectedYears}
            variant="custom-only"
          />
          {statement ? (
            <CompanyStatementsLazy matrix={statement} />
          ) : (
            <Alert variant="destructive-soft">
              <AlertTitle>Demonstracao indisponivel</AlertTitle>
              <AlertDescription>
                {contentError ??
                  "Nao foi possivel carregar esta demonstracao agora."}
              </AlertDescription>
            </Alert>
          )}
        </SurfaceCard>
      )}
    </PageShell>
  );
}
