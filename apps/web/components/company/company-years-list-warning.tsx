import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type CompanyYearsListWarningProps = {
  /** `detail_fallback`: cockpit loaded via company-card metadata; `no_data_shell`: empty years UX */
  context: "detail_fallback" | "no_data_shell";
};

export function CompanyYearsListWarning({ context }: CompanyYearsListWarningProps) {
  const title =
    context === "no_data_shell"
      ? "Lista de anos indisponivel agora"
      : "Lista de anos nao confirmada";
  const description =
    context === "no_data_shell"
      ? "Nao foi possivel consultar o endpoint de anos. O estado da pagina usa os campos de leitura do cartao da empresa e pode ficar incompleto ate outra tentativa."
      : "O recorte foi montado com os campos de disponibilidade do cartao da empresa porque a lista oficial de anos nao respondeu. Atualize a pagina se KPIs ou demonstracoes parecerem inconsistentes.";

  return (
    <Alert className="rounded-[1.25rem] border border-border/65 bg-muted/25 px-4 py-4">
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="text-muted-foreground">{description}</AlertDescription>
    </Alert>
  );
}
