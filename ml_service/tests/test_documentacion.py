"""INV-41 (D10) — Como en el Core API, la documentación interactiva y el OpenAPI solo se sirven con
ENTORNO=desarrollo (docs/INV-41-requerimientos.md)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import rutas_de_documentacion

RUTAS = ("/api/docs", "/api/redoc", "/api/openapi.json")


@pytest.mark.parametrize("entorno", ["staging", "produccion"])
def test_fuera_de_desarrollo_no_hay_documentacion(entorno):
    cliente = TestClient(FastAPI(**rutas_de_documentacion(entorno)))
    assert [cliente.get(r).status_code for r in RUTAS] == [404, 404, 404]


def test_en_desarrollo_se_sirve():
    cliente = TestClient(FastAPI(**rutas_de_documentacion("desarrollo")))
    assert [cliente.get(r).status_code for r in RUTAS] == [200, 200, 200]
