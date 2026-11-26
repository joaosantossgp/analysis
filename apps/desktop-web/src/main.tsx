import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { refreshCompaniesOnRunProgress } from "./lib/api/localDatabase";
import { queryClient } from "./lib/query";
import "./index.css";

refreshCompaniesOnRunProgress(queryClient);

const container = document.getElementById("root");
if (!container) {
  throw new Error("root container missing from index.html");
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
