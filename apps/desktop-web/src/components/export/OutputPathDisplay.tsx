type Props = {
  path: string | null | undefined;
  label?: string;
  missing?: boolean;
};

export function OutputPathDisplay({ path, label = "Destino local", missing = false }: Props) {
  if (!path) {
    return (
      <p style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)", margin: 0 }}>
        {label}: <span className="font-mono">indisponível</span>
      </p>
    );
  }

  return (
    <div className="min-w-0 space-y-1">
      <p
        style={{
          color: missing ? "var(--color-state-warn)" : "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {missing ? "Pasta será criada no primeiro export" : label}
      </p>
      <code
        className="block truncate font-mono"
        style={{
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-xs)",
          lineHeight: 1.35,
        }}
        title={path}
      >
        {path}
      </code>
    </div>
  );
}
