import { useAuth0 } from "@auth0/auth0-react";
import { Navigate } from "react-router-dom";
import { useTheme } from "@/context/ThemeContext";
import "@/styles/login.css";
import AuthButtons from "@/auth0/AuthButtons";
import logo from "@/assets/Logo_blanco_esp.png";

export default function Login() {
  const { isAuthenticated } = useAuth0();
  const { dark, toggle } = useTheme();

  if (isAuthenticated) return <Navigate to="/home" replace />;

  return (
    <div className="login-container">
      <div className="login-box">
        <button className="theme-toggle" onClick={toggle} title="Cambiar tema">
          {dark ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="17" height="17">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="17" height="17">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>

        <div className="login-icon">
          <div className="login-logo-wrap">
            <img src={logo} alt="Logo" className="login-logo" />
          </div>
        </div>
        <h1>Bienvenido</h1>
        <p>Acceda a su cuenta para continuar</p>
        <AuthButtons />
      </div>
    </div>
  );
}

