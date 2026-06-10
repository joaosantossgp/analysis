/**
 * Validate a Brazilian CNPJ number using standard check digit validation.
 */
export function validateCNPJ(value: string | null | undefined): boolean {
  if (!value) return false;

  // Remove known formatting characters
  const cleaned = value.replace(/[.\-/]/g, "").trim();

  // Cleaned value must be exactly 14 digits
  if (!/^\d{14}$/.test(cleaned)) {
    return false;
  }

  // Reject known invalid patterns (all same digits)
  if (/^(\d)\1{13}$/.test(cleaned)) {
    return false;
  }

  const digits = cleaned.split("").map(Number);

  // Validate first check digit
  const multipliers1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let sum1 = 0;
  for (let i = 0; i < 12; i++) {
    sum1 += digits[i] * multipliers1[i];
  }
  const rem1 = sum1 % 11;
  const expectedDigit1 = rem1 < 2 ? 0 : 11 - rem1;
  if (digits[12] !== expectedDigit1) {
    return false;
  }

  // Validate second check digit
  const multipliers2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let sum2 = 0;
  for (let i = 0; i < 13; i++) {
    sum2 += digits[i] * multipliers2[i];
  }
  const rem2 = sum2 % 11;
  const expectedDigit2 = rem2 < 2 ? 0 : 11 - rem2;
  if (digits[13] !== expectedDigit2) {
    return false;
  }

  return true;
}

/**
 * Format a Brazilian CNPJ number.
 * Standard format: 00.000.000/0000-00.
 * Returns "Not available" for invalid values.
 */
export function formatCNPJ(value: string | null | undefined): string {
  if (!value) return "Not available";

  // Clean known formatting characters
  const cleaned = value.replace(/[.\-/]/g, "").trim();

  // Validate check digits and digit count
  if (!validateCNPJ(cleaned)) {
    return "Not available";
  }

  return `${cleaned.slice(0, 2)}.${cleaned.slice(2, 5)}.${cleaned.slice(5, 8)}/${cleaned.slice(8, 12)}-${cleaned.slice(12, 14)}`;
}
