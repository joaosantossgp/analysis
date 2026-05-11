import type { getCompanyAvailability } from "@/lib/company-discovery";

type AvailabilityKind = ReturnType<typeof getCompanyAvailability>["kind"];

export function getAvailabilityBadgeClassName(kind: AvailabilityKind): string {
  switch (kind) {
    case "ready":
      return "border-emerald-500/20 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300";
    case "requestable":
      return "border-primary/20 bg-primary/8 text-primary/80";
    case "low_signal":
      return "border-amber-500/24 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "stalled":
      return "border-destructive/25 bg-destructive/8 text-destructive";
  }
}
