import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  clearCompanyClassification,
  fetchGicsStructure,
  filterGicsOptions,
  setCompanyClassification,
} from "@/lib/api/classification";
import type { CompanyClassification, GicsSubIndustry } from "@/lib/bridge/types";

type Props = {
  cdCvm: number;
  classification: CompanyClassification | null | undefined;
};

/** Notice shown when the shipped curation moved after the analyst's local edit. */
export function curatedChangeNotice(classification: CompanyClassification | null | undefined): string | null {
  const edit = classification?.user_edit;
  if (!edit?.curated_changed_since_edit) return null;
  const curated = edit.curated_sub_industry
    ? `${edit.curated_sub_industry} (${edit.curated_sub_industry_code})`
    : "no curated value";
  return `The curated classification changed to ${curated} since your edit.`;
}

export function ClassificationEditor({ cdCvm, classification }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<GicsSubIndustry | null>(null);
  const queryClient = useQueryClient();

  const structure = useQuery({ queryKey: ["gics-structure"], queryFn: fetchGicsStructure, enabled: open, staleTime: Infinity });
  const options = useMemo(() => filterGicsOptions(structure.data ?? [], search), [structure.data, search]);

  const onSaved = () => {
    void queryClient.invalidateQueries({ queryKey: ["company-info", cdCvm] });
    void queryClient.invalidateQueries({ queryKey: ["companies"] });
    setOpen(false);
    setSelected(null);
    setSearch("");
  };
  const save = useMutation({
    mutationFn: (code: string) => setCompanyClassification(cdCvm, code),
    onSuccess: onSaved,
  });
  const revert = useMutation({ mutationFn: () => clearCompanyClassification(cdCvm), onSuccess: onSaved });

  if (!classification) return null;
  const notice = curatedChangeNotice(classification);
  const error = save.error ?? revert.error ?? structure.error;

  if (!open) {
    return (
      <span className="flex items-center gap-2">
        {notice ? <span className="text-xs" style={{ color: "var(--color-state-warn)" }}>{notice}</span> : null}
        <Button size="xs" variant="ghost" onClick={() => setOpen(true)} aria-label="Edit GICS classification">
          Edit classification
        </Button>
      </span>
    );
  }

  return (
    <div
      role="dialog"
      aria-label="Edit GICS classification"
      className="flex w-full flex-col gap-2"
      style={{
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-surface-1)",
        padding: 12,
        maxWidth: 640,
      }}
    >
      <div className="text-xs" style={{ color: "var(--color-text-secondary)" }}>
        Pick a GICS sub-industry. Your choice is stored locally, wins over the curated value and is kept across updates.
      </div>
      {notice ? <div className="text-xs" style={{ color: "var(--color-state-warn)" }}>{notice}</div> : null}
      <Input
        autoFocus
        placeholder="Search sub-industry, industry, sector or code"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
      />
      <ul role="listbox" style={{ maxHeight: 220, overflowY: "auto", margin: 0, padding: 0, listStyle: "none" }}>
        {structure.isLoading ? <li className="text-xs">Loading GICS structure…</li> : null}
        {!structure.isLoading && options.length === 0 ? <li className="text-xs">No sub-industry matches.</li> : null}
        {options.map((item) => (
          <li
            key={item.sub_industry_code}
            role="option"
            aria-selected={selected?.sub_industry_code === item.sub_industry_code}
            onClick={() => setSelected(item)}
            className="cursor-pointer text-xs"
            style={{
              padding: "4px 6px",
              borderRadius: "var(--radius-sm)",
              background:
                selected?.sub_industry_code === item.sub_industry_code ? "var(--color-surface-3)" : "transparent",
            }}
          >
            <strong>{item.sub_industry}</strong>{" "}
            <span style={{ color: "var(--color-text-secondary)" }}>
              {item.sector} › {item.industry_group} › {item.industry} · {item.sub_industry_code}
            </span>
          </li>
        ))}
      </ul>
      {error ? (
        <div className="text-xs" role="alert" style={{ color: "var(--color-state-err)" }}>
          {error instanceof Error ? error.message : String(error)}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={!selected}
          loading={save.isPending}
          onClick={() => selected && save.mutate(selected.sub_industry_code)}
        >
          Save
        </Button>
        {classification.origin === "user" ? (
          <Button size="sm" variant="secondary" loading={revert.isPending} onClick={() => revert.mutate()}>
            Revert to curated
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
