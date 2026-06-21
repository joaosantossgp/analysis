/**
 * Sanitizes a filename to prevent path traversal or invalid characters.
 */
export function sanitizeFilename(filename: string): string {
  // Allow alphanumeric, underscores, hyphens, and dots. Replace others with underscores.
  const cleaned = filename.replace(/[^a-zA-Z0-9_\-.]/g, "_");
  // Remove multiple consecutive underscores/dots
  return cleaned.replace(/_+/g, "_").replace(/\.+/g, ".").trim();
}

/**
 * Escapes a cell value for CSV formatting.
 */
export function escapeCsvCell(val: string | number | null | undefined): string {
  if (val === null || val === undefined) {
    return "";
  }
  const str = String(val);
  // If the cell contains quotes, commas, or newlines, wrap in quotes and escape internal quotes
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function downloadCsvFile(options: {
  filename: string;
  headers: string[];
  rows: Array<Array<string | number | null | undefined>>;
}): void {
  const { filename, headers, rows } = options;
  if (!headers.length) return;

  // Build CSV content with escaping
  const csvHeaders = headers.map(escapeCsvCell).join(",");
  const csvRows = rows.map((row) => row.map(escapeCsvCell).join(","));
  
  // UTF-8 BOM for Microsoft Excel compatibility
  const csvContent = "\uFEFF" + [csvHeaders, ...csvRows].join("\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  
  // Ensure the filename ends with .csv and is sanitized
  const baseName = filename.endsWith(".csv") ? filename.slice(0, -4) : filename;
  const safeFilename = `${sanitizeFilename(baseName)}.csv`;

  link.setAttribute("href", url);
  link.setAttribute("download", safeFilename);
  document.body.appendChild(link);
  
  try {
    link.click();
  } catch (err) {
    console.error("CSV download failed", err);
  } finally {
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}
