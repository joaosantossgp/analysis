import Link from "next/link";

import { CompareKpiTable } from "@/components/compare/compare-kpi-table";
import { CompareSelector } from "@/components/compare/compare-selector";
import { CompareTracker } from "@/components/compare/compare-tracker";
import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import type { CompareCompanyOption, ComparePageData } from "@/lib/compare-page-data";
import { cn } from "@/lib/utils";

function getComparisonStateCopy(compareData: ComparePageData): {
  title: string;
  description: string;
} | null {
  if (compareData.selectedCompanies.length < 2 || !compareData.dataError) {
    return null;
  }

  if (compareData.availableYears.length === 0) {
    return {
      title: "Sem periodo em comum",
      description:
        "A selecao atual nao chegou a um recorte anual comum. Ajuste as empresas ou volte ao diretorio para montar outra combinacao.",
    };
  }

  if (compareData.comparedCompanies.length < 2) {
    return {
      title: "Dados insuficientes para comparar",
      description:
        "A pagina manteve a selecao atual, mas ainda faltam ao menos duas empresas com dados validos para o periodo resolvido.",
    };
  }

  return {
    title: "Comparacao precisa de ajuste",
    description:
      "Os dados foram carregados, mas este recorte ainda nao produz uma tabela comparavel util. Ajuste o periodo ou a combinacao de empresas.",
  };
}

export type ComparePageViewProps = {
  compareData: ComparePageData;
  quickCompanies: CompareCompanyOption[];
};

export function ComparePageView({
  compareData,
  quickCompanies,
}: ComparePageViewProps) {
  const comparisonState = getComparisonStateCopy(compareData);
  const partialErrorDescription =
    compareData.partialErrors.length === 0
      ? null
      : [
          compareData.partialErrors.slice(0, 3).join(" "),
          compareData.comparedCompanies.length >= 2 &&
          compareData.comparedCompanies.length < compareData.selectedCompanies.length
            ? `A tabela abaixo usa ${compareData.comparedCompanies.length} empresas com dados completos para o periodo.`
            : null,
        ]
          .filter(Boolean)
          .join(" ");

  return (
    <PageShell density="default">
      <CompareTracker
        companyIds={compareData.selectedCompanies.map((company) => company.cd_cvm)}
        years={compareData.selectedYears}
        comparableCompanies={compareData.comparedCompanies.length}
      />

      <SectionHeading
        eyebrow="PG-04 - Comparar"
        title="Comparacao de empresas"
        titleAs="h1"
        description="Monte uma comparacao lado a lado apenas com empresas prontas. Se uma companhia ainda for solicitavel ou tiver sinal fraco, abra o diretorio primeiro."
        meta={
          <InfoChip tone="muted">
            {compareData.comparedCompanies.length >= 2
              ? `${compareData.comparedCompanies.length} empresas comparaveis`
              : "Selecione ao menos 2 empresas"}
          </InfoChip>
        }
      />

      <CompareSelector
        pathname="/comparar"
        selectedCompanies={compareData.selectedCompanies}
        quickCompanies={quickCompanies}
        availableYears={compareData.availableYears}
        selectedYears={compareData.selectedYears}
      />

      {compareData.dataError ? (
        <Alert variant="destructive-soft">
          <AlertTitle>Comparacao indisponivel no estado atual</AlertTitle>
          <AlertDescription>{compareData.dataError}</AlertDescription>
        </Alert>
      ) : null}

      {compareData.partialErrors.length > 0 ? (
        <Alert className="rounded-3xl border-border/70 bg-background/85 px-5 py-4 text-left">
          <AlertTitle>Alguns dados nao puderam ser carregados</AlertTitle>
          <AlertDescription>{partialErrorDescription}</AlertDescription>
        </Alert>
      ) : null}

      {compareData.selectedCompanies.length < 2 ? (
        <SurfaceCard tone="muted" padding="hero" className="space-y-5">
          <SectionHeading
            eyebrow="Passo inicial"
            title="Selecione ao menos duas empresas"
            titleAs="h2"
            description="Use a busca da comparacao ou entre pelo diretorio de empresas para montar a primeira analise lado a lado."
            descriptionClassName="text-sm leading-7"
          />
          <div className="flex flex-wrap gap-3">
            <Link
              href="/empresas"
              className={cn(
                buttonVariants({ size: "lg" }),
                "rounded-full px-5",
              )}
            >
              Abrir diretorio
            </Link>
            <Link
              href="/"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "rounded-full px-5",
              )}
            >
              Voltar para home
            </Link>
          </div>
        </SurfaceCard>
      ) : null}

      {comparisonState ? (
        <SurfaceCard
          tone="muted"
          padding="hero"
          className="space-y-5"
          data-testid="compare-state-card"
        >
          <SectionHeading
            eyebrow="Estado atual"
            title={comparisonState.title}
            titleAs="h2"
            description={comparisonState.description}
            descriptionClassName="text-sm leading-7"
          />
          <div className="flex flex-wrap gap-3">
            <Link
              href="/comparar"
              className={cn(
                buttonVariants({ size: "lg" }),
                "rounded-full px-5",
              )}
            >
              Reiniciar comparacao
            </Link>
            <Link
              href="/empresas"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "rounded-full px-5",
              )}
            >
              Escolher outras empresas
            </Link>
          </div>
        </SurfaceCard>
      ) : null}

      {compareData.comparedCompanies.length >= 2 &&
      compareData.referenceYear !== null &&
      compareData.rows.length > 0 &&
      !compareData.dataError ? (
        <CompareKpiTable
          companies={compareData.comparedCompanies}
          rows={compareData.rows}
          referenceYear={compareData.referenceYear}
        />
      ) : null}
    </PageShell>
  );
}
