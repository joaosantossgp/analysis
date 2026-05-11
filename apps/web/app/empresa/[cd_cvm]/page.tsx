import { redirect } from "next/navigation";

type EmpresaAliasPageProps = {
  params: Promise<{ cd_cvm: string }>;
};

export default async function EmpresaAliasPage({ params }: EmpresaAliasPageProps) {
  const { cd_cvm } = await params;
  redirect(`/empresas/${encodeURIComponent(cd_cvm)}`);
}
