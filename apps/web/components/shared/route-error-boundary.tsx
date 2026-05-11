"use client";

import { useEffect } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { getUserFacingErrorCopy } from "@/lib/api";

type RouteErrorBoundaryProps = {
  error: Error & { digest?: string };
  reset: () => void;
  contextLabel: string;
};

export function RouteErrorBoundary({
  error,
  reset,
  contextLabel,
}: RouteErrorBoundaryProps) {
  useEffect(() => {
    console.error(`[${contextLabel}]`, error);
  }, [error, contextLabel]);

  const copy = getUserFacingErrorCopy(error);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-12 sm:px-6">
      <div className="rounded-[1.25rem] border border-destructive/30 bg-destructive/5 p-6">
        <Alert variant="destructive-soft">
          <AlertTitle>{copy.title}</AlertTitle>
          <AlertDescription>{copy.message}</AlertDescription>
        </Alert>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Button
            size="lg"
            className="rounded-full px-5"
            onClick={() => reset()}
          >
            Tentar novamente
          </Button>
          {error.digest ? (
            <span className="font-mono text-xs text-muted-foreground">
              ref: {error.digest}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
