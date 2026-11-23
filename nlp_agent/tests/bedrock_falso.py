"""
INV-67 — Un Bedrock simulado (Chat Completions) con `httpx.MockTransport`.

Guarda las peticiones para revisar su forma y su firma, y responde con un guion:
cada respuesta es un texto o una lista de llamadas `(nombre, argumentos)`. Sin
`stream`, un `chat.completion`; con `stream`, eventos SSE como los de la API
compatible con OpenAI: el texto en pedazos, las llamadas con el id y el nombre
primero y los argumentos por partes, el `finish_reason`, el uso y `[DONE]`.
"""
import json

import httpx
from botocore.credentials import ReadOnlyCredentials

CREDENCIALES = ReadOnlyCredentials("AKIDEXAMPLE", "secreto-de-prueba", None)
CREDENCIALES_TEMPORALES = ReadOnlyCredentials("ASIAEXAMPLE", "secreto-de-prueba", "token-de-sesion")
USO = {"prompt_tokens": 1200, "completion_tokens": 80, "total_tokens": 1280}


def evento(d: dict | str) -> str:
    return f"data: {d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)}\n\n"


def _delta(delta: dict, fin: str | None = None) -> str:
    return evento({"object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": fin}]})


def eventos_de(respuesta, uso: dict = USO) -> list[str]:
    eventos = [_delta({"role": "assistant", "content": ""})]
    if isinstance(respuesta, str):
        mitad = len(respuesta) // 2
        eventos += [_delta({"content": respuesta[:mitad]}), _delta({"content": respuesta[mitad:]}), _delta({}, "stop")]
    else:
        for i, (nombre, argumentos) in enumerate(respuesta):
            texto = json.dumps(argumentos, ensure_ascii=False)
            eventos += [_delta({"tool_calls": [{"index": i, "id": f"call_{i}", "type": "function",
                                                "function": {"name": nombre, "arguments": ""}}]}),
                        _delta({"tool_calls": [{"index": i, "function": {"arguments": texto[:5]}}]}),
                        _delta({"tool_calls": [{"index": i, "function": {"arguments": texto[5:]}}]})]
        eventos.append(_delta({}, "tool_calls"))
    return [*eventos, evento({"object": "chat.completion.chunk", "choices": [], "usage": uso}), evento("[DONE]")]


class BedrockFalso:
    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.guion: list = []                 # vacío: responde «Listo.»
        self.estados: list[int] = []          # códigos que se devuelven, en orden, antes de responder bien
        self.cuerpo_error = '{"error": {"message": "falla simulada", "type": "invalid_request_error"}}'
        self.eventos: list[str] | None = None  # eventos crudos para el próximo stream
        self.mensaje: dict | None = None       # mensaje crudo para la próxima respuesta sin stream
        self.uso = dict(USO)
        self.caido = False

    def cuerpo(self, i: int = -1) -> dict:
        return json.loads(self.peticiones[i].content)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        if self.caido:
            raise httpx.ConnectError("conexión rechazada", request=request)
        if self.estados:
            return httpx.Response(self.estados.pop(0), text=self.cuerpo_error)
        respuesta = self.guion.pop(0) if self.guion else "Listo."
        if not json.loads(request.content).get("stream"):
            mensaje, self.mensaje = self.mensaje, None
            if mensaje is None:
                mensaje = ({"role": "assistant", "content": respuesta} if isinstance(respuesta, str) else
                           {"role": "assistant", "content": None, "tool_calls": [
                               {"id": f"call_{i}", "type": "function",
                                "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}}
                               for i, (n, a) in enumerate(respuesta)]})
            return httpx.Response(200, json={"object": "chat.completion", "usage": self.uso,
                                             "choices": [{"index": 0, "message": mensaje, "finish_reason": "stop"}]})
        eventos, self.eventos = self.eventos, None
        return httpx.Response(200, content="".join(eventos or eventos_de(respuesta, self.uso)).encode(),
                              headers={"content-type": "text/event-stream"})
