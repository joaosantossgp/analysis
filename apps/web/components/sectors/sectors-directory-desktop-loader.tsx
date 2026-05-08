"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { SectorDirectoryList } from "@/components/sectors/sector-directory-list";
import { SectorHubTracker } from "@/components/sectors/sector-hub-tracker";
import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
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

export function SectorsDirectoryDesktopLoader() {
  const [directory, setDirectory] = useState<SectorDirectory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bridgeReady = useDesktopBridgeReady("sectors-directory");

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function load() {
      if (cancelled) return;

      try {
        const data = await bridgeFetchSectors();
        if (!cancelled) {
          setDirectory(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setDirectory(null);
          setError(errorMessage(err));
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [bridgeReady]);

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
        title="Leitura por setores"
        titleAs="h1"
        description="Entre por cadeias produtivas e clusters analiticos para sair da navegacao empresa a empresa quando o problema e tematico."
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <InfoChip tone="muted">
              {formatCompactInteger(directory.items.length)} setores
            </InfoChip>
            <InfoChip tone="muted">
              {formatCompactInteger(totalCompanies)} empresas somadas
            </InfoChip>
          </div>
        }
      />

      <SurfaceCard tone="subtle" padding="lg" className="space-y-4">
        <p className="text-sm leading-7 text-muted-foreground">
          Cada card entrega um snapshot do ano mais recente disponivel no setor,
          mantendo metricas ausentes como lacunas explicitas em vez de
          preenchimento artificial.
        </p>
      </SurfaceCard>

      <SectorDirectoryList items={directory.items} />
    </PageShell>
  );
}
