import { ExportActionPanel } from "@/components/export/ExportActionPanel";

type Props = {
  cdCvm: number;
  statementType?: string;
  scopeLabel?: string;
  scopeNote?: string;
  className?: string;
  framed?: boolean;
};

export function ExportCompanyButton({
  cdCvm,
  statementType,
  scopeLabel,
  scopeNote,
  className,
  framed = false,
}: Props) {
  return (
    <ExportActionPanel
      cdCvm={cdCvm}
      statementType={statementType}
      scopeLabel={scopeLabel}
      scopeNote={scopeNote}
      className={className}
      framed={framed}
    />
  );
}
