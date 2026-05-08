import { NextRequest } from "next/server";

import { proxyJsonRoute } from "@/lib/api-route-proxy";

export async function GET(request: NextRequest) {
  const query = new URLSearchParams();
  const rawQ = request.nextUrl.searchParams.get("q");
  const rawLimit = request.nextUrl.searchParams.get("limit");
  const rawReadyOnly = request.nextUrl.searchParams.get("ready_only");

  if (rawQ) {
    query.set("q", rawQ);
  }

  if (rawLimit) {
    query.set("limit", rawLimit);
  }

  if (rawReadyOnly === "1" || rawReadyOnly?.toLowerCase() === "true") {
    query.set("ready_only", "true");
  }

  return proxyJsonRoute({
    upstreamPath: `/companies/suggestions${query.toString() ? `?${query.toString()}` : ""}`,
    networkMessage: "Nao foi possivel conectar a API da V2.",
    fallbackMessage: (status) =>
      status >= 500
        ? "A API da V2 nao conseguiu retornar sugestoes agora."
        : "Nao foi possivel buscar sugestoes de empresas agora.",
    invalidResponseMessage:
      "A API da V2 retornou um corpo invalido para as sugestoes.",
  });
}
