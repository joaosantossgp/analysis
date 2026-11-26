import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { Kbd } from "@/components/ui/Kbd";

import { rankCommands, type Command } from "./CommandRegistry";
import { buildActionCommands } from "./commands/actions";
import {
  buildCompanyCommands,
  useCompaniesIndex,
} from "./commands/companies";
import { buildNavigationCommands } from "./commands/navigation";

type Props = {
  open: boolean;
  primed: boolean;
  onClose: () => void;
};

function glyphFor(cmd: Command): string {
  switch (cmd.glyph) {
    case "company":
      return "○";
    case "route":
      return "▤";
    case "action":
      return "↻";
  }
}

export function CommandBar({ open, primed, onClose }: Props) {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);

  const companiesQuery = useCompaniesIndex(primed);

  // Reset state when palette closes — next open starts clean.
  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIdx(0);
    } else {
      // Defer focus to after portal mount.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const allCommands: Command[] = useMemo(() => {
    const nav = buildNavigationCommands(navigate);
    const actions = buildActionCommands();
    const companies = buildCompanyCommands(companiesQuery.data, navigate);
    return [...nav, ...actions, ...companies];
  }, [navigate, companiesQuery.data]);

  const results = useMemo(
    () => rankCommands(allCommands, query, 12),
    [allCommands, query],
  );

  // Clamp activeIdx into result range.
  useEffect(() => {
    if (activeIdx >= results.length) setActiveIdx(Math.max(0, results.length - 1));
  }, [results.length, activeIdx]);

  // Scroll the active row into view as it changes.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const row = list.children[activeIdx] as HTMLElement | undefined;
    row?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  if (!open) return null;

  function activate(cmd: Command | undefined) {
    if (!cmd) return;
    cmd.run();
    onClose();
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, Math.max(0, results.length - 1)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      activate(results[activeIdx]);
    } else if (event.key === "Tab") {
      event.preventDefault();
      const dir = event.shiftKey ? -1 : 1;
      setActiveIdx((i) => {
        const next = i + dir;
        if (next < 0) return results.length - 1;
        if (next >= results.length) return 0;
        return next;
      });
    }
  }

  const node = (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onClick={onClose}
      className="fixed inset-0 flex items-start justify-center pt-[20vh]"
      style={{
        zIndex: "var(--z-palette)" as unknown as number,
        background: "rgba(0, 0, 0, 0.65)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex w-full max-w-2xl flex-col overflow-hidden rounded-md"
        style={{
          background: "var(--color-surface-2)",
          border: "1px solid var(--color-border-strong)",
          boxShadow: "var(--shadow-overlay)",
        }}
      >
        {/* Search input */}
        <div
          className="flex items-center gap-2 px-4 py-3"
          style={{ borderBottom: "1px solid var(--color-border-subtle)" }}
        >
          <span
            aria-hidden="true"
            className="font-mono text-sm"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            ›
          </span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search companies, pages and actions…"
            className="w-full bg-transparent font-mono outline-none"
            style={{ color: "var(--color-text-primary)", fontSize: "var(--text-base)" }}
            aria-label="Comando ou busca"
            autoComplete="off"
            spellCheck={false}
          />
          {companiesQuery.isLoading ? (
            <span className="font-mono text-2xs" style={{ color: "var(--color-text-tertiary)" }}>
              indexando…
            </span>
          ) : null}
          <Kbd>Esc</Kbd>
        </div>

        {/* Results */}
        <ul
          ref={listRef}
          role="listbox"
          aria-label="Resultados"
          className="max-h-[50vh] overflow-y-auto"
        >
          {results.length === 0 ? (
            <li
              className="px-4 py-6 text-center font-mono text-sm"
              style={{ color: "var(--color-text-tertiary)" }}
            >
              {query.trim()
                ? "No results."
                : "Type to search companies, or pick a page."}
            </li>
          ) : (
            results.map((cmd, idx) => {
              const isActive = idx === activeIdx;
              return (
                <li
                  key={cmd.id}
                  role="option"
                  aria-selected={isActive}
                  onMouseEnter={() => setActiveIdx(idx)}
                  onClick={() => activate(cmd)}
                  className="flex cursor-pointer items-center gap-3 px-4"
                  style={{
                    background: isActive ? "var(--color-surface-4)" : "transparent",
                    borderLeft: isActive
                      ? "2px solid var(--color-action-primary)"
                      : "2px solid transparent",
                    height: "var(--row-h-comfortable)",
                  }}
                >
                  <span
                    aria-hidden="true"
                    className="w-4 text-center font-mono text-xs"
                    style={{
                      color:
                        cmd.group === "companies"
                          ? "var(--color-id-ticker)"
                          : cmd.group === "actions"
                            ? "var(--color-action-primary)"
                            : "var(--color-text-tertiary)",
                    }}
                  >
                    {glyphFor(cmd)}
                  </span>
                  <span
                    className="flex-1 truncate"
                    style={{
                      color: "var(--color-text-primary)",
                      fontSize: "var(--text-base)",
                    }}
                  >
                    {cmd.label}
                  </span>
                  {cmd.secondary ? (
                    <span
                      className="font-mono text-xs"
                      style={{
                        color:
                          cmd.group === "companies"
                            ? "var(--color-id-ticker)"
                            : "var(--color-text-tertiary)",
                      }}
                    >
                      {cmd.secondary}
                    </span>
                  ) : null}
                </li>
              );
            })
          )}
        </ul>

        {/* Footer */}
        <div
          className="flex items-center justify-between gap-4 px-4 py-2 font-mono text-2xs"
          style={{
            borderTop: "1px solid var(--color-border-subtle)",
            color: "var(--color-text-tertiary)",
          }}
        >
          <span className="flex items-center gap-2">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd>
            navegar
          </span>
          <span className="flex items-center gap-2">
            <Kbd>Enter</Kbd>
            abrir
          </span>
          <span>
            {companiesQuery.data
              ? `${companiesQuery.data.length} empresas indexadas`
              : companiesQuery.isError
                ? "erro ao indexar"
                : primed
                  ? "carregando empresas…"
                  : "—"}
          </span>
        </div>
      </div>
    </div>
  );

  return createPortal(node, document.body);
}
