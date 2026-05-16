import { useState } from "react";
import "@/styles/login.css";

export default function Register() {
  const [dark, setDark] = useState(true);

  return (
    <div className={`login-container ${dark ? "theme-dark" : "theme-light"}`}>
      <div className="login-box">
        <button className="theme-toggle" onClick={() => setDark(!dark)} title="Cambiar tema">
          {dark ? "â˜€ï¸" : "ðŸŒ™"}
        </button>
        <div className="login-icon">â¬¡</div>
        <h1>Crear cuenta</h1>
        <p>CompletÃ¡ tus datos para registrarte</p>
      </div>
    </div>
  );
}

