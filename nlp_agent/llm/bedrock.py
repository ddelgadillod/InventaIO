"""
Cliente de Amazon Bedrock (INV-67).

`ClienteBedrock` implementa `ClienteLLM` sobre Chat Completions, la API compatible
con OpenAI: la ficha de Qwen3-32B lista ahí el llamado a herramientas y no en
Converse (B1). Cada petición se firma con SigV4; las credenciales salen de la
cadena estándar de AWS (variables, AWS_PROFILE o el rol de la EC2), nunca del
repositorio (B4). El bucle le pasa los mensajes en el formato de Ollama y la
traducción vive aquí (B7), así que el agente no cambia. Decisiones en
docs/INV-67-requerimientos.md.
"""
import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable

import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import ReadOnlyCredentials
from botocore.exceptions import BotoCoreError
from botocore.session import Session

from core.config import Settings
from llm.cliente import ErrorLLM, FragmentoLLM, Metricas, RespuestaLLM, _llamadas
from llm.razonamiento import FiltroRazonamiento

# B6: la URL base de Chat Completions y el servicio con que se firma
ENDPOINTS = {
    "runtime": ("https://bedrock-runtime.{region}.amazonaws.com/openai/v1", "bedrock"),
    "mantle": ("https://bedrock-mantle.{region}.api.aws/v1", "bedrock-mantle"),
}
# B9: una cuenta nueva tiene cuotas bajas. Solo antes de recibir respuesta, nunca a mitad del stream
REINTENTABLES = {429, 503}
ESPERAS_S = (1.0, 2.0)


class CadenaAWS:
    """Las credenciales de la cadena estándar de botocore. En la EC2 se renuevan solas al vencer."""

    def __init__(self) -> None:
        self._credenciales = None

    def __call__(self) -> ReadOnlyCredentials | None:
        try:
            if self._credenciales is None:
                self._credenciales = Session().get_credentials()
            return self._credenciales.get_frozen_credentials() if self._credenciales else None
        except BotoCoreError:          # p. ej. un AWS_PROFILE que no existe
            return None


def costo_usd(settings: Settings, entrada: int, salida: int) -> float:
    """B11: con los precios configurados (US$ por millón de tokens)."""
    return (entrada * settings.BEDROCK_PRECIO_ENTRADA + salida * settings.BEDROCK_PRECIO_SALIDA) / 1e6


def a_chat_completions(mensajes: list[dict]) -> list[dict]:
    """B7: del formato que arma el bucle (el de Ollama) al de Chat Completions. Las llamadas llevan
    `type` e `id` y los argumentos como texto JSON; cada resultado, el `tool_call_id` de su llamada,
    emparejado en orden (el bucle agrega los resultados en el orden de las llamadas)."""
    salida, pendientes, n = [], [], 0
    for m in mensajes:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            llamadas = []
            for ll in m["tool_calls"]:
                n += 1
                funcion = ll.get("function", {})
                argumentos = funcion.get("arguments", {})
                llamadas.append({
                    "id": ll.get("id") or f"llamada-{n}", "type": "function",
                    "function": {"name": funcion.get("name", ""),
                                 "arguments": argumentos if isinstance(argumentos, str)
                                 else json.dumps(argumentos, ensure_ascii=False)},
                })
            pendientes = list(llamadas)
            salida.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": llamadas})
        elif m.get("role") == "tool":
            if not pendientes:
                raise ErrorLLM("solicitud_invalida", "resultado de herramienta sin una llamada que lo pida")
            i = next((k for k, ll in enumerate(pendientes) if ll["function"]["name"] == m.get("tool_name")), 0)
            salida.append({"role": "tool", "tool_call_id": pendientes.pop(i)["id"], "content": m.get("content", "")})
        else:
            salida.append({"role": m["role"], "content": m.get("content", "")})
    return salida


def _detalle(cuerpo: str) -> str:
    try:
        d = json.loads(cuerpo)
    except json.JSONDecodeError:
        return cuerpo[:300]
    if isinstance(d, dict):
        error = d.get("error")
        d = error.get("message", error) if isinstance(error, dict) else error or d.get("message", d)
    return str(d)[:300]


def _error_http(status: int, cuerpo: str) -> ErrorLLM:
    """B8: solo los códigos que ya existen, porque el Core API los traduce para el usuario."""
    detalle = _detalle(cuerpo)
    if status == 404:
        return ErrorLLM("modelo_no_descargado", detalle)
    if status in (400, 422):
        return ErrorLLM("solicitud_invalida", detalle)
    if status in (401, 403):
        return ErrorLLM("llm_no_disponible", f"Bedrock rechazó las credenciales o el permiso ({status}): {detalle}")
    if status == 429:
        return ErrorLLM("llm_no_disponible", f"Bedrock limitó las peticiones (429): {detalle}")
    return ErrorLLM("llm_no_disponible", f"Bedrock respondió {status}")


class ClienteBedrock:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None,
                 credenciales: Callable[[], ReadOnlyCredentials | None] | None = None):
        self._s = settings
        base, self._servicio = ENDPOINTS[settings.BEDROCK_ENDPOINT]
        self._url = base.format(region=settings.BEDROCK_REGION) + "/chat/completions"
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(settings.LLM_TIMEOUT_S, connect=5.0), transport=transport)
        self._credenciales = credenciales or CadenaAWS()
        self._dormir = asyncio.sleep
        # B11: lo que lleva consumido el cliente; el arnés lo lee antes y después de cada pregunta
        self.uso = {"tokens_entrada": 0, "tokens_salida": 0, "peticiones": 0}

    def _cuerpo(self, mensajes, stream: bool, herramientas=None) -> dict:
        cuerpo = {
            "model": self._s.LLM_MODELO,
            "messages": a_chat_completions(mensajes),
            "stream": stream,
            "temperature": self._s.LLM_TEMPERATURA,
            "top_p": self._s.LLM_TOP_P,
            "max_tokens": self._s.LLM_TOPE_RESPUESTA,
        }
        if stream:
            cuerpo["stream_options"] = {"include_usage": True}
        if herramientas:
            cuerpo["tools"] = herramientas
        return {**cuerpo, **self._s.BEDROCK_CUERPO_EXTRA}

    def _firmadas(self, datos: bytes) -> dict:
        credenciales = self._credenciales()
        if credenciales is None:
            raise ErrorLLM("llm_no_disponible", "no hay credenciales de AWS (AWS_PROFILE, variables o el rol de la EC2)")
        pedido = AWSRequest(method="POST", url=self._url, data=datos, headers={"Content-Type": "application/json"})
        SigV4Auth(credenciales, self._servicio, self._s.BEDROCK_REGION).add_auth(pedido)
        return dict(pedido.headers.items())

    async def _enviar(self, cuerpo: dict, stream: bool) -> httpx.Response:
        """La respuesta con 200; con `stream`, quien llama la cierra. Se firma en cada intento (x-amz-date)."""
        datos = json.dumps(cuerpo, ensure_ascii=False).encode()
        for intento in range(len(ESPERAS_S) + 1):
            pedido = self._http.build_request("POST", self._url, content=datos, headers=self._firmadas(datos))
            try:
                r = await self._http.send(pedido, stream=stream)
            except httpx.TimeoutException as exc:
                raise ErrorLLM("tiempo_agotado", "el modelo no respondió a tiempo") from exc
            except httpx.TransportError as exc:
                raise ErrorLLM("llm_no_disponible", "Bedrock no es alcanzable") from exc
            if r.status_code == 200:
                return r
            texto = (await r.aread()).decode(errors="replace")
            await r.aclose()
            if r.status_code in REINTENTABLES and intento < len(ESPERAS_S):
                await self._dormir(ESPERAS_S[intento])
                continue
            raise _error_http(r.status_code, texto)

    def _metricas(self, uso: dict | None, inicio: float, primero: float | None = None) -> Metricas:
        uso = uso or {}
        entrada, salida = uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0)
        self.uso["tokens_entrada"] += entrada
        self.uso["tokens_salida"] += salida
        self.uso["peticiones"] += 1
        fin = time.monotonic()
        primero = primero or fin
        return Metricas(tokens_prompt=entrada, tokens_respuesta=salida, ms_prompt=round((primero - inicio) * 1000, 1),
                        ms_respuesta=round((fin - primero) * 1000, 1), ms_total=round((fin - inicio) * 1000, 1))

    async def version(self) -> str:
        """B10: sin llamar al modelo, porque el Core API consulta /ready. Sin credenciales, no está listo."""
        if self._credenciales() is None:
            raise ErrorLLM("llm_no_disponible", "no hay credenciales de AWS")
        return f"bedrock {self._s.BEDROCK_ENDPOINT} {self._s.BEDROCK_REGION}"

    async def modelo_disponible(self, modelo: str) -> bool:
        # Un modelo que no existe en la región responde 404 en el primer chat (modelo_no_descargado)
        return self._credenciales() is not None

    async def chat(self, mensajes, herramientas=None, opciones=None) -> RespuestaLLM:
        # `opciones` son de Ollama (num_gpu): aquí no aplican
        inicio = time.monotonic()
        r = await self._enviar(self._cuerpo(mensajes, False, herramientas), stream=False)
        try:
            d = r.json()
        except json.JSONDecodeError as exc:
            raise ErrorLLM("respuesta_invalida", "Bedrock respondió algo que no es JSON") from exc
        mensaje = ((d.get("choices") or [{}])[0]).get("message") or {}
        filtro = FiltroRazonamiento()
        texto = filtro.filtrar(mensaje.get("content") or "") + filtro.cerrar()
        return RespuestaLLM(
            texto=texto.strip(),
            llamadas=_llamadas(mensaje),
            metricas=self._metricas(d.get("usage"), inicio),
            razonamiento_filtrado=filtro.hubo_razonamiento or bool(mensaje.get("reasoning_content") or mensaje.get("reasoning")),
        )

    async def chat_stream(self, mensajes, opciones=None, herramientas=None, razonar: bool | None = None) -> AsyncIterator[FragmentoLLM]:
        # `razonar` (P7 de INV-33) no tiene equivalente documentado en Bedrock: va por BEDROCK_CUERPO_EXTRA (B14)
        filtro = FiltroRazonamiento()
        inicio, primero = time.monotonic(), None
        parciales: dict[int, dict] = {}
        uso, terminado, razonamiento = None, False, False
        r = await self._enviar(self._cuerpo(mensajes, True, herramientas), stream=True)
        try:
            async for linea in r.aiter_lines():
                if not linea.startswith("data:"):
                    continue
                dato = linea[5:].strip()
                if dato == "[DONE]":
                    terminado = True
                    break
                try:
                    d = json.loads(dato)
                except json.JSONDecodeError as exc:
                    raise ErrorLLM("respuesta_invalida", "Bedrock envió un evento que no es JSON") from exc
                if "error" in d:
                    raise ErrorLLM("respuesta_invalida", _detalle(dato))
                uso = d.get("usage") or uso
                for eleccion in d.get("choices") or []:
                    delta = eleccion.get("delta") or {}
                    if primero is None and (delta.get("content") or delta.get("tool_calls")):
                        primero = time.monotonic()
                    razonamiento |= bool(delta.get("reasoning_content") or delta.get("reasoning"))
                    # Las llamadas llegan por partes: el id y el nombre primero, los argumentos en pedazos
                    for parte in delta.get("tool_calls") or []:
                        ll = parciales.setdefault(parte.get("index", 0), {"id": None, "function": {"name": "", "arguments": ""}})
                        ll["id"] = parte.get("id") or ll["id"]
                        funcion = parte.get("function") or {}
                        ll["function"]["name"] += funcion.get("name") or ""
                        ll["function"]["arguments"] += funcion.get("arguments") or ""
                    if texto := filtro.filtrar(delta.get("content") or ""):
                        yield FragmentoLLM(texto=texto)
                    terminado |= bool(eleccion.get("finish_reason"))
        except httpx.TimeoutException as exc:
            raise ErrorLLM("tiempo_agotado", "el modelo no respondió a tiempo") from exc
        except httpx.TransportError as exc:
            raise ErrorLLM("llm_no_disponible", "Bedrock no es alcanzable") from exc
        finally:
            await r.aclose()
        if not terminado:
            raise ErrorLLM("respuesta_invalida", "el stream de Bedrock terminó sin final")
        if resto := filtro.cerrar():
            yield FragmentoLLM(texto=resto)
        if parciales:
            # Como con Ollama 0.40.5: las llamadas en su propio fragmento, antes del final
            yield FragmentoLLM(llamadas=_llamadas({"tool_calls": [parciales[i] for i in sorted(parciales)]}))
        yield FragmentoLLM(fin=True, metricas=self._metricas(uso, inicio, primero),
                           razonamiento_filtrado=filtro.hubo_razonamiento or razonamiento)

    async def cerrar(self) -> None:
        await self._http.aclose()
