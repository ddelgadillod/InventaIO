"""
InventAI/o — API de chat (INV-36)
POST /api/chat/message: valida el token (los 3 roles) y la conversación, toma
un cupo (429 si no hay, X3), abre el flujo del agente interno con el token del
usuario y reenvía sus eventos SSE sin cambios (contrato v1, §4.3 de
docs/INV-30-requerimientos.md). Corta a los CHAT_TIMEOUT_S con un evento
`error` `tiempo_agotado` y, si el cliente se va, cierra el flujo del agente,
que corta la generación. GET /api/chat/health: el estado del agente (X7).
Decisiones en docs/INV-36-requerimientos.md.
"""
import asyncio
import logging
import re
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from auth.dependencies import bearer_scheme, get_current_user, resolver_usuario
from chat.cliente import get_cliente_agente
from chat.concurrencia import get_limitador
from chat.sse import Reenvio, evento
from core.config import get_settings
from core.database import get_db
from models.usuario import Usuario
from schemas.chat import PeticionChat, SaludChat

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# El Core API no configura registros propios (C8): una línea por flujo, sin texto (X9, Ley 1581)
log = logging.getLogger("inventaio.chat")
if not log.handlers:
    _manejador = logging.StreamHandler()
    _manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_manejador)
    log.setLevel(logging.INFO)

REQUEST_ID = re.compile(r"[0-9a-f]{32}")
EJEMPLO_SSE = (
    'event: meta\ndata: {"request_id": "9dbe36948a4f445d9febc02de8812e57", "modelo": "qwen3:8b", "version_prompt": "v1"}\n\n'
    'event: tool\ndata: {"id": "1-1", "nombre": "consultar_inventario", "estado": "inicio", '
    '"etiqueta": "Inventario · GLORIETA · crítico", "lenta": false}\n\n'
    'event: tool\ndata: {"id": "1-1", "nombre": "consultar_inventario", "estado": "ok", "ms": 302, "codigo": null}\n\n'
    'event: data\ndata: {"id": "1-1", "herramienta": "consultar_inventario", "forma": "tabla", '
    '"titulo": "Inventario · GLORIETA · crítico", "columnas": [...], "filas": [...], "total": 173, '
    '"mostrando": 10, "fecha_dato": "2025-12-31"}\n\n'
    'event: token\ndata: {"texto": "En GLORIETA hay 173 productos en estado crítico"}\n\n'
    'event: done\ndata: {"tokens_prompt": 2248, "tokens_respuesta": 86, "ms_total": 3777, "ms_modelo": 3400, '
    '"ms_herramientas": 302, "rondas": 2, "fechas_datos": ["2025-12-31"]}\n\n'
)


class RespuestaSSE(StreamingResponse):
    media_type = "text/event-stream"


def usuario_chat(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    # La sesión se cierra al resolver el usuario, no al terminar el flujo de 120 s (X12, C5)
    db: Session = Depends(get_db, scope="function"),
) -> tuple[Usuario, dict, str]:
    usuario, payload = resolver_usuario(credentials.credentials, db)
    return usuario, payload, credentials.credentials


@router.post(
    "/message",
    response_class=RespuestaSSE,
    summary="Pregunta al agente, con la respuesta en streaming (SSE)",
    description=(
        "Para los 3 roles. El cuerpo es la conversación (`mensajes`, a lo sumo 13, el último del usuario). "
        "Responde `text/event-stream` con los eventos del agente sin cambios: `meta`, `tool`, `data`, "
        "`token` y `done` o `error` (contrato v1, docs/INV-30-requerimientos.md §4.3), más comentarios "
        "`: ping` cada 15 s. Un fallo antes del primer evento sale con su código (503, 502 o 504); "
        "después, como evento `error`. A los 120 s, `error` `tiempo_agotado`."
    ),
    responses={
        200: {"description": "Flujo de eventos SSE", "content": {"text/event-stream": {"example": EJEMPLO_SSE}}},
        401: {"description": "Token inválido, vencido, de refresco o que vence en menos de 120 s"},
        403: {"description": "Sin token o cuenta desactivada"},
        429: {"description": "Ya hay una respuesta en curso del usuario o el asistente está ocupado; con Retry-After"},
        502: {"description": "El agente respondió algo distinto de un flujo de eventos"},
        503: {"description": "Agente no disponible"},
        504: {"description": "El agente no envió el primer evento a tiempo"},
    },
)
async def mensaje(
    peticion: PeticionChat,
    auth: tuple = Depends(usuario_chat),
    x_request_id: str | None = Header(None),
):
    usuario, payload, token = auth
    s = get_settings()
    inicio = time.monotonic()
    request_id = x_request_id if x_request_id and REQUEST_ID.fullmatch(x_request_id) else uuid.uuid4().hex
    registro = {"request_id": request_id, "usuario_id": usuario.id, "rol": usuario.rol}

    # X6: un token que vence en medio del flujo dejaría a las herramientas sin permiso
    if payload.get("exp") is not None and payload["exp"] - time.time() < s.CHAT_MARGEN_TOKEN_S:
        _registrar(registro, "rechazado", 401, inicio)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El token vence antes de terminar la respuesta: renuévelo",
                            headers={"WWW-Authenticate": "Bearer"})
    limitador = get_limitador()
    try:
        limitador.reservar(usuario.id)
    except HTTPException as exc:
        _registrar(registro, "rechazado", exc.status_code, inicio)
        raise
    try:
        flujo = await get_cliente_agente().abrir(peticion.model_dump(), f"Bearer {token}", request_id)
    except HTTPException as exc:
        limitador.liberar(usuario.id)
        _registrar(registro, "error", exc.status_code, inicio)
        raise

    async def reenviar():
        reenvio, resultado = Reenvio(), "interrumpido"
        try:
            for bloque in reenvio.recibir(flujo.primero):
                yield bloque
            while True:
                restante = inicio + s.CHAT_TIMEOUT_S - time.monotonic()
                try:
                    if restante <= 0:
                        raise TimeoutError
                    fragmento = await asyncio.wait_for(flujo.fragmentos.__anext__(), restante)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    resultado = "error"
                    reenvio.codigo_error = "tiempo_agotado"
                    yield evento("error", {"codigo": "tiempo_agotado",
                                           "mensaje": f"El asistente superó {s.CHAT_TIMEOUT_S:g} s"})
                    return
                for bloque in reenvio.recibir(fragmento):
                    yield bloque
            if resto := reenvio.resto():
                yield resto
            # X5-b no se aprobó: si el agente corta sin done ni error, no se agrega nada
            resultado = {"done": "ok", "error": "error"}.get(reenvio.ultimo, "interrumpido")
        except asyncio.CancelledError:
            resultado = "cancelado"                   # el cliente se fue
            raise
        except Exception:
            resultado = "error"
            log.exception("chat request_id=%s falló el reenvío", request_id)
        finally:
            await flujo.cerrar()
            limitador.liberar(usuario.id)
            _registrar(registro, resultado, reenvio.codigo_error or 200, inicio, reenvio)

    return RespuestaSSE(reenviar(), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                             "X-Request-Id": request_id})


def _registrar(registro: dict, resultado: str, codigo, inicio: float, reenvio: Reenvio | None = None) -> None:
    done = reenvio.done if reenvio else {}
    log.info("chat request_id=%s usuario_id=%s rol=%s resultado=%s codigo=%s ms=%d eventos=%d tokens_prompt=%s "
             "tokens_respuesta=%s ms_modelo=%s ms_herramientas=%s rondas=%s",
             registro["request_id"], registro["usuario_id"], registro["rol"], resultado, codigo,
             (time.monotonic() - inicio) * 1000, reenvio.eventos if reenvio else 0, done.get("tokens_prompt", "-"),
             done.get("tokens_respuesta", "-"), done.get("ms_modelo", "-"), done.get("ms_herramientas", "-"),
             done.get("rondas", "-"))


@router.get(
    "/health",
    response_model=SaludChat,
    summary="Estado del asistente",
    description=("Para los 3 roles (X7). 200 con el modelo del agente, los flujos activos y el límite; "
                 "503 con `motivo` (`ollama_no_alcanzable`, `modelo_no_descargado` o `agente_no_disponible`)."),
    responses={503: {"description": "El agente o el modelo no están listos"}},
)
async def salud(usuario: Usuario = Depends(get_current_user)):
    listo = await get_cliente_agente().listo()
    limitador = get_limitador()
    return SaludChat(estado="listo", modelo=listo.get("modelo", ""), version=listo.get("version", ""),
                     flujos_activos=len(limitador.activos), limite=limitador.max_total)
