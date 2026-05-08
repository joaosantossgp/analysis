import { ProblemStateCard } from "@/components/shared/problem-state-card";

export default function NotFound() {
  return (
    <ProblemStateCard
      centered
      eyebrow="404 - rota nao encontrada"
      title="Esse caminho ainda nao existe nesta fase."
      description="O slice atual cobre a home, o diretorio de empresas, a comparacao, o detalhe por companhia e a leitura por setores. KPIs e macro entram nas proximas fases."
      actions={[
        { href: "/", label: "Voltar para a home" },
        { href: "/empresas", label: "Abrir empresas", variant: "outline" },
      ]}
    />
  );
}
