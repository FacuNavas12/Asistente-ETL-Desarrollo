/**
 * Hook que envuelve fetch() para incluir automáticamente el Bearer token de Auth0
 * cuando VITE_AUTH_REQUIRED=true.
 *
 * Uso:
 *   const authFetch = useAuthFetch();
 *   const res = await authFetch("/api/v1/etl/generate", { method: "POST", ... });
 *
 * En producción (organización propia):
 *   Reemplazar getAccessTokenSilently() por el mecanismo del proveedor de identidad
 *   corporativo (MSAL para Azure AD, Keycloak JS, etc.) sin cambiar los componentes.
 */
import { useAuth0 } from "@auth0/auth0-react";

const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED === "true";
const AUTH_AUDIENCE = import.meta.env.VITE_AUTH0_AUDIENCE;

export function useAuthFetch() {
  const { getAccessTokenSilently } = useAuth0();

  return async function authFetch(url, options = {}) {
    if (!AUTH_REQUIRED) {
      return fetch(url, options);
    }

    const token = await getAccessTokenSilently({
      authorizationParams: { audience: AUTH_AUDIENCE },
    });

    return fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        Authorization: `Bearer ${token}`,
      },
    });
  };
}
