"""
INV-30 — Fixtures compartidos.

- `OllamaFalso`: un Ollama simulado con `httpx.MockTransport`. Guarda las
  peticiones para revisar su forma y responde lo que cada prueba configure
  (versión, modelos, respuesta normal o en stream, códigos de error, caída).
- `cliente`: el `ClienteOllama` real contra ese Ollama simulado.
- `core`: el `ClienteCoreAPI` real contra un Core API simulado (`CoreFalso`,
  INV-32), y `ctx`, el contexto de una pregunta del gerente.
- `api`: un TestClient de la app con esos dos clientes. Ninguna prueba de este
  archivo necesita Ollama; las de la marca `llm` (test_llm_real.py) sí.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from core.config import Settings, get_settings
from herramientas.contexto import Contexto
from herramientas.core_api import ClienteCoreAPI
from llm.cliente import ClienteOllama
from main import crear_app
from tests.core_falso import CoreFalso

TOKEN = {"Authorization": "Bearer token-de-prueba"}


def linea(d: dict) -> bytes:
    return (json.dumps(d) + "\n").encode()


def fin_ollama(**extra) -> dict:
    return {
        "done": True, "prompt_eval_count": 40, "eval_count": 12, "load_duration": 2_000_000,
        "prompt_eval_duration": 30_000_000, "eval_duration": 240_000_000, "total_duration": 280_000_000,
        **extra,
    }


class OllamaFalso:
    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.version = "0.40.5"
        self.modelos = ["qwen3:8b", "llama3.1:8b"]
        self.fragmentos = ["¡Hola", "! ¿En qué", " te ayudo?"]
        self.respuesta = {"message": {"role": "assistant", "content": "Hola"}, **fin_ollama()}
        self.status = 200
        self.cuerpo_error = '{"error":"falla simulada"}'
        self.lineas_stream: list[bytes] | None = None
        self.caido = False

    def cuerpo(self, i: int = -1) -> dict:
        return json.loads(self.peticiones[i].content)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        if self.caido:
            raise httpx.ConnectError("conexión rechazada", request=request)
        if self.status != 200:
            return httpx.Response(self.status, text=self.cuerpo_error)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": self.version})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": m, "digest": "500a1f067a9fdeadbeef", "size": 5_230_000_000, "details": {"parameter_size": "8.2B"}}
                for m in self.modelos]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "size": 6_190_000_000, "size_vram": 6_190_000_000}]})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/chat":
            if not json.loads(request.content).get("stream"):
                return httpx.Response(200, json=self.respuesta)
            lineas = self.lineas_stream
            if lineas is None:
                lineas = [linea({"done": False, "message": {"role": "assistant", "content": f}}) for f in self.fragmentos]
                lineas.append(linea({**fin_ollama(), "message": {"role": "assistant", "content": ""}}))
            return httpx.Response(200, content=b"".join(lineas))
        return httpx.Response(404, text="ruta desconocida")


@pytest.fixture
def ajustes() -> Settings:
    return Settings(OLLAMA_BASE_URL="http://ollama-falso:11434", CORE_API_URL="http://core-falso:8000")


@pytest.fixture
def ollama() -> OllamaFalso:
    return OllamaFalso()


@pytest.fixture
def cliente(ajustes, ollama) -> ClienteOllama:
    return ClienteOllama(ajustes, transport=httpx.MockTransport(ollama))


@pytest.fixture
def core_api() -> CoreFalso:
    return CoreFalso()


@pytest.fixture
def core(ajustes, core_api) -> ClienteCoreAPI:
    return ClienteCoreAPI(ajustes, transport=httpx.MockTransport(core_api))


@pytest.fixture
def ctx(core) -> Contexto:
    return Contexto(core, TOKEN["Authorization"], "req-1")


@pytest.fixture
def api(cliente, core):
    with TestClient(crear_app(cliente, core)) as tc:
        yield tc


@pytest.fixture
def entorno(monkeypatch):
    """Cambia variables de entorno de la configuración y limpia la caché de get_settings."""
    def poner(**valores):
        for k, v in valores.items():
            monkeypatch.setenv(k, str(v))
        get_settings.cache_clear()
    yield poner
    get_settings.cache_clear()


def eventos_sse(texto: str) -> list[tuple[str, dict]]:
    """Convierte el cuerpo SSE en una lista de (evento, datos)."""
    salida = []
    for bloque in texto.strip().split("\n\n"):
        campos = dict(l.split(": ", 1) for l in bloque.splitlines() if ": " in l)  # noqa: E741
        salida.append((campos["event"], json.loads(campos["data"])))
    return salida
