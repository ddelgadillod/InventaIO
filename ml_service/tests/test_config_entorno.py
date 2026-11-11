"""INV-66 (CA 1 y 2) — Contraseña de la base por entorno y servicio sin CORS (docs/INV-66-requerimientos.md)."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.config import CLAVE_BD_DESARROLLO, Settings


@pytest.fixture(autouse=True)
def sin_variables(monkeypatch):
    for v in ("ENTORNO", "POSTGRES_PASSWORD"):
        monkeypatch.delenv(v, raising=False)


def configuracion(**valores) -> Settings:
    return Settings(_env_file=None, **valores)


@pytest.mark.parametrize("valores", [{}, {"ENTORNO": "staging"}, {"ENTORNO": "produccion", "POSTGRES_PASSWORD": ""}])
def test_fuera_de_desarrollo_exige_una_contrasena_propia(valores):
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        configuracion(**valores)


def test_el_error_no_muestra_las_variables_de_entrada():
    with pytest.raises(ValidationError) as e:
        configuracion(ENTORNO="produccion", POSTGRES_PASSWORD="", POSTGRES_USER="usuario-de-la-nube")
    assert "usuario-de-la-nube" not in str(e.value)


def test_produccion_con_contrasena_propia_y_desarrollo_con_la_del_repo():
    assert configuracion(ENTORNO="produccion", POSTGRES_PASSWORD="otra-clave").ENTORNO == "produccion"
    assert configuracion(ENTORNO="desarrollo").POSTGRES_PASSWORD == CLAVE_BD_DESARROLLO


def test_un_entorno_desconocido_no_arranca():
    with pytest.raises(ValidationError, match="ENTORNO"):
        configuracion(ENTORNO="prod", POSTGRES_PASSWORD="otra-clave")


def test_el_servicio_no_responde_cors_a_ningun_origen(monkeypatch):
    # Sin `with`: no corre el lifespan (modelos y bodega); el middleware de CORS respondería antes de las rutas
    monkeypatch.setenv("ENTORNO", "desarrollo")
    from main import app

    r = TestClient(app).options("/api/health", headers={"Origin": "https://a.co",
                                                        "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
