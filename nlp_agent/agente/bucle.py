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

INV-33: qwen3 a veces escribe la llamada como texto («<tools>{"name": …,
"arguments": …}</tools>») en lugar de pedirla (3 de 681 respuestas el 21-oct).
El comienzo de cada ronda se retiene mientras pueda ser esa etiqueta; si lo es,
la llamada se ejecuta como si hubiera llegado bien y el texto no se muestra.

INV-33 (§3f, 23-oct): las mejoras de `agente/mejoras.py`, cada una con su
interruptor: la guarda de argumentos antes de ejecutar (P1, P6), la aclaración
armada con los candidatos (P2), la regla de «sin datos» del verificador (P3),
seguir cuando el modelo solo ofrece consultar (P4) y el razonamiento en el
reintento (P7). `resumen.llamadas` guarda lo que pidió el modelo y
`resumen.ejecutadas`, lo que se consultó.
"""
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from agente.fidelidad import (
    aclaracion_sin_opciones,
    fecha_de,
    respaldo,
    respaldo_glosario,
)
from agente.fidelidad import verificar as verificar_respuesta
from agente.mejoras import (
    CONTINUAR,
    Mejoras,
    aclaracion,
    corregir_argumentos,
    ofrece_consultar,
    pregunta_con_opciones,
    sin_repetidas,
    texto_usuario,
)
from agente.sugerencias import sugerencias
from herramientas.base import ErrorArgumentos, Resultado
from herramientas.catalogo import CATALOGO, esquemas
from herramientas.contexto import Contexto
from herramientas.core_api import ErrorHerramienta
from llm.cliente import ClienteLLM, ErrorLLM, LlamadaHerramienta

MAX_RONDAS = 3
ETIQUETAS_LLAMADA = ("<tools>", "<tool_call>")
LLAMADA_EN_TEXTO = re.compile(r"^\s*<(tools|tool_call)>\s*(.*?)\s*</\1>\s*$", re.DOTALL)
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
        # Con las correcciones del contexto (INV-33, §3g), el esquema puede cambiar (C1, C4)
        self.catalogo = esquemas(ctx.mejoras) if catalogo is CATALOGO else [h.esquema() for h in catalogo]

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
    llamadas_en_texto: int = 0       # INV-33: llamadas que el modelo escribió como texto y se recuperaron
    fechas_datos: list[str] = field(default_factory=list)
    # INV-33 (Z1, Z4, Z9, Z11, Z14): solo con `verificar`
    datos: list[dict] = field(default_factory=list)          # las tablas de `data`, para la respuesta de respaldo
    borrador: str = ""               # la primera respuesta final del modelo, antes de verificarla
    fidelidad: str = ""              # ok | reintento | respaldo
    cifras_sin_respaldo: int = 0     # del borrador
    respaldo: bool = False
    sugerencias: list[str] = field(default_factory=list)   # Z6: según las herramientas usadas
    # INV-33 (§3f): solo con las mejoras
    ejecutadas: list[dict] = field(default_factory=list)    # {ronda, herramienta, argumentos}, tras la guarda
    correcciones: list[str] = field(default_factory=list)   # lo que corrigió la guarda (P1, P6)
    aclaracion: bool = False         # P2: la respuesta es la aclaración armada con los candidatos
    seguida: bool = False            # P4: el bucle siguió cuando el modelo solo ofreció consultar


def llamadas_en_texto(texto: str) -> list[LlamadaHerramienta] | None:
    """Las llamadas que el modelo escribió como texto, o None si el texto no es solo eso."""
    m = LLAMADA_EN_TEXTO.match(texto)
    if not m:
        return None
    cuerpo = m.group(2)
    try:
        objetos = json.loads(cuerpo)
    except json.JSONDecodeError:
        try:                                        # una llamada por línea
            objetos = [json.loads(linea) for linea in cuerpo.splitlines() if linea.strip()]
        except json.JSONDecodeError:
            return None
    objetos = objetos if isinstance(objetos, list) else [objetos]
    llamadas = []
    for o in objetos:
        if not isinstance(o, dict) or not isinstance(o.get("name"), str):
            return None
        argumentos = o.get("arguments", {})
        if isinstance(argumentos, str):
            try:
                argumentos = json.loads(argumentos)
            except json.JSONDecodeError:
                return None
        if not isinstance(argumentos, dict):
            return None
        llamadas.append(LlamadaHerramienta(o["name"], argumentos))
    return llamadas or None


def _puede_ser_llamada(texto: str) -> bool:
    t = texto.lstrip()
    return not t or any(e.startswith(t) or t.startswith(e) for e in ETIQUETAS_LLAMADA)


def _sugerencias(resumen: "Resumen") -> list[str]:
    """Z6: según las herramientas que respondieron; ninguna tras un 403 (un rechazo no sugiere más consultas)."""
    sin_permiso = any(isinstance(r, dict) and (r.get("error") or {}).get("status") == 403 for r in resumen.resultados)
    usadas = [ll["herramienta"] for ll, r in zip(resumen.llamadas, resumen.resultados, strict=False)
              if not (isinstance(r, dict) and "error" in r)]
    return sugerencias(usadas, hubo_error=sin_permiso)


def _emitir(resumen: "Resumen", final: str):
    """Un texto ya decidido se emite por palabras, como un stream."""
    for pedazo in re.findall(r"\S+\s*|\s+", final):
        resumen.texto += pedazo
        yield "token", {"texto": pedazo}


def _guarda(llamadas: list, texto: str, mejoras: Mejoras, resumen: "Resumen", request_id: str) -> tuple[list, dict]:
    """P1 y P6: las llamadas que se ejecutan, sin filtros que no se pidieron ni repetidas, y lo corregido en cada una."""
    corregidas, notas = [], {}
    for ll in llamadas:
        if ll.error:
            corregidas.append(ll)
            continue
        nuevos, correcciones = corregir_argumentos(ll.nombre, ll.argumentos, texto, filtros=mejoras.argumentos,
                                                   agrupacion=mejoras.agrupacion, meses=mejoras.meses,
                                                   relleno=mejoras.relleno, periodo=mejoras.periodo)
        corregidas.append(replace(ll, argumentos=nuevos) if correcciones else ll)
        if correcciones:
            notas[len(corregidas) - 1] = correcciones
            resumen.correcciones += [f"{ll.nombre}: {c}" for c in correcciones]
    if mejoras.argumentos:
        quedan, quitadas = sin_repetidas([(ll.nombre, ll.argumentos) for ll in corregidas])
        if quitadas:
            resumen.correcciones.append(f"{quitadas} llamada(s) repetida(s)")
        notas = {quedan.index(i): n for i, n in notas.items() if i in quedan}
        corregidas = [corregidas[i] for i in quedan]
    if resumen.correcciones:
        log.info("guarda request_id=%s correcciones=%d", request_id, len(resumen.correcciones))
    return corregidas, notas


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
    verificar: bool = False,
    mejoras: Mejoras = Mejoras(),
) -> AsyncIterator[tuple[str, dict]]:
    """Agrega a `mensajes` las rondas y produce (evento, datos). Las cifras quedan en `resumen`.

    Con `verificar` (INV-33, Z1): la respuesta final no se transmite mientras se genera. Se verifica (cifras y total,
    `agente/fidelidad.py`); si falla, el modelo la corrige una vez y, si vuelve a fallar, va la respuesta de respaldo
    con los datos consultados. Si no dice la fecha de los datos, se le agrega el cierre fijo (Z2). `mejoras`: §3f;
    seguir (P4) y la regla de «sin datos» (P3) solo actúan con `verificar`, porque necesitan retener la respuesta."""
    invalidas, reintentada, razonar = 0, False, False
    contexto = "\n".join(m["content"] for m in mensajes if m.get("role") in ("system", "user", "assistant")
                         and isinstance(m.get("content"), str))       # la conversación: lo que el modelo ya sabía
    texto_u = texto_usuario(mensajes)
    for ronda in range(1, max_rondas + 3):
        con_herramientas = ronda <= max_rondas and invalidas < MAX_ARGUMENTOS_INVALIDOS
        llamadas, texto, cerrada = [], "", False
        retenido = con_herramientas or verificar      # el comienzo, mientras pueda ser una llamada escrita; todo, si se verifica
        extra = {"razonar": True} if razonar else {}  # P7: solo la ronda del reintento
        razonar = False
        fragmentos = llm.chat_stream(mensajes, opciones, ejecutor.catalogo if con_herramientas else None, **extra).__aiter__()
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
                    if verificar or (retenido and _puede_ser_llamada(texto)):
                        continue
                    salida, retenido = (texto if retenido else f.texto), False
                    resumen.texto += salida
                    yield "token", {"texto": salida}
        finally:
            await fragmentos.aclose()    # si el cliente se fue, corta la generación en Ollama
        resumen.rondas = ronda
        if not cerrada:
            raise ErrorLLM("respuesta_invalida", "el modelo terminó sin cerrar la respuesta")
        if retenido and texto and con_herramientas and not llamadas and (escritas := llamadas_en_texto(texto)):
            llamadas, texto = escritas, ""
            resumen.llamadas_en_texto += len(escritas)
            log.info("llamada escrita como texto request_id=%s nombres=%s", request_id, [x.nombre for x in escritas])
        elif retenido and texto and not verificar:
            resumen.texto += texto
            yield "token", {"texto": texto}
        if not llamadas or not con_herramientas:
            resumen.sugerencias = _sugerencias(resumen)
            if not verificar:
                return
            if mejoras.aclaracion and aclaracion_sin_opciones(texto, resumen.resultados) and \
                    (pregunta := pregunta_con_opciones(resumen.resultados)):
                # P2: preguntó «¿cuál?» sin nombrar las opciones que trajo la herramienta: se le agregan
                resumen.aclaracion, resumen.sugerencias = True, []
                resumen.borrador, resumen.fidelidad = texto, "ok"
                log.info("aclaracion request_id=%s ronda=%d sin_opciones=true", request_id, ronda)
                for evento in _emitir(resumen, pregunta):
                    yield evento
                return
            if (mejoras.seguir and not resumen.seguida and ronda < max_rondas and invalidas < MAX_ARGUMENTOS_INVALIDOS
                    and ofrece_consultar(texto)):
                # P4: solo ofreció consultar algo que el bucle puede consultar ya: se le contesta que sí, una vez
                resumen.seguida = True
                mensajes.append({"role": "assistant", "content": texto})
                mensajes.append({"role": "user", "content": CONTINUAR})
                log.info("seguir request_id=%s ronda=%d", request_id, ronda)
                continue
            v = verificar_respuesta(texto, contexto, resumen.resultados, sin_datos=mejoras.sin_datos)
            if not reintentada:
                resumen.borrador, resumen.cifras_sin_respaldo = texto, len(v.cifras_sin_respaldo)
            if not v.ok and not reintentada:
                # Un reintento con lo que hay que corregir (Z4); puede volver a consultar si quedan rondas
                reintentada, razonar = True, mejoras.razonar
                mensajes.append({"role": "assistant", "content": texto})
                mensajes.append({"role": "user", "content": f"(Verificación automática) {v.correccion()}"})
                log.info("fidelidad request_id=%s reintento cifras=%s totales=%s sin_datos=%s", request_id,
                         len(v.cifras_sin_respaldo), v.totales_omitidos, v.sin_datos_con_contenido)
                continue
            if v.ok:
                resumen.fidelidad = "reintento" if reintentada else "ok"
                resumen.sugerencias = _sugerencias(resumen)
                final = f"{texto.rstrip()}\n\n{v.cierre()}" if v.cierre() else texto
            else:
                resumen.fidelidad, resumen.respaldo, resumen.sugerencias = "respaldo", True, []
                final = ((mejoras.glosario and not resumen.datos and respaldo_glosario(resumen.resultados))
                         or respaldo(resumen.datos, fecha_de(resumen.resultados)))
            log.info("fidelidad request_id=%s resultado=%s cifras_sin_respaldo=%d", request_id, resumen.fidelidad,
                     resumen.cifras_sin_respaldo)
            for evento in _emitir(resumen, final):
                yield evento
            return
        for ll in llamadas:
            resumen.llamadas.append({"ronda": ronda, "herramienta": ll.nombre, "argumentos": ll.argumentos})
        notas = {}
        if mejoras.argumentos or mejoras.agrupacion or mejoras.relleno or mejoras.periodo:
            llamadas, notas = _guarda(llamadas, texto_u, mejoras, resumen, request_id)
        mensajes.append(_mensaje_asistente(texto, llamadas))
        de_la_ronda = len(resumen.resultados)
        for n, ll in enumerate(llamadas, 1):
            resumen.ejecutadas.append({"ronda": ronda, "herramienta": ll.nombre, "argumentos": ll.argumentos})
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
                        resumen.datos.append(resultado.data)
                        yield "data", {"id": id_, "herramienta": ll.nombre, **resultado.data, "fecha_dato": resultado.fecha_dato}
            if notas.get(n - 1) and isinstance(contenido, dict):
                contenido = {**contenido, "nota_guarda": "Se quitó " + "; ".join(notas[n - 1])}
            resumen.resultados.append(contenido)
            mensajes.append({"role": "tool", "tool_name": ll.nombre, "content": json.dumps(contenido, ensure_ascii=False)})
        if mejoras.aclaracion and (pregunta := aclaracion(resumen.resultados[de_la_ronda:])):
            # P2: la ronda solo trajo «ambiguo»: se pregunta cuál, con las opciones, sin pasar por el modelo
            resumen.aclaracion, resumen.sugerencias = True, []
            if verificar:
                resumen.borrador, resumen.fidelidad = pregunta, "ok"
            log.info("aclaracion request_id=%s ronda=%d", request_id, ronda)
            for evento in _emitir(resumen, pregunta):
                yield evento
            return
