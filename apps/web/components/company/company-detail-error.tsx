import Link from "next/link";

import {
  InfoChip,
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CompanyDetailErrorPage({
  message,
}: {
  message: string;
}) {
  return (
    <PageShell density="relaxed" className="max-w-4xl">
      <SurfaceCard tone="default" padding="lg" className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <InfoChip tone="brand">Detalhe da companhia</InfoChip>
        </div>
        <SectionHeading
          title="Detalhes indisponiveis"
          titleAs="h1"
          description="Nao foi possivel carregar os dados desta companhia agora."
        />
        <Alert variant="destructive-soft">
          <AlertTitle>Falha na leitura detalhada</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
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
