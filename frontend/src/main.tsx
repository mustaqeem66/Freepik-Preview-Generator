import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ApiBridge } from "./api/bridge";
import { watchCspViolations } from "./security/cspViolations";
import "./index.css";
import "./studioPolish.css";
import "./studioPremium.css";
import "./studioControls.css";
import "lenis/dist/lenis.css";
import "./studioMotion.css";
import "./desktopTitlebar.css";

// Log engine-reported violations when the native bridge is available.
// Missing events or an unavailable bridge are not CSP enforcement evidence.
watchCspViolations(async (violations) => {
  const api = await ApiBridge.getApi(250);
  await api?.report_csp_violations?.(violations);
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
