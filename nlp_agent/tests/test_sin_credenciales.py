"""Criterio 6: el agente no tiene credenciales propias hacia la bodega ni hacia el Core API."""
import re
from pathlib import Path

from core.config import Settings

RAIZ = Path(__file__).resolve().parent.parent


def test_la_configuracion_no_tiene_credenciales():
    campos = set(Settings.model_fields)
    assert not {c for c in campos if re.search(r"POSTGRES|PASSWORD|SECRET|TOKEN|DATABASE|USUARIO", c)}


def test_el_codigo_no_usa_la_bodega():
    codigo = [p for p in RAIZ.rglob("*.py") if "tests" not in p.parts]
    for p in codigo:
        texto = p.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+(psycopg|sqlalchemy|asyncpg)", texto, re.M), p
