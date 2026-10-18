"""
Pruebas con el modelo real (marca `llm`): solo en local, con Ollama corriendo y
el modelo de LLM_MODELO descargado; si no, se saltan. Nunca en el CI.
    bash scripts/ollama_wsl.sh iniciar
    cd nlp_agent && OLLAMA_BASE_URL=http://localhost:11434 pytest -m llm
"""
import asyncio

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
