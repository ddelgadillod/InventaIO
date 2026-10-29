"""
InventAI/o — Cliente del Core API hacia el agente (INV-36, X11)
Como api/ml/cliente.py, pero asíncrono y en streaming. Reenvía el token del
usuario y el X-Request-Id: el agente consulta el Core API a su nombre (D13).

Antes de responder 200, espera el primer evento del agente hasta
CHAT_ESPERA_INICIO_S (X4), así los fallos de conexión salen con su código
HTTP: 503 si no hay agente o responde 503, 502 si responde otra cosa y 504 si
no envía nada a tiempo. Después, los fallos los maneja el router como eventos.
"""
import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache

import httpx
from fastapi import HTTPException, status

from core.config import get_settings


@dataclass
class Flujo:
    respuesta: httpx.Response
    fragmentos: AsyncIterator[bytes]
    primero: bytes

    async def cerrar(self) -> None:
        # Cierra la conexión: el agente ve la desconexión y corta la generación (X5-e)
        await self.respuesta.aclose()


def _motivo(r: httpx.Response) -> str | None:
    try:
        cuerpo = r.json()
    except ValueError:
        return None
    return cuerpo.get("motivo") if isinstance(cuerpo, dict) else None


class ClienteAgente:
    def __init__(self, base_url: str, espera_inicio: float, transport: httpx.AsyncBaseTransport | None = None):
        self.espera_inicio = espera_inicio
        # Sin tiempo de lectura propio: el router controla el total del flujo
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport,
                                       timeout=httpx.Timeout(None, connect=5.0, write=10.0, pool=5.0))

    async def abrir(self, cuerpo: dict, autorizacion: str, request_id: str) -> Flujo:
        limite = time.monotonic() + self.espera_inicio
        peticion = self._http.build_request("POST", "/chat", json=cuerpo,
                                            headers={"Authorization": autorizacion, "X-Request-Id": request_id})
        try:
            r = await asyncio.wait_for(self._http.send(peticion, stream=True), self.espera_inicio)
        except TimeoutError:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, f"El agente no respondió en {self.espera_inicio:g} s")
        except httpx.TransportError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agente no disponible")
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("text/event-stream"):
            await r.aread()
            await r.aclose()
            if r.status_code == 503:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _motivo(r) or "Agente no disponible")
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Agente respondió {r.status_code}")
        fragmentos = r.aiter_raw()
        try:
            primero = await asyncio.wait_for(fragmentos.__anext__(), max(limite - time.monotonic(), 0.001))
        except TimeoutError:
            await r.aclose()
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, f"El agente no respondió en {self.espera_inicio:g} s")
        except StopAsyncIteration:
            await r.aclose()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "El agente cerró la respuesta sin enviar eventos")
        except httpx.TransportError:
            await r.aclose()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Agente no disponible")
        return Flujo(r, fragmentos, primero)

    async def listo(self) -> dict:
        """GET /ready del agente: {status, modelo, version, …} o, con 503, el motivo (X7)."""
        try:
            r = await self._http.get("/ready", timeout=10.0)
        except httpx.TransportError:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"motivo": "agente_no_disponible"})
        if r.status_code == 503:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"motivo": _motivo(r) or "agente_no_disponible"})
        if r.status_code != 200:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Agente respondió {r.status_code}")
        return r.json()

    async def cerrar(self) -> None:
        await self._http.aclose()


@lru_cache
def get_cliente_agente() -> ClienteAgente:
    s = get_settings()
    return ClienteAgente(s.NLP_AGENT_URL, s.CHAT_ESPERA_INICIO_S)
