import type { ReactNode } from "react";

type Props = {
  title: string;
  /** Optional control shown at the right of the section title. */
  action?: ReactNode;
  children: ReactNode;
};

/** Small outlined label next to a value, e.g. "Main checkout" or "Isolated data". */
export function Tag({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span
      className="ml-2 inline-flex items-center gap-1 rounded-sm border px-1 font-mono text-2xs uppercase tracking-wider"
      style={{ borderColor: color, color }}
    >
      {children}
    </span>
  );
}

/** Shared frame of a dev panel section: title row, then the section body. */
export function SectionFrame({ title, action, children }: Props) {
  return (
    <section
      aria-label={title}
      className="flex flex-col gap-2 px-3 py-2"
      style={{ borderTop: "1px solid var(--color-border-subtle)" }}
    >
      <div className="flex items-center justify-between" style={{ minHeight: 22 }}>
        <h3
          className="font-mono text-2xs uppercase tracking-wider"
          style={{ color: "var(--color-text-tertiary)", margin: 0 }}
        >
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  );
}
