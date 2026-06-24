import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import AuthProvider from "./auth0/AuthProvider.jsx";
import { ThemeProvider } from "./context/ThemeContext.jsx";
import { EtlProvider } from "./context/EtlContext.jsx";
import { ToastProvider } from "./components/ui/Toast.jsx";
import "@/styles/theme.css";

const router = createBrowserRouter([
  {
    path: "*",
    element: (
      <AuthProvider>
        <ThemeProvider>
          <EtlProvider>
            <ToastProvider>
              <App />
            </ToastProvider>
          </EtlProvider>
        </ThemeProvider>
      </AuthProvider>
    ),
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);

