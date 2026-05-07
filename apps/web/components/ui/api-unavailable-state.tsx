"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from "next/link";

type ApiUnavailableStateProps = {
  title: string;
  description: string;
  onRetry?: () => void;
  retryHref?: string;
  retryClassName?: string;
};

export function ApiUnavailableState({
  title,
  description,
  onRetry,
  retryHref,
  retryClassName,
}: ApiUnavailableStateProps) {
  return (
    <div className="space-y-3">
      <Alert variant="destructive-soft">
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{description}</AlertDescription>
      </Alert>
      {onRetry ? (
        <Button type="button" onClick={onRetry} className={retryClassName}>
          Tentar novamente
        </Button>
      ) : retryHref ? (
        <Link href={retryHref} className={cn(buttonVariants(), "inline-flex", retryClassName)}>
          Tentar novamente
        </Link>
      ) : null}
    </div>
  );
}
