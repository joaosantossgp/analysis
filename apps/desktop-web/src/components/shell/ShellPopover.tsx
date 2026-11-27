import { useEffect, useRef, type ReactNode } from "react";

/**
 * Compact panel opened from a top-bar pill (Data panel, Software update).
 * Closes on Escape, a click outside or its close button; render it only while open.
 */
export function ShellPopover({
  id,
  title,
  closeLabel,
  onClose,
  children,
}: {
  id: string;
  title: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // Once per opening: re-running on every render would pull focus off the panel's buttons.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    window.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <button
        type="button"
        tabIndex={-1}
        aria-label={closeLabel}
        onClick={onClose}
        style={{ position: "fixed", inset: 0, background: "transparent", cursor: "default", zIndex: "var(--z-drawer)" as unknown as number }}
      />
      <div
        id={id}
        ref={panelRef}
        role="dialog"
        aria-label={title}
        tabIndex={-1}
        style={{
          position: "fixed",
          top: "calc(36px + 32px + 8px)",
          right: 16,
          width: "min(360px, calc(100vw - 32px))",
          maxHeight: "calc(100vh - 116px)",
          overflow: "auto",
          background: "var(--color-surface-2)",
          border: "1px solid var(--color-border-default)",
          borderRadius: "var(--radius-md)",
          boxShadow: "var(--shadow-overlay)",
          zIndex: "var(--z-overlay)" as unknown as number,
        }}
      >
        <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
          <h2 className="text-sm font-semibold" style={{ color: "var(--color-text-primary)" }}>{title}</h2>
          <button
            type="button"
            aria-label={closeLabel}
            onClick={onClose}
            className="rounded-sm px-1.5 text-sm hover:bg-[var(--color-surface-3)]"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            ×
          </button>
        </div>
        <div className="p-3">{children}</div>
      </div>
    </>
  );
}
