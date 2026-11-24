import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/alexandria";
import "@fontsource-variable/readex-pro";
import App from "./App";
import { StoreProvider } from "./store";
import "./styles/base.css";
import "./styles/shell.css";
import "./styles/ui.css";
import "./styles/home.css";
import "./styles/pages.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <StoreProvider>
        <App />
      </StoreProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
