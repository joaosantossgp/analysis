import { ProblemStateCard } from "@/components/shared/problem-state-card";

export function CompanyDetailErrorPage({
  message,
}: {
  message: string;
}) {
  return (
    <ProblemStateCard
      eyebrow="Detalhe da companhia"
      title="Detalhes indisponiveis"
      description="Nao foi possivel carregar os dados desta companhia agora."
      alertTitle="Falha na leitura detalhada"
      alertDescription={message}
      tone="default"
      padding="lg"
      actions={[
        {
          href: "/empresas",
          label: "Voltar para o diretorio",
          variant: "outline",
          className: "w-fit",
        },
      ]}
    />
  );
}
