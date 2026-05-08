"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";

const CompanyDetailBody = dynamic(() =>
  import("@/components/company/company-detail-body").then((mod) => mod.CompanyDetailBody),
);
import { CompanyDetailErrorPage } from "@/components/company/company-detail-error";
import { CompanyNoDataPage } from "@/components/company/company-no-data";
import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
import { buttonVariants } from "@/components/ui/button";
import { getReadableCompanyYears } from "@/lib/company-detail-handoff";
import type { CompanyInfo, KPIBundle, StatementMatrix } from "@/lib/api";
import {
  bridgeFetchCompanyInfo,
  bridgeFetchCompanyKpis,
  bridgeFetchCompanyStatement,
  bridgeFetchCompanyYears,
} from "@/lib/desktop-bridge";
import {
  coerceDetailTab,
  coerceStatement,
  getFirstParam,
  normalizeSelectedYears,
} from "@/lib/search-params";
import { cn } from "@/lib/utils";

type CompanyDetailDesktopLoaderProps = {
  cdCvm: number;
  searchParams: Record<string, string | string[] | undefined>;
};

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Nao foi possivel carregar os dados locais agora.";
}

function isYearsNotFoundError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: string }).code === "not_found"
  );
}

function CompanyDetailLoadingState() {
  return (
    <PageShell density="relaxed" className="max-w-4xl">
      <SurfaceCard tone="default" padding="lg" className="space-y-4 animate-pulse">
        <div className="h-7 w-56 rounded-full bg-muted/70" />
        <div className="h-40 rounded-2xl bg-muted/50" />
        <div className="h-32 rounded-2xl bg-muted/40" />
      </SurfaceCard>
    </PageShell>
  );
}

function CompanyDetailNotFoundCard() {
  return (
    <PageShell density="relaxed" className="max-w-4xl">
      <SurfaceCard tone="default" padding="lg" className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <InfoChip tone="brand">Detalhe da companhia</InfoChip>
        </div>
        <SectionHeading
          title="Empresa nao encontrada"
          titleAs="h1"
          description="Nao ha registro local para este codigo CVM na base empacotada."
        />
        <Link
          href="/empresas"
          className={cn(
            buttonVariants({ variant: "outline", size: "lg" }),
            "w-fit rounded-full px-5",
          )}
        >
          Voltar para o diretorio
        </Link>
      </SurfaceCard>
    </PageShell>
  );
}

export function CompanyDetailDesktopLoader({
  cdCvm,
  searchParams,
}: CompanyDetailDesktopLoaderProps) {
  const aba = getFirstParam(searchParams.aba);
  const stmt = getFirstParam(searchParams.stmt);
  const anos = getFirstParam(searchParams.anos);
  const loadKey = `${cdCvm}|${aba ?? ""}|${stmt ?? ""}|${anos ?? ""}`;
  const bridgeReady = useDesktopBridgeReady(loadKey);

  const [state, setState] = useState<{
    key: string;
    phase:
      | "loading"
      | "bridge_timeout"
      | "error"
      | "not_found"
      | "no_data"
      | "ready";
    errorMessage?: string;
    company?: CompanyInfo;
    readableYears?: number[];
    currentTab?: "visao-geral" | "demonstracoes";
    currentStatement?: string;
    selectedYears?: number[];
    bundle?: KPIBundle | null;
    statement?: StatementMatrix | null;
    contentError?: string | null;
  } | null>(null);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function run() {
      if (cancelled) return;

      setState({ key: loadKey, phase: "loading" });

      try {
        const company = await bridgeFetchCompanyInfo(cdCvm);
        if (cancelled) return;

        if (!company) {
          setState({ key: loadKey, phase: "not_found" });
          return;
        }

        let availableYears: number[] = [];
        try {
          availableYears = await bridgeFetchCompanyYears(cdCvm);
        } catch (error) {
          if (isYearsNotFoundError(error)) {
            availableYears = [];
          } else {
            throw error;
          }
        }

        if (cancelled) return;

        const readableYears = getReadableCompanyYears(company, availableYears);

        if (readableYears.length === 0) {
          setState({ key: loadKey, phase: "no_data", company });
          return;
        }

        const currentTab = coerceDetailTab(aba);
        const currentStatement = coerceStatement(stmt);
        const selectedYears = normalizeSelectedYears(readableYears, anos);

        let bundle: KPIBundle | null = null;
        let statement: StatementMatrix | null = null;
        let contentError: string | null = null;

        if (currentTab === "visao-geral") {
          try {
            bundle = await bridgeFetchCompanyKpis(cdCvm, selectedYears);
          } catch (error) {
            contentError = errorMessage(error);
          }
        } else {
          try {
            statement = await bridgeFetchCompanyStatement(
              cdCvm,
              selectedYears,
              currentStatement,
            );
          } catch (error) {
            contentError = errorMessage(error);
          }
        }

        if (cancelled) return;

        setState({
          key: loadKey,
          phase: "ready",
          company,
          readableYears,
          currentTab,
          currentStatement,
          selectedYears,
          bundle,
          statement,
          contentError,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          key: loadKey,
          phase: "error",
          errorMessage: errorMessage(error),
        });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [bridgeReady, loadKey, cdCvm, aba, stmt, anos]);

  if (bridgeReady === "timeout" && (!state || state.key !== loadKey)) {
    return (
      <CompanyDetailErrorPage message="Bridge local do desktop indisponivel. Reabra o aplicativo para carregar os dados locais." />
    );
  }

  if (!state || state.key !== loadKey) {
    return <CompanyDetailLoadingState />;
  }

  if (state.phase === "loading") {
    return <CompanyDetailLoadingState />;
  }

  if (state.phase === "bridge_timeout" || state.phase === "error") {
    return (
      <CompanyDetailErrorPage message={state.errorMessage ?? "Erro desconhecido."} />
    );
  }

  if (state.phase === "not_found") {
    return <CompanyDetailNotFoundCard />;
  }

  if (state.phase === "no_data" && state.company) {
    return <CompanyNoDataPage company={state.company} />;
  }

  if (
    state.phase === "ready" &&
    state.company &&
    state.readableYears &&
    state.currentTab !== undefined &&
    state.currentStatement !== undefined &&
    state.selectedYears
  ) {
    const pathname = `/empresas/${cdCvm}`;
    return (
      <CompanyDetailBody
        company={state.company}
        pathname={pathname}
        currentTab={state.currentTab}
        currentStatement={state.currentStatement}
        readableYears={state.readableYears}
        selectedYears={state.selectedYears}
        bundle={state.bundle ?? null}
        statement={state.statement ?? null}
        contentError={state.contentError ?? null}
      />
    );
  }

  return <CompanyDetailLoadingState />;
}
