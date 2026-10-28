"""Hardening (INV-66) — Los tokens con PyJWT en lugar de python-jose, que tenía una
CVE sin corrección y arrastraba ecdsa (CVE-2024-23342). decode_token devuelve None
ante todo lo que no sea un HS256 vigente firmado con la clave del Core API. Sin base."""
import base64
import json
from datetime import timedelta

import jwt
import pytest

from core.config import get_settings
from core.security import create_access_token, create_refresh_token, decode_token

CLAVE = get_settings().JWT_SECRET_KEY


def _b64(datos: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()


def test_ida_y_vuelta_conserva_los_campos():
    payload = decode_token(create_access_token({"sub": "7", "email": "a@b.co", "rol": "gerente"}))
    assert payload["sub"] == "7" and payload["rol"] == "gerente" and payload["type"] == "access"
    assert isinstance(payload["exp"], int)                                     # INV-36 lee exp como entero
    assert decode_token(create_refresh_token({"sub": "7"}))["type"] == "refresh"


@pytest.mark.parametrize("token", [
    create_access_token({"sub": "1"}, timedelta(seconds=-1)),                  # vencido
    create_access_token({"sub": "1"})[:-2] + "xx",                             # firma alterada
    jwt.encode({"sub": "1", "type": "access"}, "otra-clave-de-al-menos-32-bytes!!", algorithm="HS256"),
    f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({'sub': '1', 'type': 'access'})}.",
    "no-es-un-token",
    "",
])
def test_rechaza_lo_que_no_es_un_hs256_vigente_de_esta_clave(token):
    assert decode_token(token) is None


# PyJWT avisa que la clave es corta para HS512 (pide 64 bytes); para HS256 alcanza con 32
@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
def test_rechaza_otro_algoritmo_con_la_misma_clave():
    assert decode_token(jwt.encode({"sub": "1", "type": "access"}, CLAVE, algorithm="HS512")) is None
