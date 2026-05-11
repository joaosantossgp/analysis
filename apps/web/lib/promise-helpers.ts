export function settledOr<T, F>(
  result: PromiseSettledResult<T>,
  fallback: F,
): T | F {
  return result.status === "fulfilled" ? result.value : fallback;
}

export function settledReason<T, R>(
  result: PromiseSettledResult<T>,
  mapReason: (reason: unknown) => R,
): R | null {
  return result.status === "rejected" ? mapReason(result.reason) : null;
}
