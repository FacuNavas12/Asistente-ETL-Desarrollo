"""
Autenticación de la API — Marco AGESIC 5.0, función Proteger.

Diseño intercambiable: el sistema de autenticación se configura 100% por
variables de entorno. Para el prototipo se usa Auth0; en producción se
reemplaza cambiando AUTH_JWKS_URL / AUTH_AUDIENCE / AUTH_ISSUER sin tocar
código de negocio.

Variables de entorno requeridas cuando AUTH_REQUIRED=true:
  AUTH_JWKS_URL   URL del endpoint JWKS del proveedor de identidad.
                  Auth0:      https://<tenant>.auth0.com/.well-known/jwks.json
                  Azure AD:   https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
                  Keycloak:   https://<host>/realms/<realm>/protocol/openid-connect/certs
  AUTH_AUDIENCE   Identificador de la API registrado en el proveedor.
  AUTH_ISSUER     Issuer del token (debe coincidir con el claim "iss").
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    import jwt
except ImportError:
    jwt = None  # type: ignore[assignment]  — solo requerido cuando AUTH_REQUIRED=true
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# Singleton de PyJWKClient — se inicializa la primera vez que AUTH_REQUIRED=true.
# PyJWKClient gestiona su propio cache de claves públicas (cache_jwk_set=True,
# lifespan=600 s). No se necesita cache manual adicional.
_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client

    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PyJWT no está instalado. Ejecutar: pip install PyJWT==2.10.1",
        )
    if not settings.auth_jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_JWKS_URL no está configurado. Agregar al .env y reiniciar el servidor.",
        )
    if not settings.auth_audience:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_AUDIENCE no está configurado. Agregar al .env y reiniciar el servidor.",
        )
    if not settings.auth_issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_ISSUER no está configurado. Agregar al .env y reiniciar el servidor.",
        )

    _jwks_client = jwt.PyJWKClient(
        settings.auth_jwks_url,
        cache_jwk_set=True,
        lifespan=600,  # refresca claves públicas cada 10 minutos
    )
    logger.info("JWKS client inicializado: %s", settings.auth_jwks_url)
    return _jwks_client


def _validate_token(token: str) -> dict:
    """Valida un JWT Bearer contra el JWKS del proveedor configurado."""
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth_audience,
            issuer=settings.auth_issuer,
            options={"require": ["exp", "iss", "aud"]},
        )
        return payload
    except HTTPException:
        raise  # re-lanza los errores de configuración tal cual
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Audiencia del token inválida.")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Emisor del token inválido.")
    except jwt.PyJWKClientConnectionError as exc:
        logger.error("No se pudo conectar al endpoint JWKS: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo verificar el token: el servidor de identidad no está disponible.",
        )
    except jwt.PyJWTError as exc:
        logger.warning("Token JWT inválido: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[dict]:
    """
    Dependencia FastAPI para proteger endpoints.

    - AUTH_REQUIRED=false (default):  permite cualquier request (modo desarrollo).
    - AUTH_REQUIRED=true:             exige Bearer JWT válido firmado por el proveedor
                                      configurado en AUTH_JWKS_URL / AUTH_AUDIENCE / AUTH_ISSUER.

    Para proteger un router completo:
        router = APIRouter(dependencies=[Depends(require_auth)])

    Para proteger un endpoint puntual:
        @router.post("/ruta")
        async def handler(payload: dict = Depends(require_auth)):
            ...
    """
    if not settings.auth_required:
        return None  # modo desarrollo — sin validación

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _validate_token(credentials.credentials)
