import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate, useLocation } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import "../css/navbar.css";

export default function Navbar({ onHomeClick }) {
  const { user, logout } = useAuth0();
  const { dark, toggle } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [dropOpen, setDropOpen] = useState(false);


  //boton home en cualquier lado que no sea home
  const showHomeIcon = location.pathname !== "/home";


  const handleLogout = () =>
    logout({ logoutParams: { returnTo: window.location.origin } });

  const handleHomeClick = () => {
    if (onHomeClick) onHomeClick();
    else navigate("/home");
  };

  return (
    <header className="navbar">
      <span className="navbar__brand">Asistente ETL</span>

      <div className="navbar__actions">
        {showHomeIcon && (
          <button className="navbar__icon-btn" onClick={handleHomeClick} title="Inicio">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
          </button>
        )}

        <button className="navbar__icon-btn" onClick={toggle} title={dark ? "Modo claro" : "Modo oscuro"}>
          {dark ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>

        <div className="navbar__avatar-wrap" onClick={() => setDropOpen(o => !o)}>
          {user?.picture ? (
            <img src={user.picture} alt="avatar" className="navbar__avatar" />
          ) : (
            <div className="navbar__avatar-fallback">
              {user?.name?.[0]?.toUpperCase()}
            </div>
          )}

          {dropOpen && (
            <div className="navbar__dropdown" onClick={e => e.stopPropagation()}>
              <button onClick={() => { navigate("/profile"); setDropOpen(false); }}>
                Mi Perfil
              </button>
              <button className="navbar__logout" onClick={handleLogout}>
                Cerrar Sesión
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
