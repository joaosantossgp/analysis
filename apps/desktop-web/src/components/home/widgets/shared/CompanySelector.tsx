import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCompanies } from "@/lib/api/companies";

interface CompanySelectorProps {
  onSelect: (cdCvm: number, name: string, ticker: string) => void;
  placeholder?: string;
}

export function CompanySelector({
  onSelect,
  placeholder = "Search company by name or ticker...",
}: CompanySelectorProps) {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ["companies-search", debouncedSearch],
    queryFn: () => fetchCompanies({ search: debouncedSearch, page_size: 6 }),
    enabled: debouncedSearch.length >= 2,
  });

  const list = data?.mode === "desktop" ? data.page.items : [];

  return (
    <div className="relative w-full space-y-1">
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-zinc-800 bg-zinc-955 px-3 py-1.5 font-mono text-xs text-zinc-100 placeholder-zinc-650 focus:border-orange-500 focus:outline-none"
      />
      {isLoading && (
        <p className="px-2 text-2xs text-zinc-550 font-mono">Searching database...</p>
      )}
      {!isLoading && debouncedSearch.length >= 2 && list.length === 0 && (
        <p className="px-2 text-2xs text-zinc-550 font-mono">No matching companies found.</p>
      )}
      {list.length > 0 && (
        <div className="absolute left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950 p-1 shadow-xl">
          {list.map((c) => (
            <button
              key={c.cd_cvm}
              onClick={() => {
                onSelect(c.cd_cvm, c.company_name, c.ticker_b3 || "");
                setSearch("");
                setDebouncedSearch("");
              }}
              className="flex w-full items-center justify-between rounded-sm px-2 py-1 text-left font-mono text-xs hover:bg-zinc-800 text-zinc-200 hover:text-white"
            >
              <span className="truncate mr-2 text-left">{c.company_name}</span>
              <span className="shrink-0 text-2xs text-cyan-400">
                {c.ticker_b3 || `CVM ${c.cd_cvm}`}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
