"use client";

import { RouteErrorBoundary } from "@/components/shared/route-error-boundary";

export default function SetoresError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteErrorBoundary {...props} contextLabel="setores" />;
}
