import { lazy } from "react";

/**
 * Dev panel entry point for the app shell. `import.meta.env.DEV` is a Vite
 * compile-time constant, so a production build resolves this to `null` and
 * drops the dev panel code from the bundle: the packaged app has no dot, panel
 * or shortcut.
 */
export const LazyDevPanel = import.meta.env.DEV
  ? lazy(() => import("./DevPanel").then((m) => ({ default: m.DevPanel })))
  : null;
