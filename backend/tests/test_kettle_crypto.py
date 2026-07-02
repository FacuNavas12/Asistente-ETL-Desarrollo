"""
Unit tests para app/core/kettle_crypto.py — ofuscación de passwords Kettle.
Vectores oficiales verificados contra export real de Spoon 9.x.
"""
import random

import pytest

from app.core.kettle_crypto import decode, encode

VECTORS = [
    ("abcd", "Encrypted 2be98afc86aa7f2e4cb79ce10df90acde"),
    ("pg_test_pw", "Encrypted 2be98afc86aa78283940dab63caadbfcd"),
    ("mssql_test_pw", "Encrypted 2be98afa519d48388940dab63caadbfcd"),
]


@pytest.mark.parametrize("plain,expected", VECTORS)
def test_encode_matches_official_vector(plain, expected):
    assert encode(plain) == expected


@pytest.mark.parametrize("plain,expected", VECTORS)
def test_decode_matches_official_vector(plain, expected):
    assert decode(expected) == plain


@pytest.mark.parametrize("plain,expected", VECTORS)
def test_decode_accepts_hash_without_prefix(plain, expected):
    hex_only = expected[len("Encrypted "):]
    assert decode(hex_only) == plain


def test_empty_password_not_obfuscated():
    assert encode("") == ""
    assert decode("") == ""


@pytest.mark.parametrize("ref", ["${DB_PASSWORD}", "%%DB_PASSWORD%%", "prefix_${VAR}_suffix"])
def test_variable_reference_left_as_is(ref):
    assert encode(ref) == ref
    assert decode(ref) == ref


def test_roundtrip_property_ascii_printable():
    rng = random.Random(42)
    charset = [chr(c) for c in range(33, 127)]  # ASCII imprimible, sin espacios
    for _ in range(200):
        length = rng.randint(1, 24)
        pw = "".join(rng.choice(charset) for _ in range(length))
        assert decode(encode(pw)) == pw
