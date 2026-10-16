"""
INV-30 — `POST /chat`: el «hola» de punta a punta, con el modelo y sin herramientas.

Solo lo llama el Core API (INV-36) con el `Authorization` del usuario y un
`X-Request-Id`. Responde SSE con `meta`, `token`…, y `done` o `error` al final
(docs/INV-30-requerimientos.md §4.3); INV-32 agrega `tool` y `data`. El texto de
los mensajes nunca va a los registros (Ley 1581).
"""
import asyncio
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from chat.schemas import ChatPeticion
from chat.sse import evento
from core.config import get_settings
from llm.cliente import ErrorLLM

router = APIRouter(tags=["Chat"])
log = logging.getLogger("nlp_agent.chat")

VERSION_PROMPT = "v0"
PROMPT_SISTEMA = (Path(__file__).resolve().parent.parent / "prompts" / VERSION_PROMPT / "sistema.md").read_text(encoding="utf-8")
ROLES = {"usuario": "user", "agente": "assistant"}


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
    # El agente no valida el token: lo reenvía al Core API en cada herramienta
    # (INV-32), que es quien decide los permisos. Sin token no hay a nombre de quién consultar.
    if not authorization:
        raise HTTPException(401, "falta el encabezado Authorization con el token del usuario")
    _validar(peticion)
    s = get_settings()
    llm = request.app.state.llm
    request_id = x_request_id or uuid.uuid4().hex
    mensajes = [{"role": "system", "content": PROMPT_SISTEMA}] + [
        {"role": ROLES[m.rol], "content": m.texto} for m in peticion.mensajes
    ]

    async def flujo():
        inicio = time.monotonic()
        yield evento("meta", {
            "request_id": request_id,
            "modelo": s.LLM_MODELO,
            "version_prompt": VERSION_PROMPT,
            "fecha_datos": None,          # la ponen las herramientas de INV-32
        })
        codigo = "ok"
        fragmentos = llm.chat_stream(mensajes).__aiter__()
        limite = inicio + s.LLM_TIMEOUT_S
        try:
            while True:
                restante = limite - time.monotonic()
                if restante <= 0:
                    raise TimeoutError
                try:
                    f = await asyncio.wait_for(fragmentos.__anext__(), restante)
                except StopAsyncIteration:
                    raise ErrorLLM("respuesta_invalida", "el modelo terminó sin cerrar la respuesta") from None
                if not f.fin:
                    yield evento("token", {"texto": f.texto})
                    continue
                yield evento("done", {
                    "tokens_prompt": f.metricas.tokens_prompt,
                    "tokens_respuesta": f.metricas.tokens_respuesta,
                    "ms_total": round((time.monotonic() - inicio) * 1000),
                })
                break
        except TimeoutError:
            codigo = "tiempo_agotado"
            yield evento("error", {"codigo": codigo, "mensaje": f"el agente superó {s.LLM_TIMEOUT_S:.0f} s"})
        except ErrorLLM as exc:
            codigo = exc.codigo
            yield evento("error", {"codigo": codigo, "mensaje": exc.mensaje})
        finally:
            await fragmentos.aclose()     # si el cliente se fue, corta la generación en Ollama
            log.info("chat request_id=%s resultado=%s ms=%d", request_id, codigo, (time.monotonic() - inicio) * 1000)

    return StreamingResponse(
        flujo(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Request-Id": request_id},
    )
