import { HealthCard } from "./components/HealthCard";

export function App() {
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col gap-6 px-6 py-10">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-widest text-zinc-500">
          Phase 1 prototype
        </p>
        <h1 className="text-3xl font-semibold text-zinc-50">
          CVM Analytics — desktop SPA shell
        </h1>
        <p className="max-w-xl text-sm text-zinc-400">
          Parallel Vite + React build that exercises the existing Python
          bridge. Replaces nothing in production yet; the released exe still
          ships the Next.js standalone runtime.
        </p>
      </header>
      <main className="space-y-6">
        <HealthCard />
      </main>
      <footer className="mt-auto pt-6 text-xs text-zinc-600">
        apps/desktop-web · proof-of-concept · not packaged yet
      </footer>
    </div>
  );
}
