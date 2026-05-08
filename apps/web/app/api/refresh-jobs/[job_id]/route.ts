import { proxyJsonRoute } from "@/lib/api-route-proxy";

type RefreshJobsRouteProps = {
  params: Promise<{ job_id: string }>;
};

export async function GET(_: Request, { params }: RefreshJobsRouteProps) {
  const { job_id } = await params;

  return proxyJsonRoute({
    upstreamPath: `/refresh/jobs/${job_id}`,
    fallbackMessage: (status) =>
      status === 404
        ? "Job de refresh nao encontrado."
        : "Nao foi possivel obter o status do batch job.",
  });
}
