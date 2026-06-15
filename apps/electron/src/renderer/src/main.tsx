import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { UiProvider } from "./components/ui";
import "./index.css";
import "./loaders.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("root container not found");
}

createRoot(container).render(
  <StrictMode>
    <UiProvider>
      <App />
    </UiProvider>
  </StrictMode>,
);
