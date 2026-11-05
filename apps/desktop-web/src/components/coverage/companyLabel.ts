

export function formatB3OrCvm(company: { ticker_b3?: string | null; cd_cvm?: number | string | null }) {
  const ticker = String(company.ticker_b3 || "").trim();
  if (ticker) return ticker;
  return company.cd_cvm ? `CVM ${company.cd_cvm}` : "CVM n/a";
}
