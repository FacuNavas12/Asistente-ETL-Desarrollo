import { Auth0Provider } from "@auth0/auth0-react";

const AUTH_AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE;

export default function AuthProvider({ children }) {
  const domain   = "asistente.us.auth0.com";
  const clientId = "fOKhQZ0pH2f9aRsgOHdS9FZletL0AT19";

  const onRedirectCallback = (appState) => {
    window.history.replaceState({}, document.title, appState?.returnTo || "/home");
  };

  // audience se incluye solo cuando está configurado (VITE_AUTH0_AUDIENCE en .env).
  // Sin audience, Auth0 emite tokens opacos (modo prototipo sin API registrada).
  // Con audience, Auth0 emite JWT RS256 que el backend puede validar con JWKS.
  const authorizationParams = {
    redirect_uri: `${window.location.origin}/home`,
    ...(AUTH_AUDIENCE ? { audience: AUTH_AUDIENCE } : {}),
  };

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={authorizationParams}
      onRedirectCallback={onRedirectCallback}
    >
      {children}
    </Auth0Provider>
  );
}