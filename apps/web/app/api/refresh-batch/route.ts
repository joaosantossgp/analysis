import { proxyJsonRoute } from "@/lib/api-route-proxy";

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    body = {};
  }

  return proxyJsonRoute({
    upstreamPath: "/refresh/batch",
    method: "POST",
    body,
    fallbackMessage: (status) =>
      status === 429
        ? "Ja existe um batch refresh em andamento."
        : status >= 500
          ? "A API nao conseguiu iniciar o batch refresh."
          : "Nao foi possivel solicitar o batch refresh.",
  });
}
