import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { Navigate } from "react-router-dom";
import "../css/login.css";
import AuthButtons from "../auth0/AuthButtons";

export default function Login() {
  const { isAuthenticated } = useAuth0();
  const [dark, setDark] = useState(true);

  if (isAuthenticated) return <Navigate to="/home" replace />;

  return (
    <div className={`login-container ${dark ? "theme-dark" : "theme-light"}`}>
      <div className="login-box">
        <button className="theme-toggle" onClick={() => setDark(!dark)} title="Cambiar tema">
          {dark ? "☀️" : "🌙"}
        </button>
        <div className="login-icon">⬡</div>
        <h1>Bienvenido</h1>
        <p>Accedé a tu cuenta para continuar</p>
        <AuthButtons />
      </div>
    </div>
  );
}
