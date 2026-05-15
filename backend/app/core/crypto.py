# Cómo generar una nueva clave maestra:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#
# Rotación de claves:
#   1. Generá una nueva clave.
#   2. Poné la nueva primera en CREDENTIALS_ENCRYPTION_KEYS: NEW_KEY,OLD_KEY
#   3. A partir de ese momento encrypt_password usa la nueva; decrypt_password acepta ambas.
#   4. Cuando todos los registros estén re-encriptados, eliminá la clave vieja de la lista.
#
# NUNCA commitees estas claves ni las pierdas: los passwords cifrados son irrecuperables sin ellas.

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet

_cipher: MultiFernet | None = None


def _get_cipher() -> MultiFernet:
    global _cipher
    if _cipher is None:
        from app.core.config import settings
        _cipher = MultiFernet(
            [Fernet(k.encode()) for k in settings.credentials_encryption_keys]
        )
    return _cipher


def encrypt_password(plain: str) -> bytes:
    return _get_cipher().encrypt(plain.encode())


def decrypt_password(blob: bytes) -> str:
    return _get_cipher().decrypt(blob).decode()
