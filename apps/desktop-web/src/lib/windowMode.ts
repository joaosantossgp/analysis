export function isExcelMappingWindow(search: string): boolean {
  return new URLSearchParams(search).get("window") === "excel-mapping";
}
