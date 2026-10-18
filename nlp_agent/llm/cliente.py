"""
Cliente del modelo de lenguaje (INV-30).

`ClienteLLM` es la interfaz que usan el chat, las herramientas (INV-32) y el
arnés del spike. `ClienteOllama` la implementa con la API nativa de Ollama
(`/api/chat`): trae `think`, `keep_alive`, `options.num_gpu` y los tiempos de
lectura del prompt y de generación que pide el criterio 3 (decisión W11, ajuste
a N5 y N8). Un adaptador compatible con OpenAI se agrega en INV-34 si el perfil
de producción lo necesita.
"""
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from core.config import Settings
from llm.razonamiento import FiltroRazonamiento


class ErrorLLM(Exception):
    """Falla del modelo con un código estable para el evento `error` del chat."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass
class Metricas:
    tokens_prompt: int = 0
    tokens_respuesta: int = 0
    ms_carga: float = 0.0
    ms_prompt: float = 0.0
    ms_respuesta: float = 0.0
    ms_total: float = 0.0

    @classmethod
    def de_ollama(cls, d: dict) -> "Metricas":
        ms = lambda clave: round(d.get(clave, 0) / 1e6, 1)  # noqa: E731 — Ollama mide en ns
        return cls(
            tokens_prompt=d.get("prompt_eval_count", 0),
            tokens_respuesta=d.get("eval_count", 0),
            ms_carga=ms("load_duration"),
            ms_prompt=ms("prompt_eval_duration"),
            ms_respuesta=ms("eval_duration"),
            ms_total=ms("total_duration"),
        )


@dataclass
class LlamadaHerramienta:
    nombre: str
    argumentos: dict[str, Any]


@dataclass
class RespuestaLLM:
    texto: str
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)
    metricas: Metricas = field(default_factory=Metricas)
    razonamiento_filtrado: bool = False


@dataclass
class FragmentoLLM:
    texto: str = ""
    fin: bool = False
    metricas: Metricas | None = None


class ClienteLLM(Protocol):
    async def version(self) -> str: ...

    async def modelo_disponible(self, modelo: str) -> bool: ...

    async def chat(
        self, mensajes: list[dict], herramientas: list[dict] | None = None, opciones: dict | None = None
    ) -> RespuestaLLM: ...

    def chat_stream(self, mensajes: list[dict], opciones: dict | None = None) -> AsyncIterator[FragmentoLLM]: ...

    async def cerrar(self) -> None: ...


def _con_tag(modelo: str) -> str:
    return modelo if ":" in modelo else f"{modelo}:latest"


def _argumentos(crudos: Any) -> dict:
    # Algunos modelos devuelven los argumentos como texto JSON (INV-32, criterio 13)
    if isinstance(crudos, str):
        try:
            crudos = json.loads(crudos) if crudos.strip() else {}
        except json.JSONDecodeError as exc:
            raise ErrorLLM("respuesta_invalida", "argumentos de herramienta que no son JSON") from exc
    if not isinstance(crudos, dict):
        raise ErrorLLM("respuesta_invalida", "argumentos de herramienta que no son un objeto")
    return crudos


def _error_http(status: int, cuerpo: str) -> ErrorLLM:
    try:
        detalle = json.loads(cuerpo).get("error", cuerpo)
    except (json.JSONDecodeError, AttributeError):
        detalle = cuerpo
    if status == 404:
        return ErrorLLM("modelo_no_descargado", str(detalle))
    if status == 400:
        return ErrorLLM("solicitud_invalida", str(detalle))
    return ErrorLLM("llm_no_disponible", f"Ollama respondió {status}")


class ClienteOllama:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._s = settings
        self._http = httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=httpx.Timeout(settings.LLM_TIMEOUT_S, connect=5.0),
            transport=transport,
        )

    def _cuerpo(self, mensajes, stream: bool, herramientas=None, opciones=None) -> dict:
        cuerpo = {
            "model": self._s.LLM_MODELO,
            "messages": mensajes,
            "stream": stream,
            "think": self._s.LLM_RAZONAMIENTO,
            "keep_alive": self._s.LLM_KEEP_ALIVE,
            "options": {
                "num_ctx": self._s.LLM_NUM_CTX,
                "temperature": self._s.LLM_TEMPERATURA,
                "top_p": self._s.LLM_TOP_P,
                "seed": self._s.LLM_SEMILLA,
                **(opciones or {}),        # p. ej. num_gpu=0 para medir sin GPU (W12)
            },
        }
        if herramientas:
            cuerpo["tools"] = herramientas
        return cuerpo

    async def _get(self, ruta: str) -> dict:
        try:
            r = await self._http.get(ruta, timeout=5.0)
        except httpx.TimeoutException as exc:
            raise ErrorLLM("tiempo_agotado", "Ollama no respondió a tiempo") from exc
        except httpx.TransportError as exc:
            raise ErrorLLM("llm_no_disponible", "Ollama no es alcanzable") from exc
        if r.status_code != 200:
            raise _error_http(r.status_code, r.text)
        return r.json()

    async def version(self) -> str:
        return (await self._get("/api/version")).get("version", "")

    async def modelo_disponible(self, modelo: str) -> bool:
        modelos = (await self._get("/api/tags")).get("models", [])
        nombres = {_con_tag(m.get("name") or m.get("model", "")) for m in modelos}
        return _con_tag(modelo) in nombres

    async def chat(self, mensajes, herramientas=None, opciones=None) -> RespuestaLLM:
        try:
            r = await self._http.post("/api/chat", json=self._cuerpo(mensajes, False, herramientas, opciones))
        except httpx.TimeoutException as exc:
            raise ErrorLLM("tiempo_agotado", "el modelo no respondió a tiempo") from exc
        except httpx.TransportError as exc:
            raise ErrorLLM("llm_no_disponible", "Ollama no es alcanzable") from exc
        if r.status_code != 200:
            raise _error_http(r.status_code, r.text)
        d = r.json()
        mensaje = d.get("message", {})
        filtro = FiltroRazonamiento()
        texto = filtro.filtrar(mensaje.get("content", "")) + filtro.cerrar()
        llamadas = [
            LlamadaHerramienta(nombre=ll["function"]["name"], argumentos=_argumentos(ll["function"].get("arguments", {})))
            for ll in mensaje.get("tool_calls") or []
        ]
        return RespuestaLLM(
            texto=texto.strip(),
            llamadas=llamadas,
            metricas=Metricas.de_ollama(d),
            razonamiento_filtrado=filtro.hubo_razonamiento,
        )

    async def chat_stream(self, mensajes, opciones=None) -> AsyncIterator[FragmentoLLM]:
        filtro = FiltroRazonamiento()
        try:
            async with self._http.stream("POST", "/api/chat", json=self._cuerpo(mensajes, True, None, opciones)) as r:
                if r.status_code != 200:
                    raise _error_http(r.status_code, (await r.aread()).decode(errors="replace"))
                async for linea in r.aiter_lines():
                    if not linea.strip():
                        continue
                    try:
                        d = json.loads(linea)
                    except json.JSONDecodeError as exc:
                        raise ErrorLLM("respuesta_invalida", "Ollama envió una línea que no es JSON") from exc
                    if "error" in d:
                        raise ErrorLLM("respuesta_invalida", str(d["error"]))
                    texto = filtro.filtrar(d.get("message", {}).get("content", ""))
                    if d.get("done"):
                        texto += filtro.cerrar()
                        if texto:
                            yield FragmentoLLM(texto=texto)
                        yield FragmentoLLM(fin=True, metricas=Metricas.de_ollama(d))
                        return
                    if texto:
                        yield FragmentoLLM(texto=texto)
        except httpx.TimeoutException as exc:
            raise ErrorLLM("tiempo_agotado", "el modelo no respondió a tiempo") from exc
        except httpx.TransportError as exc:
            raise ErrorLLM("llm_no_disponible", "Ollama no es alcanzable") from exc
        raise ErrorLLM("respuesta_invalida", "el stream de Ollama terminó sin `done`")

    async def cerrar(self) -> None:
        await self._http.aclose()
