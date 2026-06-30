type MmgdPeriodRow = {
  period: string;
  mmgd_projects_count: number | null;
};

export function getMmgdDetailMonths(series: MmgdPeriodRow[]): string[] {
  return [...series]
    .filter((row) => (row.mmgd_projects_count ?? 0) > 0)
    .map((row) => row.period)
    .sort((a, b) => b.localeCompare(a));
}

export function resolveMmgdDetailMonth(
  series: MmgdPeriodRow[],
  selectedMonth: string | null,
): string | null {
  const months = getMmgdDetailMonths(series);
  if (selectedMonth && months.includes(selectedMonth)) return selectedMonth;
  return months[0] ?? null;
}

export function resolveMmgdPageOffset({
  requestedOffset,
  limit,
  totalRows,
}: {
  requestedOffset: number;
  limit: number;
  totalRows: number;
}): number {
  const safeLimit = Math.max(1, Number.isFinite(limit) ? Math.floor(limit) : 50);
  const safeTotal = Math.max(0, Number.isFinite(totalRows) ? Math.floor(totalRows) : 0);
  const maxOffset = safeTotal > 0 ? Math.floor((safeTotal - 1) / safeLimit) * safeLimit : 0;
  const offset = Math.max(0, Number.isFinite(requestedOffset) ? Math.floor(requestedOffset) : 0);
  return Math.min(offset, maxOffset);
}
