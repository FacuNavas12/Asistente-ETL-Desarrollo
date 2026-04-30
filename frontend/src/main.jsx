import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { BrowserRouter } from "react-router-dom";
import AuthProvider from "./auth0/AuthProvider.jsx";
import { ThemeProvider } from "./context/ThemeContext.jsx";
import { EtlProvider } from "./context/EtlContext.jsx";
import "./css/theme.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ThemeProvider>
          <EtlProvider>
            <App />
          </EtlProvider>
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
