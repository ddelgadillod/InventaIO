"""
`POST /chat` del agente: contrato v1 (§4.3 de docs/INV-30-requerimientos.md).

Solo lo llama el Core API (INV-36) con el `Authorization` del usuario y un
`X-Request-Id`. Responde SSE con `meta` de inmediato y después los eventos del
bucle de herramientas de INV-32 (`tool`, `data`, `token`), y `done` o `error` al
final, con `: ping` cada CHAT_PING_S de silencio (X5-c de INV-36). Todo dentro
de `LLM_TIMEOUT_S`. El texto de los mensajes nunca va a los
registros (Ley 1581).
"""
import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from agente.bucle import EjecutorCoreAPI, Resumen, responder
from agente.historial import POR_PERFIL, recortar
from agente.mejoras import Mejoras
from agente.prompt import prompt_sistema, quien, version_prompt
from chat.schemas import ChatPeticion
from chat.sse import evento
from core.config import get_settings
from herramientas.contexto import Contexto
from herramientas.core_api import ErrorHerramienta
from llm.cliente import ErrorLLM

router = APIRouter(tags=["Chat"])
log = logging.getLogger("nlp_agent.chat")

ROLES = {"usuario": "user", "agente": "assistant"}
PING = ": ping\n\n"               # comentario SSE: los lectores lo ignoran (X5-c de INV-36)


def _validar(peticion: ChatPeticion) -> None:
    s = get_settings()
    if len(peticion.mensajes) > s.MAX_MENSAJES:
        raise HTTPException(422, f"a lo sumo {s.MAX_MENSAJES} mensajes por petición")
    if any(len(m.texto) > s.MAX_CARACTERES_MENSAJE for m in peticion.mensajes):
        raise HTTPException(422, f"cada mensaje admite a lo sumo {s.MAX_CARACTERES_MENSAJE} caracteres")
    if peticion.mensajes[-1].rol != "usuario":
        raise HTTPException(422, "el último mensaje debe ser del usuario")


@router.post("/chat")
async def chat(
    peticion: ChatPeticion,
    request: Request,
    authorization: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    # El agente no valida el token: lo reenvía al Core API en cada herramienta,
    # que es quien decide los permisos (D13). Sin token no hay a nombre de quién consultar.
    if not authorization:
        raise HTTPException(401, "falta el encabezado Authorization con el token del usuario")
    _validar(peticion)
    s = get_settings()
    llm = request.app.state.llm
    request_id = x_request_id or uuid.uuid4().hex
    mejoras = Mejoras.desde_texto(s.MEJORAS)
    ctx = Contexto(request.app.state.core, authorization, request_id, mejoras=mejoras)
    completo = [{"role": ROLES[m.rol], "content": m.texto} for m in peticion.mensajes]
    # Z7: turnos completos fuera, desde el más viejo, hasta caber en el presupuesto; la pregunta siempre queda
    historial, turnos_recortados = recortar(completo, s.HISTORIAL_PRESUPUESTO or POR_PERFIL.get(s.PERFIL_PROMPT, 1500))

    async def flujo():
        inicio = time.monotonic()
        limite = inicio + s.LLM_TIMEOUT_S
        # Primero y de inmediato, antes de llamar al Core API o a Ollama (X5-f)
        yield evento("meta", {"request_id": request_id, "modelo": s.LLM_MODELO,
                              "version_prompt": version_prompt(s.PROMPT_VERSION, s.PERFIL_PROMPT)})
        codigo, resumen, eventos, pendiente = "ok", Resumen(), None, None
        try:
            try:
                perfil = await asyncio.wait_for(ctx.perfil(), max(limite - time.monotonic(), 0.001))
                rol, sucursal = perfil.rol, perfil.sucursal
            except ErrorHerramienta:
                rol, sucursal = None, None       # sin perfil, las herramientas igual responden con su error
            sistema = prompt_sistema(quien(rol, sucursal), rol, sucursal, s.PROMPT_VERSION, s.PERFIL_PROMPT)
            mensajes = [{"role": "system", "content": sistema}, *historial]
            # Z1: con FIDELIDAD_RETENER, el bucle verifica la respuesta (con la conversación recortada como contexto)
            eventos = responder(llm, mensajes, EjecutorCoreAPI(ctx), resumen, request_id=request_id,
                                verificar=s.FIDELIDAD_RETENER, mejoras=mejoras).__aiter__()
            pendiente = None
            while True:
                restante = limite - time.monotonic()
                if restante <= 0:
                    raise TimeoutError
                # Sin cancelar la espera: si pasa CHAT_PING_S sin eventos, «: ping» y se sigue esperando
                pendiente = pendiente or asyncio.ensure_future(eventos.__anext__())
                listos, _ = await asyncio.wait({pendiente}, timeout=min(s.CHAT_PING_S, restante))
                if not listos:
                    if limite - time.monotonic() > 0:
                        yield PING
                    continue
                try:
                    nombre, datos = pendiente.result()
                except StopAsyncIteration:
                    break
                finally:
                    if pendiente.done():
                        pendiente = None
                yield evento(nombre, datos)
            yield evento("done", {
                "tokens_prompt": resumen.tokens_prompt_max,
                "tokens_respuesta": resumen.tokens_respuesta,
                "ms_total": round((time.monotonic() - inicio) * 1000),
                "ms_modelo": round(resumen.ms_modelo),
                "ms_herramientas": round(resumen.ms_herramientas),
                "rondas": resumen.rondas,
                "fechas_datos": resumen.fechas_datos,
                # Contrato v1.1 (INV-33, aprobado el 21-oct): sin verificación, fidelidad va en null
                "fidelidad": resumen.fidelidad or None,
                "respaldo": resumen.respaldo,
                "sugerencias": resumen.sugerencias,
                "turnos_recortados": turnos_recortados,
            })
        except TimeoutError:
            codigo = "tiempo_agotado"
            yield evento("error", {"codigo": codigo, "mensaje": f"el agente superó {s.LLM_TIMEOUT_S:.0f} s"})
        except ErrorLLM as exc:
            codigo = exc.codigo
            yield evento("error", {"codigo": codigo, "mensaje": exc.mensaje})
        finally:
            if pendiente is not None and not pendiente.done():
                pendiente.cancel()
                await asyncio.gather(pendiente, return_exceptions=True)
            if eventos is not None:
                await eventos.aclose()     # si el cliente se fue, corta la generación en Ollama
            # Z14: también la fidelidad, las cifras sin respaldo del borrador y lo recortado; nunca el texto
            log.info("chat request_id=%s resultado=%s ms=%d rondas=%d herramientas=%d tokens_prompt=%d tokens_respuesta=%d "
                     "fidelidad=%s cifras_sin_respaldo=%d turnos_recortados=%d correcciones=%d aclaracion=%s seguida=%s",
                     request_id, codigo, (time.monotonic() - inicio) * 1000, resumen.rondas, len(resumen.llamadas),
                     resumen.tokens_prompt_max, resumen.tokens_respuesta, resumen.fidelidad or "-",
                     resumen.cifras_sin_respaldo, turnos_recortados, len(resumen.correcciones),
                     str(resumen.aclaracion).lower(), str(resumen.seguida).lower())

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Request-Id": request_id},
    )
