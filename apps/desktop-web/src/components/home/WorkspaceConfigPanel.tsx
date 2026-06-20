import { WORKSPACE_REGISTRY } from "./WorkspaceRegistry";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  activeCardIds: string[];
  onToggleCard: (id: string) => void;
};

export function WorkspaceConfigPanel({
  isOpen,
  onClose,
  activeCardIds,
  onToggleCard,
}: Props) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-drawer flex w-80 flex-col border-l border-zinc-800 bg-zinc-950/95 p-5 shadow-drawer backdrop-blur-sm animate-in slide-in-from-right duration-200">
      <header className="flex items-center justify-between border-b border-zinc-800 pb-3 font-mono">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-100">
          Configure Workspace
        </h3>
        <button
          onClick={onClose}
          className="text-zinc-500 hover:text-zinc-300 text-xs font-semibold"
          aria-label="Close configuration panel"
        >
          [ CLOSE ]
        </button>
      </header>

      <div className="flex-1 overflow-y-auto py-4 space-y-4">
        <p className="text-2xs font-mono text-zinc-500 uppercase">
          Toggle Analyst Cards
        </p>

        <div className="space-y-3">
          {Object.values(WORKSPACE_REGISTRY).map((card) => {
            const isActive = activeCardIds.includes(card.id);
            return (
              <div
                key={card.id}
                onClick={() => onToggleCard(card.id)}
                className={`group flex cursor-pointer items-start justify-between rounded-lg border p-3 font-mono transition-all duration-150 ${
                  isActive
                    ? "border-orange-500/50 bg-orange-500/5"
                    : "border-zinc-850 bg-zinc-900/30 hover:border-zinc-700"
                }`}
              >
                <div className="min-w-0 flex-1 pr-2">
                  <p className="text-xs font-medium text-zinc-200 group-hover:text-white">
                    {card.title}
                  </p>
                  <p className="mt-1 text-2xs text-zinc-500 leading-normal">
                    {card.description}
                  </p>
                  <span className="mt-2 inline-block rounded bg-zinc-900 px-1 py-0.5 text-3xs text-zinc-400 border border-zinc-850">
                    {card.defaultSize.toUpperCase()}
                  </span>
                </div>

                <div className="shrink-0 pt-0.5">
                  <div
                    className={`flex h-4 w-4 items-center justify-center rounded border transition-colors ${
                      isActive
                        ? "border-orange-500 bg-orange-500 text-zinc-950"
                        : "border-zinc-700 bg-zinc-950 group-hover:border-zinc-500"
                    }`}
                  >
                    {isActive && (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 16 16"
                        fill="currentColor"
                        className="h-3 w-3"
                      >
                        <path
                          fillRule="evenodd"
                          d="M12.416 3.376a.75.75 0 0 1 .208 1.04l-5 7.5a.75.75 0 0 1-1.154.114l-3-3a.75.75 0 0 1 1.06-1.06l2.353 2.353 4.493-6.74a.75.75 0 0 1 1.04-.207z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <footer className="border-t border-zinc-900 pt-3 text-center">
        <p className="text-3xs text-zinc-600 font-mono">
          Drag cards by their headers to rearrange your workspace layout.
        </p>
      </footer>
    </div>
  );
}
