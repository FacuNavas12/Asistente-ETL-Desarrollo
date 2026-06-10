import { useAuth0 } from "@auth0/auth0-react";
import { useEtl } from "@/context/EtlContext";

export default function LogoutButton() {
  const { logout } = useAuth0();
  const { clearAll } = useEtl();

  const handleLogout = () => {
    clearAll();
    logout({ logoutParams: { returnTo: window.location.origin } });
  };

  return (
    <button className="logout-btn" onClick={handleLogout}>
      Cerrar Sesión
    </button>
  );
}

