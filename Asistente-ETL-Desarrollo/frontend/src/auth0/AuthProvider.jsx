import { Auth0Provider } from "@auth0/auth0-react";

export default function AuthProvider({ children }) {
  const domain = "asistente.us.auth0.com";
  const clientId = "fOKhQZ0pH2f9aRsgOHdS9FZletL0AT19";

  const onRedirectCallback = (appState) => {
    window.history.replaceState({}, document.title, appState?.returnTo || "/home");
  };

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{ redirect_uri: `${window.location.origin}/home` }}
      onRedirectCallback={onRedirectCallback}
    >
      {children}
    </Auth0Provider>
  );
}