"""INV-66 (CA 1 y 2) — Secretos por entorno y CORS por variable (docs/INV-66-requerimientos.md, P1 a P7)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from core.config import CLAVE_BD_DESARROLLO, CLAVE_JWT_DESARROLLO, Settings
from main import configurar_cors

CLAVE_BUENA = "x" * 32
SECRETOS = ("ENTORNO", "JWT_SECRET_KEY", "POSTGRES_PASSWORD", "CORS_ORIGENES")


@pytest.fixture(autouse=True)
def sin_variables(monkeypatch):
    """Cada caso fija lo suyo: ni el ENTORNO del conftest ni las variables del contenedor cuentan."""
    for v in SECRETOS:
        monkeypatch.delenv(v, raising=False)


def configuracion(**valores) -> Settings:
    return Settings(_env_file=None, **valores)


def test_sin_entorno_se_asume_produccion_y_exige_los_secretos():
    with pytest.raises(ValidationError) as e:
        configuracion()
    assert "ENTORNO=produccion" in str(e.value)
    assert "JWT_SECRET_KEY" in str(e.value)
    assert "POSTGRES_PASSWORD" in str(e.value)


@pytest.mark.parametrize("entorno", ["staging", "produccion"])
@pytest.mark.parametrize("clave", [CLAVE_JWT_DESARROLLO, "corta", "y" * 31, ""])
def test_fuera_de_desarrollo_rechaza_la_clave_jwt_del_repo_o_corta(entorno, clave):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        configuracion(ENTORNO=entorno, JWT_SECRET_KEY=clave, POSTGRES_PASSWORD="otra-clave")


@pytest.mark.parametrize("clave_bd", [CLAVE_BD_DESARROLLO, ""])
def test_fuera_de_desarrollo_rechaza_la_contrasena_de_la_base_del_repo_o_vacia(clave_bd):
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        configuracion(ENTORNO="produccion", JWT_SECRET_KEY=CLAVE_BUENA, POSTGRES_PASSWORD=clave_bd)


def test_el_error_no_muestra_los_secretos():
    with pytest.raises(ValidationError) as e:
        configuracion(ENTORNO="produccion", JWT_SECRET_KEY="corta", POSTGRES_PASSWORD="contrasena-real-de-la-nube")
    assert "contrasena-real-de-la-nube" not in str(e.value)
    assert "corta" not in str(e.value).replace("ENTORNO", "")


def test_produccion_con_secretos_propios_arranca():
    s = configuracion(ENTORNO="produccion", JWT_SECRET_KEY=CLAVE_BUENA, POSTGRES_PASSWORD="otra-clave")
    assert s.ENTORNO == "produccion"
    assert s.ORIGENES_CORS == []


def test_desarrollo_acepta_los_valores_por_defecto():
    s = configuracion(ENTORNO="desarrollo")
    assert (s.JWT_SECRET_KEY, s.POSTGRES_PASSWORD) == (CLAVE_JWT_DESARROLLO, CLAVE_BD_DESARROLLO)


def test_un_entorno_desconocido_no_arranca():
    with pytest.raises(ValidationError, match="ENTORNO"):
        configuracion(ENTORNO="prod", JWT_SECRET_KEY=CLAVE_BUENA, POSTGRES_PASSWORD="otra-clave")


def test_cors_con_asterisco_solo_en_desarrollo():
    with pytest.raises(ValidationError, match="CORS_ORIGENES"):
        configuracion(ENTORNO="staging", JWT_SECRET_KEY=CLAVE_BUENA, POSTGRES_PASSWORD="otra-clave",
                      CORS_ORIGENES="https://a.co, *")
    assert configuracion(ENTORNO="desarrollo", CORS_ORIGENES="*").ORIGENES_CORS == ["*"]


def test_origenes_cors_se_separan_por_comas():
    s = configuracion(ENTORNO="desarrollo", CORS_ORIGENES=" https://a.co ,, http://localhost:5173 ")
    assert s.ORIGENES_CORS == ["https://a.co", "http://localhost:5173"]


# ── CORS (CA 2) ─────────────────────────────────────

def cliente_con_cors(origenes: list[str]) -> TestClient:
    app = FastAPI()
    configurar_cors(app, origenes)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return TestClient(app)


def preflight(cliente: TestClient, origen: str):
    return cliente.options("/api/health", headers={"Origin": origen, "Access-Control-Request-Method": "GET"})


def test_sin_origenes_no_hay_cors():
    cliente = cliente_con_cors([])
    assert "access-control-allow-origin" not in preflight(cliente, "https://a.co").headers
    r = cliente.get("/api/health", headers={"Origin": "https://a.co"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers


def test_con_origen_configurado_solo_ese_origen_pasa():
    cliente = cliente_con_cors(["https://a.co"])
    permitido = preflight(cliente, "https://a.co")
    assert permitido.status_code == 200
    assert permitido.headers["access-control-allow-origin"] == "https://a.co"
    assert "access-control-allow-credentials" not in permitido.headers

    rechazado = preflight(cliente, "https://b.co")
    assert rechazado.status_code == 400
    assert "access-control-allow-origin" not in rechazado.headers
