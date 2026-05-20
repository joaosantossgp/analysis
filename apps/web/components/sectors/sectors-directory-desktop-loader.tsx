"use client";

import Link from "next/link";
import { useState } from "react";
import { useSearchParams } from "next/navigation";

import { SectorDirectoryList } from "@/components/sectors/sector-directory-list";
import { SectorHubTracker } from "@/components/sectors/sector-hub-tracker";
import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { useDesktopLoader } from "@/components/shared/use-desktop-loader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import type { SectorDirectory } from "@/lib/api";
import { bridgeFetchSectors } from "@/lib/desktop-bridge";
import { formatCompactInteger } from "@/lib/formatters";
import { cn } from "@/lib/utils";

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Nao foi possivel carregar os dados locais agora.";
}

type SectorsDirectoryDesktopLoaderProps = {
  initialGroupBy?: "sector" | "sub_sector";
};

function coerceGroupBy(value: string | null, fallback: "sector" | "sub_sector"): "sector" | "sub_sector" {
  return value === "sub_sector" || value === "sub-setor" ? "sub_sector" : fallback;
}

export function SectorsDirectoryDesktopLoader({
  initialGroupBy = "sector",
}: SectorsDirectoryDesktopLoaderProps) {
  const searchParams = useSearchParams();
  const groupBy = coerceGroupBy(searchParams.get("visao"), initialGroupBy);
  const [directory, setDirectory] = useState<SectorDirectory | null>(null);
  const [error, setError] = useState<string | null>(null);

  const bridgeReady = useDesktopLoader(
    `sectors-directory:${groupBy}`,
    async (isCancelled) => {
      try {
        const data = await bridgeFetchSectors(groupBy);
        if (isCancelled()) return;
        setDirectory(data);
        setError(null);
      } catch (err) {
        if (isCancelled()) return;
        setDirectory(null);
        setError(errorMessage(err));
      }
    },
  );

  const bridgeError =
    bridgeReady === "timeout"
      ? "Bridge local do desktop indisponivel. Reabra o aplicativo para carregar os dados locais."
      : error;

  if (bridgeError && !directory) {
    return (
      <PageShell density="relaxed">
        <SurfaceCard tone="hero" padding="hero" className="space-y-6">
          <SectionHeading
            eyebrow="PG-05 - Hub de setores"
            title="Leitura setorial temporariamente indisponivel"
            titleAs="h1"
            description="O hub de setores nao respondeu agora. O restante da navegacao publica continua disponivel."
          />
          <Alert variant="destructive-soft">
            <AlertTitle>Falha controlada do hub setorial</AlertTitle>
            <AlertDescription>{bridgeError}</AlertDescription>
          </Alert>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/setores"
              className={cn(buttonVariants({ size: "lg" }), "rounded-full px-5")}
            >
              Tentar novamente
            </Link>
            <Link
              href="/"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "rounded-full px-5",
              )}
            >
              Voltar para a home
            </Link>
          </div>
        </SurfaceCard>
      </PageShell>
    );
  }

  if (!directory) {
    return (
      <PageShell density="relaxed">
        <SurfaceCard tone="hero" padding="hero" className="animate-pulse space-y-4">
          <div className="h-10 w-64 rounded-full bg-muted/70" />
          <div className="h-24 rounded-2xl bg-muted/50" />
        </SurfaceCard>
      </PageShell>
    );
  }

  const totalCompanies = directory.items.reduce(
    (accumulator, item) => accumulator + item.company_count,
    0,
  );

  return (
    <PageShell density="default">
      <SectorHubTracker sectorCount={directory.items.length} />

      <SectionHeading
        eyebrow="PG-05 - Hub de setores"
        title={groupBy === "sub_sector" ? "Leitura por sub-setores GICS" : "Leitura por setores GICS"}
        titleAs="h1"
        description="A visao usa somente campos GICS persistidos. Empresas sem GICS aparecem separadas como sem classificacao."
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <InfoChip tone="muted">
              {formatCompactInteger(directory.items.length)} grupos
            </InfoChip>
            <InfoChip tone="muted">
              {formatCompactInteger(totalCompanies)} empresas somadas
            </InfoChip>
          </div>
        }
      />

      <SurfaceCard tone="subtle" padding="lg" className="space-y-4">
        <div className="flex flex-wrap gap-2">
          <Link
            href="/setores?visao=sector"
            className={cn(
              buttonVariants({ variant: groupBy === "sector" ? "default" : "outline", size: "sm" }),
              "rounded-full px-4",
            )}
          >
            Setores GICS
          </Link>
          <Link
            href="/setores?visao=sub_sector"
            className={cn(
              buttonVariants({ variant: groupBy === "sub_sector" ? "default" : "outline", size: "sm" }),
              "rounded-full px-4",
            )}
          >
            Sub-setores GICS
          </Link>
        </div>
        <p className="text-sm leading-7 text-muted-foreground">
          Cada card mostra contagem e empresas do grupo. Metricas financeiras
          aparecem apenas quando ha dados anuais locais.
        </p>
      </SurfaceCard>

      <SectorDirectoryList items={directory.items} groupBy={groupBy} />
    </PageShell>
  );
}
