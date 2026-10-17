import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { RuntimeProvider } from "./Runtime";
import "katex/dist/katex.min.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RuntimeProvider>
      <App />
    </RuntimeProvider>
  </React.StrictMode>,
);
