import { useState, useRef, useEffect } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "@/context/ThemeContext";
import { useToast } from "@/components/ui/Toast";
import "./navbar.css";
import logo from "@/assets/Logo_blanco_esp.png";

function formatMsgTime(ts) {
  return new Date(ts).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

export default function Navbar({ guardNavigation }) {
  const { user, logout } = useAuth0();
  const { dark, toggle } = useTheme();
  const navigate = useNavigate();
  const { systemMessages, removeSystemMessage, clearSystemMessages } = useToast();

  const [avatarOpen, setAvatarOpen] = useState(false);
  const [msgOpen, setMsgOpen] = useState(false);
  const avatarRef = useRef(null);

  const initials = user?.name
    ? user.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  useEffect(() => {
    if (!avatarOpen) return;
    const handler = e => {
      if (avatarRef.current && !avatarRef.current.contains(e.target)) {
        setAvatarOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [avatarOpen]);

  // Route all navigation through the guard when one is provided (e.g. dirty form)
  const go = (path, opts) => {
    const doIt = () => navigate(path, opts);
    guardNavigation ? guardNavigation(doIt) : doIt();
  };

  const handleLogout = () =>
    logout({ logoutParams: { returnTo: window.location.origin } });

  return (
    <>
      <aside className="sidebar">
        {/* Logo */}
        <button
          className="sidebar__logo"
          onClick={() => go("/home")}
          data-tooltip="Home"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
        </button>

        {/* Avatar */}
        <div className="sidebar__avatar-wrap" ref={avatarRef}>
          <button
            className="sidebar__avatar-btn"
            onClick={() => setAvatarOpen(o => !o)}
            data-tooltip="Mi cuenta"
          >
            {user?.picture ? (
              <img src={user.picture} alt="avatar" className="sidebar__avatar-img" />
            ) : (
              <span className="sidebar__avatar-initials">{initials}</span>
            )}
          </button>

          {avatarOpen && (
            <div className="sidebar__popover">
              <span className="sidebar__popover-email">{user?.email}</span>
              <button
                className="sidebar__popover-link"
                onClick={() => { setAvatarOpen(false); go("/profile"); }}
              >
                Ver Perfil
              </button>
            </div>
          )}
        </div>

        {/* Separator */}
        <div className="sidebar__sep" />

        {/* Nuevo ETL — siempre abre formulario limpio */}
        <button
          className="sidebar__btn sidebar__btn--new"
          onClick={() => go("/etl-create", { state: { fresh: true } })}
          data-tooltip="Nuevo ETL"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>

        {/* Separator */}
        <div className="sidebar__sep" />

        {/* Mensajes */}
        <div
          className="sidebar__msg-wrap"
          onMouseEnter={() => setMsgOpen(true)}
          onMouseLeave={() => setMsgOpen(false)}
        >
          <button
            className="sidebar__btn"
            data-tooltip="Mensajes"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 4h16v16H4z" />
              <path d="M4 6l8 7 8-7" />
            </svg>
            {systemMessages.length > 0 && (
              <span className="sidebar__msg-badge">{systemMessages.length}</span>
            )}
          </button>

          {msgOpen && (
            <div className="sidebar__msg-panel">
              <div className="sidebar__msg-panel-header">
                <span>Mensajes</span>
                {systemMessages.length > 0 && (
                  <button className="sidebar__msg-clear" onClick={clearSystemMessages}>
                    Limpiar todo
                  </button>
                )}
              </div>
              {systemMessages.length === 0 ? (
                <p className="sidebar__msg-empty">Sin mensajes de sistema</p>
              ) : (
                <ul className="sidebar__msg-list">
                  {systemMessages.map((m) => (
                    <li key={m.id} className="sidebar__msg-item">
                      <span className="sidebar__msg-text">{m.text}</span>
                      <div className="sidebar__msg-item-footer">
                        <span className="sidebar__msg-time">{formatMsgTime(m.ts)}</span>
                        <button
                          className="sidebar__msg-remove"
                          onClick={() => removeSystemMessage(m.id)}
                        >
                          ×
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Spacer */}
        <div className="sidebar__spacer" />

        {/* Cambiar tema */}
        <button
          className="sidebar__btn"
          onClick={toggle}
          data-tooltip="Cambiar tema"
        >
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

        {/* Configuración */}
        <button
          className="sidebar__btn"
          onClick={() => go("/settings")}
          data-tooltip="Configuración"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>

        {/* Cerrar sesión */}
        <button
          className="sidebar__btn sidebar__btn--logout"
          onClick={handleLogout}
          data-tooltip="Cerrar sesión"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </aside>

    </>
  );
}
