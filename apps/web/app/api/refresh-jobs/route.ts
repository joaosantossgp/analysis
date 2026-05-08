import { proxyJsonRoute } from "@/lib/api-route-proxy";

export async function GET() {
  return proxyJsonRoute({
    upstreamPath: "/refresh/jobs",
    fallbackMessage: "Nao foi possivel listar os batch jobs ativos.",
  });
}
