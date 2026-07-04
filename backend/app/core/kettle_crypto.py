# Ofuscación reversible de passwords en archivos .ktr/.kjb de Pentaho Kettle/PDI
# (Encr / KettleTwoWayPasswordEncoder). Constante pública del código fuente
# Apache-2.0 de Pentaho, sin cambios desde Kettle 2.x hasta PDI 9.x — NO es
# cifrado, es ofuscación: cualquiera con este algoritmo revierte el password.
# El .ktr generado debe tratarse como archivo sensible.
#
# Verificado byte a byte contra vectores oficiales exportados de Spoon 9.x
# (ver tests/test_kettle_crypto.py).
from __future__ import annotations

_SEED = int("0933910847463829827159347601486730416058")
_PREFIX = "Encrypted "


def _is_variable_reference(pw: str) -> bool:
    return ("${" in pw and "}" in pw) or "%%" in pw


def encode(password: str) -> str:
    """Ofusca un password en claro al formato que escribe Spoon en <password>.

    Passwords vacíos o que referencian variables Kettle (${VAR}, %%VAR%%) se
    devuelven sin modificar — Spoon tampoco los ofusca.
    """
    if password == "" or _is_variable_reference(password):
        return password
    n = int.from_bytes(password.encode("latin-1"), byteorder="big", signed=True)
    r1 = _SEED ^ n
    return _PREFIX + format(r1, "x")


def decode(value: str) -> str:
    """Revierte encode(). Acepta el valor con o sin el prefijo 'Encrypted '."""
    if value == "" or _is_variable_reference(value):
        return value
    hex_part = value[len(_PREFIX):] if value.startswith(_PREFIX) else value
    r0 = int(hex_part, 16) ^ _SEED
    nbytes = (r0.bit_length() + 8) // 8 or 1
    return r0.to_bytes(nbytes, byteorder="big", signed=True).decode("latin-1")
