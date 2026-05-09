import Link from "next/link";
import type { Metadata } from "next";

import { SectorDirectoryList } from "@/components/sectors/sector-directory-list";
import { SectorHubTracker } from "@/components/sectors/sector-hub-tracker";
import { SectorsDirectoryDesktopLoader } from "@/components/sectors/sectors-directory-desktop-loader";
import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { ApiUnavailableState } from "@/components/ui/api-unavailable-state";
import { buttonVariants } from "@/components/ui/button";
import { formatCompactInteger } from "@/lib/formatters";
import { isDesktopServerMode } from "@/lib/desktop-mode";
import { fetchSectorDirectory, SECTOR_DIRECTORY_NO_STORE_READ } from "@/lib/api";
import { loadSectorsPageData } from "@/lib/sectors-page-data";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Setores",
  description:
    "Hub setorial da V2 web com leitura agregada por setor, contagem de empresas e snapshots anuais.",
};

// Desktop mode is decided at runtime via ANALISYS_DESKTOP_MODE.
// Force dynamic rendering so this route does not get pre-rendered
// with the web/API branch during build.
export const dynamic = "force-dynamic";

export default async function SetoresPage() {
  if (isDesktopServerMode()) {
    return <SectorsDirectoryDesktopLoader />;
  }

  const { directory, directoryError } = await loadSectorsPageData({
    fetchDirectory: () =>
      fetchSectorDirectory({ request: SECTOR_DIRECTORY_NO_STORE_READ }),
  });

  if (!directory) {
    return (
      <PageShell density="relaxed">
        <SurfaceCard tone="hero" padding="hero" className="space-y-6">
          <SectionHeading
            eyebrow="PG-05 - Hub de setores"
            title="Leitura setorial temporariamente indisponivel"
            titleAs="h1"
            description="O hub de setores nao respondeu agora. O restante da navegacao publica continua disponivel."
          />
          <ApiUnavailableState
            title="Falha controlada do hub setorial"
            description={
              directoryError ??
              "Nao foi possivel carregar os setores agora. Tente novamente em instantes."
            }
            retryHref="/setores"
            retryClassName="rounded-full px-5"
          />
          <div className="flex flex-wrap gap-3">
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
