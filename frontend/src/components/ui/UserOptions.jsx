import { useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "@/context/ThemeContext";
import { useEtl } from "@/context/EtlContext";
import "./userOptions.css";

export default function UserOptions({ onProfilePage = false }) {
  const { user, logout } = useAuth0();
  const { dark, toggle } = useTheme();
  const { clearAll } = useEtl();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = () => {
    clearAll();
    logout({ logoutParams: { returnTo: window.location.origin } });
  };

  return (
    <div className="user-options" onClick={() => setOpen(o => !o)}>
      {user?.picture && (
        <img src={user.picture} alt="avatar" className="user-options__avatar" />
      )}
      <span className="user-options__name">{user?.name}</span>
      <span className={`user-options__arrow ${open ? "open" : ""}`}>▼</span>

      {open && (
        <div className="user-options__dropdown" onClick={e => e.stopPropagation()}>
          {onProfilePage ? (
            <button onClick={() => navigate("/home")}>Inicio</button>
          ) : (
            <button onClick={() => navigate("/profile")}>Mi Perfil</button>
          )}
          <button onClick={toggle}>
            Modo {dark ? "☀️ Claro" : "🌙 Oscuro"}
          </button>
          <button className="user-options__logout" onClick={handleLogout}>
            Cerrar Sesión
          </button>
        </div>
      )}
    </div>
  );
}

