import { useAuth0 } from "@auth0/auth0-react";
import "../styles/authButtons.css";

export default function AuthButtons() {
  const {
    loginWithRedirect,
    logout: auth0Logout,
    isAuthenticated,
  } = useAuth0();

  const login = () =>
    loginWithRedirect({ appState: { returnTo: "/home" } });

  const signup = () =>
    loginWithRedirect({
      authorizationParams: { screen_hint: "signup" },
      appState: { returnTo: "/home" },
    });

  const logout = () =>
    auth0Logout({ logoutParams: { returnTo: window.location.origin } });

  return (
    <div className="auth-buttons">
      {!isAuthenticated ? (
        <>
          <button className="auth-btn login" onClick={login}>
            Iniciar Sesión
          </button>

          <button className="auth-btn signup" onClick={signup}>
            Crear Cuenta
          </button>
        </>
      ) : (
        <button className="auth-btn logout" onClick={logout}>
          Cerrar sesión
        </button>
      )}
    </div>
  );
}
