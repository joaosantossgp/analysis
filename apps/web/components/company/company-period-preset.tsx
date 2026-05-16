"use client";

import { startTransition, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { CalendarIcon } from "lucide-react";

import { Calendar } from "@/components/calendar";
import { CompanyHelpTip } from "@/components/company/company-help-tip";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { resolveCompanyPeriodRange } from "@/lib/company-period-range";
import { mergeSearchParams, serializeYears } from "@/lib/search-params";
import { track } from "@/lib/track";

type PresetValue = "3a" | "5a" | "all" | "custom";

type CompanyPeriodPresetProps = {
  pathname: string;
  availableYears: number[];
  selectedYears: number[];
  variant?: "full" | "custom-only";
};

const PRESET_OPTIONS: Array<{
  value: PresetValue;
  label: string;
  minYears?: number;
}> = [
  { value: "3a", label: "3A", minYears: 3 },
  { value: "5a", label: "5A", minYears: 5 },
  { value: "all", label: "Todos" },
  { value: "custom", label: "Personalizado" },
];

function arraysEqual(left: number[], right: number[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((value, index) => value === right[index]);
}

function getLastNYears(years: number[], count: number): number[] {
  return years.slice(Math.max(0, years.length - count));
}

function detectPreset(
  availableYears: number[],
  selectedYears: number[],
): PresetValue {
  if (arraysEqual(availableYears, selectedYears)) {
    return "all";
  }

  if (
    availableYears.length >= 3 &&
    arraysEqual(getLastNYears(availableYears, 3), selectedYears)
  ) {
    return "3a";
  }

  if (
    availableYears.length >= 5 &&
    arraysEqual(getLastNYears(availableYears, 5), selectedYears)
  ) {
    return "5a";
  }

  return "custom";
}

function resolvePresetYears(
  preset: Exclude<PresetValue, "custom">,
  availableYears: number[],
): number[] {
  switch (preset) {
    case "3a":
      return getLastNYears(availableYears, 3);
    case "5a":
      return getLastNYears(availableYears, 5);
    case "all":
      return availableYears;
  }
}

function getPeriodDate(value: string, fallbackYear: number | undefined): Date | undefined {
  const year = Number(value.trim() || fallbackYear);

  if (!Number.isInteger(year)) {
    return undefined;
  }

  return new Date(year, 0, 1);
}

function getCalendarBoundary(
  availableYears: number[],
  fallback: "start" | "end",
): Date | undefined {
  const year =
    fallback === "start" ? availableYears[0] : availableYears.at(-1);

  return year === undefined ? undefined : new Date(year, 0, 1);
}

type CustomCompanyPeriodRangeProps = {
  pathname: string;
  availableYears: number[];
  selectedYears: number[];
};

function CustomCompanyPeriodRange({
  pathname,
  availableYears,
  selectedYears,
}: CustomCompanyPeriodRangeProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [fromInput, setFromInput] = useState(String(selectedYears[0] ?? ""));
  const [toInput, setToInput] = useState(String(selectedYears.at(-1) ?? ""));
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const resolution = resolveCompanyPeriodRange(
      availableYears,
      fromInput,
      toInput,
    );

    if (!resolution.ok) {
      setErrorMessage(resolution.error);
      return;
    }

    setErrorMessage(null);

    if (arraysEqual(resolution.years, selectedYears)) {
      return;
    }

    const query = mergeSearchParams(searchParams.toString(), {
      anos: serializeYears(resolution.years),
    });

    track("company_years_changed", {
      years: resolution.years.join(","),
      preset: "custom",
      range_from: fromInput.trim(),
      range_to: toInput.trim(),
    });

    startTransition(() => {
      router.push(`${pathname}?${query}`);
    });
  }

  return (
    <form
      className="rounded-[1.25rem] border border-border/60 bg-muted/20 p-4"
      onSubmit={handleSubmit}
    >
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            De:
          </span>
          <PeriodCalendarPicker
            ariaLabel="Selecionar período inicial"
            availableYears={availableYears}
            value={fromInput}
            fallbackYear={selectedYears[0]}
            invalid={Boolean(errorMessage)}
            onChange={(year) => {
              setFromInput(String(year));
              if (errorMessage) {
                setErrorMessage(null);
              }
            }}
          />
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            Até:
          </span>
          <PeriodCalendarPicker
            ariaLabel="Selecionar período final"
            availableYears={availableYears}
            value={toInput}
            fallbackYear={selectedYears.at(-1)}
            invalid={Boolean(errorMessage)}
            onChange={(year) => {
              setToInput(String(year));
              if (errorMessage) {
                setErrorMessage(null);
              }
            }}
          />
        </div>

        <Button
          type="submit"
          size="sm"
          variant="secondary"
          className="h-10 rounded-full px-4"
        >
          Aplicar
        </Button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="min-w-0 flex-1 leading-5 text-muted-foreground">
          Selecione uma data; o filtro usa o ano correspondente.
        </span>
        <CompanyHelpTip>
          A página continua usando os anos cobertos pelo intervalo informado.
        </CompanyHelpTip>
        {errorMessage ? (
          <p className="w-full text-destructive md:w-auto md:ml-auto" role="alert">
            {errorMessage}
          </p>
        ) : null}
      </div>
    </form>
  );
}

type PeriodCalendarPickerProps = {
  ariaLabel: string;
  availableYears: number[];
  fallbackYear: number | undefined;
  invalid: boolean;
  value: string;
  onChange: (year: number) => void;
};

function PeriodCalendarPicker({
  ariaLabel,
  availableYears,
  fallbackYear,
  invalid,
  value,
  onChange,
}: PeriodCalendarPickerProps) {
  const selectedDate = getPeriodDate(value, fallbackYear);
  const startMonth = getCalendarBoundary(availableYears, "start");
  const endMonth = getCalendarBoundary(availableYears, "end");

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          aria-invalid={invalid ? "true" : undefined}
          aria-label={`${ariaLabel}: ${value || "ano não selecionado"}`}
          className="h-10 w-full justify-between rounded-full border-border/60 bg-background px-3 font-normal"
        >
          <span>{value || "Selecionar ano"}</span>
          <CalendarIcon data-icon="inline-end" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-3">
        <Calendar
          mode="single"
          selected={selectedDate}
          defaultMonth={selectedDate ?? startMonth}
          startMonth={startMonth}
          endMonth={endMonth}
          captionLayout="dropdown"
          disabled={(date) => !availableYears.includes(date.getFullYear())}
          onSelect={(date) => {
            if (date) {
              onChange(date.getFullYear());
            }
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

export function CompanyPeriodPreset({
  pathname,
  availableYears,
  selectedYears,
  variant = "full",
}: CompanyPeriodPresetProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const derivedPreset = detectPreset(availableYears, selectedYears);
  const [customLocked, setCustomLocked] = useState(derivedPreset === "custom");
  const activePreset: PresetValue = customLocked ? "custom" : derivedPreset;

  function applyPreset(nextPreset: PresetValue) {
    if (nextPreset === "custom") {
      setCustomLocked(true);
      return;
    }

    setCustomLocked(false);
    const nextYears = resolvePresetYears(nextPreset, availableYears);

    if (arraysEqual(nextYears, selectedYears)) {
      return;
    }

    const query = mergeSearchParams(searchParams.toString(), {
      anos: serializeYears(nextYears),
    });

    track("company_years_changed", {
      years: nextYears.join(","),
      preset: nextPreset,
    });

    startTransition(() => {
      router.push(`${pathname}?${query}`);
    });
  }

  if (variant === "custom-only") {
    return (
      <CustomCompanyPeriodRange
        key={selectedYears.join(",")}
        pathname={pathname}
        availableYears={availableYears}
        selectedYears={selectedYears}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <span className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
          Período
        </span>
        <div className="flex flex-wrap gap-2">
          {PRESET_OPTIONS.map((option) => {
            const active = option.value === activePreset;
            const disabled =
              option.minYears !== undefined &&
              availableYears.length < option.minYears;

            return (
              <Button
                key={option.value}
                type="button"
                variant={active ? "secondary" : "outline"}
                size="sm"
                className="rounded-full px-4"
                disabled={disabled}
                onClick={() => applyPreset(option.value)}
              >
                {option.label}
              </Button>
            );
          })}
        </div>
      </div>

      {activePreset === "custom" ? (
        <div className="px-1">
          <CustomCompanyPeriodRange
            key={selectedYears.join(",")}
            pathname={pathname}
            availableYears={availableYears}
            selectedYears={selectedYears}
          />
        </div>
      ) : null}
    </div>
  );
}
