"""
Pruebas con el modelo real (marca `llm`): solo en local, con Ollama corriendo y
el modelo de LLM_MODELO descargado; si no, se saltan. Nunca en el CI.
    bash scripts/ollama_wsl.sh iniciar
    cd nlp_agent && OLLAMA_BASE_URL=http://localhost:11434 pytest -m llm

Las de INV-32 usan además el Core API real con los usuarios de prueba:
    CORE_API_URL=http://localhost:8000 INVENTAIO_CLAVE_PRUEBA=… pytest -m llm
"""
import asyncio
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from core.config import get_settings
from llm.cliente import ClienteOllama, ErrorLLM
from main import crear_app
from tests.conftest import TOKEN, eventos_sse

pytestmark = pytest.mark.llm


@pytest.fixture(scope="module")
def real():
    s = get_settings()

    async def listo():
        c = ClienteOllama(s)
        try:
            return await c.modelo_disponible(s.LLM_MODELO)
        except ErrorLLM:
            return False
        finally:
            await c.cerrar()

    if not asyncio.run(listo()):
        pytest.skip(f"Ollama no responde en {s.OLLAMA_BASE_URL} o falta el modelo {s.LLM_MODELO}")
    with TestClient(crear_app()) as tc:
        yield tc


def test_ready_con_el_modelo_real(real):
    r = real.get("/ready")
    assert r.status_code == 200 and r.json()["status"] == "listo"


def test_hola_de_punta_a_punta(real):
    r = real.post("/chat", json={"mensajes": [{"rol": "usuario", "texto": "Hola, ¿qué puedes hacer?"}]}, headers=TOKEN)
    eventos = eventos_sse(r.text)
    assert eventos[0][0] == "meta" and eventos[-1][0] == "done", eventos[-1]
    texto = "".join(d["texto"] for e, d in eventos if e == "token")
    assert texto.strip() and "<think>" not in texto
    assert eventos[-1][1]["tokens_respuesta"] > 0


USUARIOS = {"gerente": "gerente@inventaio.co", "admin_bodega": "bodega@inventaio.co", "admin_sucursal": "admin.norte@inventaio.co"}


def _token(rol: str) -> str:
    clave, url = os.environ.get("INVENTAIO_CLAVE_PRUEBA"), get_settings().CORE_API_URL
    if not clave:
        pytest.skip("Falta INVENTAIO_CLAVE_PRUEBA para iniciar sesión en el Core API")
    try:
        r = httpx.post(f"{url}/api/auth/login", json={"email": USUARIOS[rol], "password": clave}, timeout=10)
    except httpx.TransportError:
        pytest.skip(f"El Core API no responde en {url}")
    assert r.status_code == 200, r.text
    return f"Bearer {r.json()['access_token']}"


@pytest.mark.parametrize("rol, pregunta", [
    ("gerente", "¿Cuántas alertas críticas hay en GLORIETA?"),
    ("admin_bodega", "¿Qué productos están en estado crítico en la Bodega Central?"),
    ("admin_sucursal", "¿Qué productos están en estado crítico en mi sucursal?"),
])
def test_una_herramienta_de_punta_a_punta_con_los_3_roles(real, rol, pregunta):
    """La regla de corte del 21-oct (documento de Sprint 6, §5), del lado del agente."""
    r = real.post("/chat", json={"mensajes": [{"rol": "usuario", "texto": pregunta}]},
                  headers={"Authorization": _token(rol), "X-Request-Id": f"llm-{rol}"})
    eventos = eventos_sse(r.text)
    nombres = [e for e, _ in eventos]
    assert nombres[0] == "meta" and nombres[-1] == "done", eventos[-1]
    fines = [d for e, d in eventos if e == "tool" and d["estado"] != "inicio"]
    assert fines and all(d["estado"] == "ok" for d in fines), fines
    assert "data" in nombres and "token" in nombres
    assert eventos[-1][1]["fechas_datos"] == ["2025-12-31"] and eventos[-1][1]["rondas"] >= 2
