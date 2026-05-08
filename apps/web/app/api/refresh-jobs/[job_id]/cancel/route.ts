import { proxyJsonRoute } from "@/lib/api-route-proxy";

type CancelRefreshJobRouteProps = {
  params: Promise<{ job_id: string }>;
};

export async function POST(_: Request, { params }: CancelRefreshJobRouteProps) {
  const { job_id } = await params;

  return proxyJsonRoute({
    upstreamPath: `/refresh/jobs/${job_id}/cancel`,
    method: "POST",
    fallbackMessage: (status) =>
      status === 404
        ? "Job de refresh nao encontrado."
        : "Nao foi possivel cancelar o batch job.",
  });
}
