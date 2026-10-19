"""
Bucle de herramientas (INV-32, T11). Lo usan el chat y el arnés: lo que se mide
es lo que corre.

Cada ronda va en streaming y con el catálogo. Ollama 0.40.5 entrega una llamada
a herramienta en un fragmento propio y sin texto (medido el 18-oct), así que una
ronda que pide herramientas no transmite nada, y la que responde transmite su
texto a medida que se genera: no hace falta una llamada extra para la respuesta
final. Hasta 3 rondas con herramientas (criterio 6); si se agotan, una última sin
herramientas obliga a responder.

Produce los eventos `tool`, `data` y `token` del contrato v1 (§4.3 de
docs/INV-30-requerimientos.md); `meta`, `done` y `error` los pone el chat. Un
error de herramienta no corta la respuesta: vuelve al modelo como dato, para
que lo explique (criterio 5). Los argumentos inválidos se devuelven con lo que
hay que corregir; al segundo, la ronda siguiente va sin herramientas
(criterio 13).
"""
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from herramientas.base import ErrorArgumentos, Resultado
from herramientas.catalogo import CATALOGO, esquemas
from herramientas.contexto import Contexto
from herramientas.core_api import ErrorHerramienta
from llm.cliente import ClienteLLM, ErrorLLM

MAX_RONDAS = 3
MAX_ARGUMENTOS_INVALIDOS = 2
log = logging.getLogger("nlp_agent.herramientas")


@dataclass
class Preparada:
    """Una llamada lista para ejecutar, o el error que la impide."""
    nombre: str
    argumentos: dict
    params: Any = None
    etiqueta: str = ""
    lenta: bool = False
    error: ErrorHerramienta | None = None
    conocida: bool = True            # una herramienta inventada no se ejecuta ni genera eventos


class Ejecutor(Protocol):
    catalogo: list[dict]             # en el formato de Ollama

    def preparar(self, nombre: str, argumentos: dict) -> Preparada: ...

    async def ejecutar(self, preparada: Preparada) -> Resultado: ...


class EjecutorCoreAPI:
    """Las herramientas reales del catálogo v1, contra el Core API con el token del usuario."""

    def __init__(self, ctx: Contexto, catalogo=CATALOGO):
        self.ctx = ctx
        self._por_nombre = {h.nombre: h for h in catalogo}
        self.catalogo = esquemas() if catalogo is CATALOGO else [h.esquema() for h in catalogo]

    def preparar(self, nombre, argumentos):
        h = self._por_nombre.get(nombre)
        if h is None:
            return Preparada(nombre, argumentos, conocida=False, error=ErrorHerramienta(404, f"No existe la herramienta {nombre}"))
        try:
            p = h.validar(argumentos)
        except ErrorArgumentos as exc:
            return Preparada(nombre, argumentos, etiqueta=h.titulo_base, error=ErrorHerramienta(422, str(exc)))
        return Preparada(nombre, argumentos, params=p, etiqueta=h.etiqueta(p), lenta=h.lenta(p))

    async def ejecutar(self, preparada):
        return await self._por_nombre[preparada.nombre].ejecutar(self.ctx, preparada.params)


@dataclass
class Resumen:
    """Lo que el chat pone en `done` y el arnés en cada corrida."""
    rondas: int = 0
    texto: str = ""
    tokens_prompt_max: int = 0       # el presupuesto de una ronda (criterio 12)
    tokens_respuesta: int = 0
    ms_modelo: float = 0.0
    ms_herramientas: float = 0.0
    razonamiento_filtrado: bool = False
    llamadas: list[dict] = field(default_factory=list)       # {ronda, herramienta, argumentos}
    resultados: list[Any] = field(default_factory=list)      # lo que leyó el modelo, en orden
    fechas_datos: list[str] = field(default_factory=list)


def _mensaje_asistente(texto: str, llamadas) -> dict:
    return {
        "role": "assistant",
        "content": texto,
        "tool_calls": [
            {**({"id": ll.id} if ll.id else {}), "function": {"name": ll.nombre, "arguments": ll.argumentos}}
            for ll in llamadas
        ],
    }


async def _ejecutar(ejecutor: Ejecutor, prep: Preparada, request_id: str) -> tuple[Resultado | None, ErrorHerramienta | None]:
    if prep.error:
        return None, prep.error
    try:
        return await ejecutor.ejecutar(prep), None
    except ErrorHerramienta as exc:
        return None, exc
    except Exception:
        # Una forma inesperada de la respuesta no tumba el chat; queda en el registro, sin datos
        log.exception("herramienta request_id=%s nombre=%s falló", request_id, prep.nombre)
        return None, ErrorHerramienta(500, "Falla interna de la herramienta")


async def responder(
    llm: ClienteLLM,
    mensajes: list[dict],
    ejecutor: Ejecutor,
    resumen: Resumen,
    opciones: dict | None = None,
    max_rondas: int = MAX_RONDAS,
    request_id: str = "",
) -> AsyncIterator[tuple[str, dict]]:
    """Agrega a `mensajes` las rondas y produce (evento, datos). Las cifras quedan en `resumen`."""
    invalidas = 0
    for ronda in range(1, max_rondas + 2):
        con_herramientas = ronda <= max_rondas and invalidas < MAX_ARGUMENTOS_INVALIDOS
        llamadas, texto, cerrada = [], "", False
        fragmentos = llm.chat_stream(mensajes, opciones, ejecutor.catalogo if con_herramientas else None).__aiter__()
        try:
            async for f in fragmentos:
                if f.llamadas:
                    llamadas += f.llamadas
                elif f.fin:
                    cerrada = True
                    m = f.metricas
                    if m:
                        resumen.tokens_prompt_max = max(resumen.tokens_prompt_max, m.tokens_prompt)
                        resumen.tokens_respuesta += m.tokens_respuesta
                        resumen.ms_modelo += m.ms_total
                    resumen.razonamiento_filtrado |= f.razonamiento_filtrado
                elif f.texto:
                    texto += f.texto
                    resumen.texto += f.texto
                    yield "token", {"texto": f.texto}
        finally:
            await fragmentos.aclose()    # si el cliente se fue, corta la generación en Ollama
        resumen.rondas = ronda
        if not cerrada:
            raise ErrorLLM("respuesta_invalida", "el modelo terminó sin cerrar la respuesta")
        if not llamadas or not con_herramientas:
            return
        mensajes.append(_mensaje_asistente(texto, llamadas))
        for n, ll in enumerate(llamadas, 1):
            resumen.llamadas.append({"ronda": ronda, "herramienta": ll.nombre, "argumentos": ll.argumentos})
            if ll.error:
                prep = Preparada(ll.nombre, {}, error=ErrorHerramienta(422, f"Argumentos inválidos: {ll.error}. Envía un objeto JSON."))
                prep.conocida = ll.nombre in {h["function"]["name"] for h in ejecutor.catalogo}
            else:
                prep = ejecutor.preparar(ll.nombre, ll.argumentos)
            if not prep.conocida:
                contenido = prep.error.para_modelo()
            else:
                id_ = f"{ronda}-{n}"
                yield "tool", {"id": id_, "nombre": ll.nombre, "estado": "inicio", "etiqueta": prep.etiqueta, "lenta": prep.lenta}
                inicio = time.monotonic()
                resultado, error = await _ejecutar(ejecutor, prep, request_id)
                ms = round((time.monotonic() - inicio) * 1000)
                resumen.ms_herramientas += ms
                invalidas += bool(error and error.status == 422 and prep.error)
                log.info("herramienta request_id=%s nombre=%s estado=%s codigo=%s ms=%d",
                         request_id, ll.nombre, "error" if error else "ok", error.status if error else "-", ms)
                yield "tool", {"id": id_, "nombre": ll.nombre, "estado": "error" if error else "ok", "ms": ms,
                               "codigo": error.status if error else None}
                if error:
                    contenido = error.para_modelo()
                else:
                    contenido = resultado.para_modelo
                    if resultado.fecha_dato and resultado.fecha_dato not in resumen.fechas_datos:
                        resumen.fechas_datos.append(resultado.fecha_dato)
                    if resultado.data:
                        yield "data", {"id": id_, "herramienta": ll.nombre, **resultado.data, "fecha_dato": resultado.fecha_dato}
            resumen.resultados.append(contenido)
            mensajes.append({"role": "tool", "tool_name": ll.nombre, "content": json.dumps(contenido, ensure_ascii=False)})
