import { proxyJsonRoute } from "@/lib/api-route-proxy";

type RefreshStatusRouteProps = {
  params: Promise<{ cd_cvm: string }>;
};

export async function GET(_: Request, { params }: RefreshStatusRouteProps) {
  const { cd_cvm } = await params;

  return proxyJsonRoute({
    upstreamPath: `/refresh-status?cd_cvm=${encodeURIComponent(cd_cvm)}`,
    networkMessage: "Nao foi possivel conectar a API da V2.",
    fallbackMessage: (status) =>
      status >= 500
        ? "A API da V2 nao conseguiu consultar o status do refresh agora."
        : "Nao foi possivel consultar o andamento desta solicitacao.",
    invalidResponseMessage:
      "A API da V2 retornou um corpo invalido para o status do refresh.",
  });
}
