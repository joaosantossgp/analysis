"use client";

import { DownloadIcon, LoaderCircleIcon } from "lucide-react";
import { useMemo, useState, type ChangeEvent } from "react";

import { RefreshProgressAlert } from "@/components/company/refresh-progress-alert";
import { useCompanyRefreshMachine } from "@/components/company/use-company-refresh-machine";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type CompanyDownloadPeriodProps = {
  cdCvm: number;
};

const MIN_YEAR = 2010;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function CompanyDownloadPeriod({ cdCvm }: CompanyDownloadPeriodProps) {
  const maxYear = useMemo(() => new Date().getFullYear(), []);
  const [startYearInput, setStartYearInput] = useState<string>(String(MIN_YEAR));
  const [endYearInput, setEndYearInput] = useState<string>(String(maxYear));

  const startYear = Number(startYearInput);
  const endYear = Number(endYearInput);
  const rangeValid =
    Number.isInteger(startYear) &&
    Number.isInteger(endYear) &&
    startYear >= MIN_YEAR &&
    endYear <= maxYear &&
    startYear <= endYear;

  const range = rangeValid ? { startYear, endYear } : undefined;

  const {
    view,
    showButtonSpinner,
    progressLabel,
    isManualStatusRefreshing,
    handleRequestRefresh,
    handleManualStatusRefresh,
  } = useCompanyRefreshMachine({ cdCvm, range });

  function handleYearChange(
    setter: (value: string) => void,
  ): (event: ChangeEvent<HTMLInputElement>) => void {
    return (event) => {
      const raw = event.target.value.trim();
      if (raw === "") {
        setter("");
        return;
      }
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) {
        return;
      }
      setter(String(Math.trunc(parsed)));
    };
  }

  function handleStartBlur(): void {
    if (startYearInput === "") {
      setStartYearInput(String(MIN_YEAR));
      return;
    }
    setStartYearInput(String(clamp(startYear, MIN_YEAR, maxYear)));
  }

  function handleEndBlur(): void {
    if (endYearInput === "") {
      setEndYearInput(String(maxYear));
      return;
    }
    setEndYearInput(String(clamp(endYear, MIN_YEAR, maxYear)));
  }

  const periodLabel = rangeValid
    ? startYear === endYear
      ? `${startYear}`
      : `${startYear}–${endYear}`
    : "—";

  return (
    <div className="flex min-w-[18rem] flex-col gap-3 sm:max-w-xl">
      <div className="flex flex-wrap items-end gap-3 rounded-[1.25rem] border border-border/60 bg-muted/20 p-4">
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`download-start-${cdCvm}`}
            className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground"
          >
            Baixar de
          </label>
          <Input
            id={`download-start-${cdCvm}`}
            type="number"
            inputMode="numeric"
            min={MIN_YEAR}
            max={maxYear}
            step={1}
            value={startYearInput}
            onChange={handleYearChange(setStartYearInput)}
            onBlur={handleStartBlur}
            className="h-10 w-28 rounded-full bg-background text-center"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor={`download-end-${cdCvm}`}
            className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground"
          >
            Até
          </label>
          <Input
            id={`download-end-${cdCvm}`}
            type="number"
            inputMode="numeric"
            min={MIN_YEAR}
            max={maxYear}
            step={1}
            value={endYearInput}
            onChange={handleYearChange(setEndYearInput)}
            onBlur={handleEndBlur}
            className="h-10 w-28 rounded-full bg-background text-center"
          />
        </div>

        <Button
          type="button"
          variant="default"
          size="sm"
          className="h-10 rounded-full px-4"
          onClick={handleRequestRefresh}
          disabled={view.requestButtonDisabled || !rangeValid}
        >
          {showButtonSpinner ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : (
            <DownloadIcon className="size-4" />
          )}
          Baixar período {periodLabel}
        </Button>
      </div>

      {!rangeValid ? (
        <p className="px-1 text-xs text-destructive" role="alert">
          Informe um intervalo válido entre {MIN_YEAR} e {maxYear}.
        </p>
      ) : null}

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
