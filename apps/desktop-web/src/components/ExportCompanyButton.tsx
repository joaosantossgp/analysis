import { ExportActionPanel } from "@/components/export/ExportActionPanel";

type Props = {
  cdCvm: number;
  statementType?: string;
  mappingPresetId?: string;
  scopeLabel?: string;
  scopeNote?: string;
  className?: string;
  framed?: boolean;
};

export function ExportCompanyButton({
  cdCvm,
  statementType,
  mappingPresetId,
  scopeLabel,
  scopeNote,
  className,
  framed = false,
}: Props) {
  return (
    <ExportActionPanel
      cdCvm={cdCvm}
      statementType={statementType}
      mappingPresetId={mappingPresetId}
      scopeLabel={scopeLabel}
      scopeNote={scopeNote}
      className={className}
      framed={framed}
    />
  );
}
