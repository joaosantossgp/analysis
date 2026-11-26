import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { requestCompanyRefresh } from "@/lib/api/companyRefresh";
import { LOCAL_DATABASE_STATE_KEY, useLocalDatabaseState } from "@/lib/api/localDatabase";

/**
 * On a company page, lets the analyst pull a company waiting in the running
 * data update ahead of the queue. It starts a company update, which never
 * resets Stale.
 */
export function QueuedCompanyNotice({ cdCvm }: { cdCvm: number }) {
  const { data } = useLocalDatabaseState();
  const queryClient = useQueryClient();
  const download = useMutation({
    mutationFn: () => requestCompanyRefresh(cdCvm),
    onSettled: () => queryClient.invalidateQueries({ queryKey: LOCAL_DATABASE_STATE_KEY }),
  });

  const run = data?.run;
  if (!run || run.current_cvm === cdCvm || !run.company_ids.includes(cdCvm)) return null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 px-3 py-2 text-xs"
      style={{ background: "var(--color-surface-2)", border: "1px solid var(--color-border-default)", borderRadius: "var(--radius-md)" }}
    >
      <span style={{ color: "var(--color-text-secondary)" }}>
        <span aria-hidden="true" style={{ color: "var(--color-id-ticker)" }}>◌ </span>
        This company is part of the running data update.
      </span>
      <Button variant="secondary" size="xs" loading={download.isPending} disabled={download.isSuccess} onClick={() => download.mutate()}>
        {download.isSuccess ? "Requested" : "Download now"}
      </Button>
      {download.error ? (
        <span role="alert" style={{ color: "var(--color-state-err)" }}>{(download.error as Error).message}</span>
      ) : null}
    </div>
  );
}
