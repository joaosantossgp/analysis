import { NextRequest } from "next/server";

import { proxyJsonRoute } from "@/lib/api-route-proxy";

export async function GET(request: NextRequest) {
  return proxyJsonRoute({
    upstreamPath: `/base-health${request.nextUrl.search}`,
    fallbackMessage: (status) =>
      status >= 500
        ? "A API nao conseguiu carregar a saude da base."
        : "Nao foi possivel carregar a saude da base.",
  });
}
