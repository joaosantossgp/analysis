"use client";

import { DownloadIcon, LoaderCircleIcon } from "lucide-react";

import { RefreshProgressAlert } from "@/components/company/refresh-progress-alert";
import { useCompanyRefreshMachine } from "@/components/company/use-company-refresh-machine";
import { Button } from "@/components/ui/button";
import { type RefreshStatusItem } from "@/lib/api";

type CompanyRequestRefreshProps = {
  cdCvm: number;
  initialStatus?: RefreshStatusItem | null;
};

export function CompanyRequestRefresh({
  cdCvm,
  initialStatus = null,
}: CompanyRequestRefreshProps) {
  const {
    view,
    showButtonSpinner,
    progressLabel,
    isManualStatusRefreshing,
    handleRequestRefresh,
    handleManualStatusRefresh,
  } = useCompanyRefreshMachine({ cdCvm, initialStatus });

  return (
    <div className="flex min-w-[18rem] flex-col gap-3 sm:max-w-xl">
      <Button
        type="button"
        variant="default"
        size="lg"
        className="w-fit rounded-full px-5"
        onClick={handleRequestRefresh}
        disabled={view.requestButtonDisabled}
      >
        {showButtonSpinner ? (
          <LoaderCircleIcon className="animate-spin" />
        ) : (
          <DownloadIcon className="size-4" />
        )}
        {view.requestButtonLabel}
      </Button>

      <RefreshProgressAlert
        view={view}
        progressLabel={progressLabel}
        isManualStatusRefreshing={isManualStatusRefreshing}
        onManualStatusRefresh={handleManualStatusRefresh}
        onRequestAgain={handleRequestRefresh}
      />
    </div>
  );
}
