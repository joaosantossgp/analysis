import Link from "next/link";
import { ArrowRightIcon, LayersIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function CtaSection() {
  return (
    <section className="w-full max-w-5xl mx-auto">
      <div
        className={cn(
          "relative overflow-hidden rounded-[1.75rem] border border-border/60",
          "bg-gradient-to-br from-card via-card to-primary/5",
          "px-8 py-12 sm:px-12 sm:py-14"
        )}
      >
        <div className="relative flex flex-col items-center gap-8 text-center lg:flex-row lg:justify-between lg:text-left">
          <div className="max-w-lg">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/8 px-3 py-1.5">
              <LayersIcon className="size-4 text-primary" />
              <span className="text-xs font-medium text-primary">Classificacao GICS</span>
            </div>
            <h2 className="font-heading text-[clamp(1.5rem,4vw,2rem)] font-medium tracking-[-0.03em] text-foreground">
              Explore empresas por setor e sub-setor
            </h2>
            <p className="mt-3 text-base leading-relaxed text-muted-foreground">
              Use a estrutura GICS para filtrar companhias, localizar pares
              naturais e abrir a pagina de qualquer empresa cadastrada.
            </p>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <Link
              href="/setores"
              className={cn(
                buttonVariants({ size: "lg" }),
                "rounded-full px-6 gap-2"
              )}
            >
              Abrir setores
              <ArrowRightIcon className="size-4" />
            </Link>
            <Link
              href="/empresas"
              className={cn(
                buttonVariants({ variant: "outline", size: "lg" }),
                "rounded-full px-6"
              )}
            >
              Ver diretorio
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
