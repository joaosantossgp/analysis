import Link from "next/link";
import type { ReactNode } from "react";

import {
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ProblemStateAction = {
  href: string;
  label: ReactNode;
  variant?: "default" | "outline" | "secondary" | "ghost" | "destructive" | "link";
  className?: string;
};

type ProblemStateCardProps = {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  alertTitle?: ReactNode;
  alertDescription?: ReactNode;
  actions?: ProblemStateAction[];
  shellClassName?: string;
  cardClassName?: string;
  centered?: boolean;
  tone?: "default" | "subtle" | "muted" | "hero" | "inset";
  padding?: "none" | "md" | "lg" | "hero";
};

export function ProblemStateCard({
  eyebrow,
  title,
  description,
  alertTitle,
  alertDescription,
  actions = [],
  shellClassName,
  cardClassName,
  centered = false,
  tone = "hero",
  padding = "hero",
}: ProblemStateCardProps) {
  return (
    <PageShell
      density="relaxed"
      className={cn(centered ? "max-w-4xl text-center" : "max-w-4xl", shellClassName)}
    >
      <SurfaceCard
        tone={tone}
        padding={padding}
        className={cn(
          "space-y-6",
          centered ? "items-center text-center" : null,
          cardClassName,
        )}
      >
        <SectionHeading
          eyebrow={eyebrow}
          title={title}
          titleAs="h1"
          description={description}
          bodyClassName={centered ? "mx-auto max-w-2xl" : undefined}
          descriptionClassName={centered ? "mx-auto" : undefined}
        />
        {alertTitle || alertDescription ? (
          <Alert variant="destructive-soft">
            {alertTitle ? <AlertTitle>{alertTitle}</AlertTitle> : null}
            {alertDescription ? (
              <AlertDescription>{alertDescription}</AlertDescription>
            ) : null}
          </Alert>
        ) : null}
        {actions.length > 0 ? (
          <div className={cn("flex flex-wrap gap-3", centered ? "justify-center" : null)}>
            {actions.map((action) => (
              <Link
                key={`${action.href}:${String(action.label)}`}
                href={action.href}
                className={cn(
                  buttonVariants({ variant: action.variant, size: "lg" }),
                  "rounded-full px-5",
                  action.className,
                )}
              >
                {action.label}
              </Link>
            ))}
          </div>
        ) : null}
      </SurfaceCard>
    </PageShell>
  );
}
