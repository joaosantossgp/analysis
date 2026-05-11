import Link from "next/link";

import { CompanyContextCard } from "@/components/company/company-context-card";
import { CompanyFreshnessCard } from "@/components/company/company-freshness-card";
import { CompanyHeader } from "@/components/company/company-header";
import { CompanyRequestRefresh } from "@/components/company/company-request-refresh";
import { CompanyYearsListWarning } from "@/components/company/company-years-list-warning";
import {
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import {
  fetchCompanyFreshness,
  type CompanyInfo,
  type RefreshStatusItem,
} from "@/lib/api";
import { companyHasNonAnnualLocalOnly } from "@/lib/company-detail-handoff";
import { getCompanyFreshnessCopy } from "@/lib/company-refresh-state";
import { cn } from "@/lib/utils";

type CompanyNoDataPageProps = {
  company: CompanyInfo;
  /** Years endpoint failed; messaging relies on company-card metadata only */
  yearsListUnreachable?: boolean;
};

type ExpectationCardProps = {
  title: string;
  description: string;
};

function ExpectationCard({ title, description }: ExpectationCardProps) {
  return (
    <SurfaceCard tone="inset" padding="md" className="space-y-2">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      <p className="text-sm leading-6 text-muted-foreground">{description}</p>
    </SurfaceCard>
  );
}

export async function CompanyNoDataPage({
  company,
  yearsListUnreachable = false,
}: CompanyNoDataPageProps) {
  let initialFreshness: RefreshStatusItem | null = null;

  try {
    initialFreshness = await fetchCompanyFreshness(company.cd_cvm);
  } catch {
    initialFreshness = null;
  }

  const freshnessCopy = initialFreshness
    ? getCompanyFreshnessCopy(initialFreshness)
    : null;
  const lastOutcomeMessage = freshnessCopy?.latestResultDescription ?? null;

  const partialAnnualUnavailable = companyHasNonAnnualLocalOnly(company);

  return (
    <PageShell density="default">
      <CompanyHeader company={company} selectedYears={[]} />

      {yearsListUnreachable ? (
        <CompanyYearsListWarning context="no_data_shell" />
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 lg:gap-8">
        <div className="flex flex-col gap-6 lg:col-span-8">
          <SurfaceCard tone="default" padding="lg" className="space-y-6">
            <SectionHeading
              eyebrow={
                partialAnnualUnavailable
                  ? "Dados locais parciais"
                  : "Empresa cadastrada, historico pendente"
              }
              title={
                partialAnnualUnavailable
                  ? "Historico anual ainda nao encaixa nesta pagina"
                  : "No historical data available yet"
              }
              titleAs="h2"
              description={
                partialAnnualUnavailable
                  ? "Ha registros locais na base, mas nenhum ano fecha como demonstrativo anual completo (DFP) para KPIs e comparacao por ano. Isso e comum quando so ha trimestrais (ITR) ou falta de linhas obrigatorias no pacote anual. Solicite a atualizacao on-demand para tentar materializar o historico anual; o header da empresa permanece."
                  : "This company exists in the database but has no downloaded history. You can request the full historical update now; the page remains available while financial data is still missing."
              }
              descriptionClassName="max-w-3xl text-sm leading-7"
            />

            <Alert className="rounded-[1.5rem] border border-border/70 bg-muted/24 px-5 py-5">
              <AlertTitle>
                {partialAnnualUnavailable
                  ? "Sem janela anual legivel para KPIs"
                  : "No financial data available yet"}
              </AlertTitle>
              <AlertDescription>
                {partialAnnualUnavailable
                  ? "A leitura desta rota usa apenas anos com periodo anual (PERIOD_LABEL alinhado ao ano). Com dados so trimestrais ou incompletos, o painel lateral mostra o estado real do refresh e esta pagina continua aberta para nova tentativa."
                  : "A solicitacao on-demand busca uma serie anual processavel na CVM e atualiza o painel lateral com o status real da tentativa. Quando o processamento encontra historico suficiente, esta mesma rota passa a abrir a visao geral completa e as demonstracoes."}
                {freshnessCopy?.retryHint ? ` ${freshnessCopy.retryHint}` : ""}
              </AlertDescription>
            </Alert>

            <CompanyRequestRefresh
              cdCvm={company.cd_cvm}
              initialStatus={initialFreshness}
            />

            {lastOutcomeMessage ? (
              <Alert className="rounded-[1.5rem] border border-border/70 bg-background/82 px-5 py-5">
                <AlertTitle>Ultimo resultado conhecido</AlertTitle>
                <AlertDescription>{lastOutcomeMessage}</AlertDescription>
              </Alert>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-3">
              <ExpectationCard
                title="1. Acompanhe pelo painel lateral"
                description="O card de freshness continua visivel neste mesmo layout e concentra status, progresso, retry e mudanca de estado quando a leitura for concluida."
              />
              <ExpectationCard
                title="2. Quando a leitura funcionar"
                description="A rota troca para o dashboard real da companhia sem mudar de pagina, preservando o mesmo header, a mesma identidade visual e os mesmos links de contexto."
              />
              <ExpectationCard
                title="3. Quando nao houver historico suficiente"
                description="A pagina continua explicitando o resultado terminal de forma calma e reutilizavel, em vez de cair num estado generico ou contraditorio."
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/empresas"
                className={cn(buttonVariants({ variant: "ghost", size: "lg" }), "rounded-full px-5")}
              >
                Voltar para o diretorio
              </Link>
            </div>
          </SurfaceCard>
        </div>

        <div className="flex flex-col gap-4 lg:col-span-4">
          <CompanyFreshnessCard cdCvm={company.cd_cvm} showRequestAction={false} />
          <CompanyContextCard
            company={company}
            selectedYears={[]}
            availableYears={[]}
            historicoNaPaginaHint={
              partialAnnualUnavailable
                ? "Sem anos anuais locais (trimestral ou DFP incompleto)"
                : undefined
            }
          />
        </div>
      </div>
    </PageShell>
  );
}
