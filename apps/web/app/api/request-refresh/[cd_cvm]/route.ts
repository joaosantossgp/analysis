import { proxyJsonRoute } from "@/lib/api-route-proxy";

type RequestRefreshRouteProps = {
  params: Promise<{ cd_cvm: string }>;
};

export async function POST(_: Request, { params }: RequestRefreshRouteProps) {
  const { cd_cvm } = await params;

  return proxyJsonRoute({
    upstreamPath: `/companies/${cd_cvm}/request-refresh`,
    method: "POST",
    networkMessage: "Nao foi possivel conectar a API da V2.",
    fallbackMessage: (status) =>
      status === 429
        ? "Solicitacao ja em andamento."
        : status >= 500
          ? "A API da V2 nao conseguiu disparar o refresh agora."
          : "Nao foi possivel solicitar os dados financeiros desta companhia.",
    invalidResponseMessage:
      "A API da V2 retornou um corpo invalido para o dispatch on-demand.",
  });
}
